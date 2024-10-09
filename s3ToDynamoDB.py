import json
import boto3
import os
import logging
from datetime import datetime
from botocore.exceptions import ClientError

# 로거 설정
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# AWS 클라이언트 설정
dynamodb = boto3.client('dynamodb')
s3 = boto3.client('s3')
apigw_management = boto3.client('apigatewaymanagementapi', 
    endpoint_url=os.environ.get('WEBSOCKET_API_ENDPOINT'))

# 상수 정의
IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.gif']
TEXT_EXTENSIONS = ['.txt']
TABLE_NAME = os.environ.get('DYNAMODB_TABLE_NAME')

def get_connection_id(report_id):
    """DynamoDB에서 Connection ID를 가져오는 함수"""
    try:
        response = dynamodb.get_item(
            TableName=TABLE_NAME,
            Key={'ReportId': {'S': report_id}},
            ProjectionExpression='ConnectionId'
        )
        return response.get('Item', {}).get('ConnectionId', {}).get('S')
    except ClientError as e:
        logger.error(f"Error getting connection ID: {str(e)}")
        return None

def create_api_response(status_code, body):
    """API Gateway 응답 형식을 생성하는 함수"""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps(body)
    }

def send_websocket_message(connection_id, message):
    """WebSocket을 통해 메시지를 전송하는 함수"""
    if not connection_id:
        logger.warning("No connection ID provided for WebSocket message")
        return False
    
    try:
        apigw_management.post_to_connection(
            ConnectionId=connection_id,
            Data=json.dumps(message)
        )
        return True
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code')
        if error_code == 'GoneException':
            logger.warning(f"Connection {connection_id} is gone, removing from database")
            try:
                dynamodb.update_item(
                    TableName=TABLE_NAME,
                    Key={'ReportId': {'S': message['reportId']}},
                    UpdateExpression='REMOVE ConnectionId'
                )
            except ClientError as del_err:
                logger.error(f"Error removing connection ID: {str(del_err)}")
        else:
            logger.error(f"Error sending WebSocket message: {str(e)}")
        return False

def process_file(bucket, key, report_id, file_extension):
    """파일 처리 및 DynamoDB 업데이트를 수행하는 함수"""
    transaction_items = []
    description = None

    if file_extension.lower() in IMAGE_EXTENSIONS:
        s3_url = f'https://{bucket}.s3.amazonaws.com/{key}'
        transaction_items.append({
            'Update': {
                'TableName': TABLE_NAME,
                'Key': {'ReportId': {'S': report_id}},
                'UpdateExpression': 'SET ImageURL = :image_url',
                'ExpressionAttributeValues': {':image_url': {'S': s3_url}}
            }
        })
        logger.info(f"Image URL to be saved: {s3_url}")

    elif file_extension.lower() in TEXT_EXTENSIONS:
        try:
            obj = s3.get_object(Bucket=bucket, Key=key)
            description = obj['Body'].read().decode('utf-8')
            transaction_items.append({
                'Update': {
                    'TableName': TABLE_NAME,
                    'Key': {'ReportId': {'S': report_id}},
                    'UpdateExpression': 'SET Description = :description',
                    'ExpressionAttributeValues': {':description': {'S': description}}
                }
            })
            logger.info(f"Text description to be saved: {description[:100]}...")
        except ClientError as e:
            logger.error(f"Error reading text file: {str(e)}")
            raise

    return transaction_items, description

def update_report_status(report_id, has_image, has_description):
    """리포트 상태를 업데이트하는 함수"""
    current_time = datetime.utcnow().isoformat()
    status = 'Complete' if has_image and has_description else 'Incomplete'

    try:
        dynamodb.update_item(
            TableName=TABLE_NAME,
            Key={'ReportId': {'S': report_id}},
            UpdateExpression='SET #status = :status, LastUpdated = :last_updated',
            ExpressionAttributeNames={'#status': 'Status'},
            ExpressionAttributeValues={
                ':status': {'S': status},
                ':last_updated': {'S': current_time}
            }
        )
        return status, current_time
    except ClientError as e:
        logger.error(f"Error updating report status: {str(e)}")
        raise

def lambda_handler(event, context):
    try:
        logger.info(f"Received event: {json.dumps(event)}")

        if 'Records' not in event or not event['Records']:
            return create_api_response(400, "No records found in event")

        record = event['Records'][0]['s3']
        bucket = record['bucket']['name']
        key = record['object']['key']
        
        logger.info(f"Processing file: {key} from bucket: {bucket}")

        report_id = os.path.splitext(key)[0]
        file_extension = os.path.splitext(key)[1]

        # 파일 처리
        transaction_items, description = process_file(bucket, key, report_id, file_extension)
        
        if not transaction_items:
            return create_api_response(400, f"Unsupported file type: {file_extension}")

        # DynamoDB 트랜잭션 실행
        dynamodb.transact_write_items(TransactItems=transaction_items)
        
        # 현재 리포트 상태 확인
        try:
            response = dynamodb.get_item(
                TableName=TABLE_NAME,
                Key={'ReportId': {'S': report_id}},
                ProjectionExpression='ImageURL, Description'
            )
            item = response.get('Item', {})
            has_image = 'ImageURL' in item or file_extension.lower() in IMAGE_EXTENSIONS
            has_description = 'Description' in item or (description is not None)
        except ClientError as e:
            logger.error(f"Error checking current report status: {str(e)}")
            raise

        # 상태 업데이트
        status, last_updated = update_report_status(report_id, has_image, has_description)

        # WebSocket 메시지 전송
        connection_id = get_connection_id(report_id)
        if connection_id:
            message = {
                "reportId": report_id,
                "status": status,
                "lastUpdated": last_updated,
                "bucket": bucket,
                "file": key
            }
            send_websocket_message(connection_id, message)

        return create_api_response(200, {
            'message': 'Processing complete',
            'reportId': report_id,
            'status': status,
            'lastUpdated': last_updated
        })

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return create_api_response(500, f"Unexpected error: {str(e)}")
