import json
import boto3
import os
from botocore.exceptions import ClientError

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
report_table = dynamodb.Table(os.environ['REPORT_TABLE_NAME']) # 환경변수 처리
connection_table = dynamodb.Table(os.environ['CONNECTION_TABLE_NAME']) # 환경변수 처리
api_gateway = boto3.client('apigatewaymanagementapi', endpoint_url=os.environ['HTTP_API_ENDPOINT']) # 환경변수 처리

def lambda_handler(event, context):
    try:
        print(f"Received S3 event: {json.dumps(event)}")
        
        bucket = event['Records'][0]['s3']['bucket']['name']
        key = event['Records'][0]['s3']['object']['key']
        report_id = os.path.splitext(os.path.basename(key))[0]
        
        report = get_report_status(report_id)
        
        if key.endswith('.txt'):
            report['Description'] = s3.get_object(Bucket=bucket, Key=key)['Body'].read().decode('utf-8')
        else:
            report['ImageURL'] = f"https://{bucket}.s3.amazonaws.com/{key}"
        
        update_report_status(report_id, report)
        
        if 'ImageURL' in report and 'Description' in report:
            send_report_to_clients(report_id, report)
        
        return {'statusCode': 200, 'body': json.dumps('처리 완료')}
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return {'statusCode': 500, 'body': json.dumps('Internal Server Error')}

def get_report_status(report_id):
    try:
        response = report_table.get_item(Key={'ReportId': report_id})
        return response.get('Item', {})
    except ClientError as e:
        print(f"Error getting report status: {e.response['Error']['Message']}")
        return {}

def update_report_status(report_id, report):
    try:
        report_table.put_item(Item={'ReportId': report_id, **report})
    except ClientError as e:
        print(f"Error updating report status: {e.response['Error']['Message']}")

def send_report_to_clients(report_id, report):
    try:
        # HTTP API를 통해 클라이언트에게 메시지 전송
        http_api_url = os.environ['HTTP_API_URL']
        payload = {
            'action': 'newReport',
            'report': {
                'ReportId': report_id,
                'ImageURL': report.get('ImageURL'),
                'Description': report.get('Description')
            }
        }
        response = api_gateway.post_to_connection(
            url=http_api_url,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'}
        )
        print("Report successfully sent to HTTP API")
    except ClientError as e:
        print(f"Error sending HTTP API request: {e.response['Error']['Message']}")
    except Exception as e:
        print(f"Error in send_report_to_clients: {str(e)}")