import json
import boto3
import os
import logging
from datetime import datetime

# 로거 설정
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# AWS 클라이언트 설정
dynamodb = boto3.client('dynamodb')
s3 = boto3.client('s3')

def lambda_handler(event, context):
    try:
        logger.info(f"Received event: {json.dumps(event)}")

        if 'Records' in event and len(event['Records']) > 0:
            record = event['Records'][0]['s3']
            bucket = record['bucket']['name']
            key = record['object']['key']
            
            logger.info(f"Processing file: {key} from bucket: {bucket}")

            report_id = os.path.splitext(key)[0]
            _, file_extension = os.path.splitext(key)

            logger.info(f"ReportId: {report_id}, File extension: {file_extension}")

            # 파일 확장자 처리 및 DynamoDB 트랜잭션 준비
            image_extensions = ['.jpg', '.jpeg', '.png', '.gif']
            transaction_items = []
            
            # 이미지 처리
            if file_extension.lower() in image_extensions:
                s3_url = f'https://{bucket}.s3.amazonaws.com/{key}'
                transaction_items.append({
                    'Update': {
                        'TableName': 'Reports',
                        'Key': {'ReportId': {'S': report_id}},
                        'UpdateExpression': 'SET ImageURL = :image_url',
                        'ExpressionAttributeValues': {
                            ':image_url': {'S': s3_url}
                        }
                    }
                })
                logger.info(f"Image URL to be saved: {s3_url}")
            
            # 텍스트 파일 처리
            elif file_extension.lower() == '.txt':
                try:
                    obj = s3.get_object(Bucket=bucket, Key=key)
                    description = obj['Body'].read().decode('utf-8')
                    transaction_items.append({
                        'Update': {
                            'TableName': 'Reports',
                            'Key': {'ReportId': {'S': report_id}},
                            'UpdateExpression': 'SET Description = :description',
                            'ExpressionAttributeValues': {
                                ':description': {'S': description}
                            }
                        }
                    })
                    logger.info(f"Text description to be saved: {description[:100]}...")
                except Exception as e:
                    logger.error(f"Error reading text file: {str(e)}")
                    return create_api_response(404, f"Error reading text file: {str(e)}")
            
            # 트랜잭션이 비어 있지 않은 경우 트랜잭션 실행
            if transaction_items:
                try:
                    # 트랜잭션 처리
                    dynamodb.transact_write_items(TransactItems=transaction_items)
                    logger.info(f"Transaction completed for report: {report_id}")
                except Exception as e:
                    logger.error(f"Error executing transaction: {str(e)}")
                    return create_api_response(500, f"Error executing transaction: {str(e)}")
            else:
                logger.warning(f"No valid transactions to process for file: {key}")
                return create_api_response(400, f"No valid transactions to process for file: {key}")
            
            # 최종 상태 업데이트 및 타임스탬프 추가
            try:
                # 상태 업데이트 (Complete 또는 Incomplete)
                item_status = 'Complete' if file_extension.lower() in image_extensions and 'Description' in transaction_items else 'Incomplete'
                current_time = datetime.utcnow().isoformat()

                # 상태 업데이트를 트랜잭션으로 추가
                dynamodb.transact_write_items(
                    TransactItems=[{
                        'Update': {
                            'TableName': 'Reports',
                            'Key': {'ReportId': {'S': report_id}},
                            'UpdateExpression': 'SET Status = :status, LastUpdated = :last_updated',
                            'ExpressionAttributeValues': {
                                ':status': {'S': item_status},
                                ':last_updated': {'S': current_time}
                            }
                        }
                    }]
                )
                
                logger.info(f"Successfully updated status for report: {report_id}")

                return create_api_response(200, {
                    'message': 'Processing complete',
                    'reportId': report_id,
                    'status': item_status,
                    'lastUpdated': current_time
                })
            
            except Exception as e:
                logger.error(f"Error updating status in DynamoDB: {str(e)}")
                return create_api_response(500, f"Error updating status in DynamoDB: {str(e)}")
    
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return create_api_response(500, f"Unexpected error: {str(e)}")

def create_api_response(status_code, body):
    return {
        'statusCode': status_code,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
        },
        'body': json.dumps(body)
    }
