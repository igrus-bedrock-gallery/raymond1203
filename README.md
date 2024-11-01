
# Infra - ResultController
## 설정사항

1. **S3 설정**
    - Notification 사용
    - 버킷 정책 추가:
    
    ```json
    {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": "*",
                "Action": "s3:GetObject",
                "Resource": "arn:aws:s3:::{본인버킷이름}/*"
            }
        ]
    }
    ```

2. **Lambda IAM 설정**
   - 본인은 FullAccess로 S3, DynamoDB, apigateway 설정해놓음

3. **DynamoDB 설정**
   - 테이블 이름: `Reports`
   - 파티션 키: `ReportId`, 형식: `String`
4. **API Gateway 설정**
   - HTTP API를 통해 POST만 설정 및 람다와 연결
## 후기
진짜 잘 적은게 맞는지 모르겠음
