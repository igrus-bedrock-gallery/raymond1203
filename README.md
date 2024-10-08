# raymond1203
Infra
# 설정사항
1. S3 설정
    Notification 사용
    버킷 정책 추가
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
2. lambda IAM 설정
   본인은 FullAccess로 S3, DynamoDB 설정해놓음
3. DynamoDB 설정
   테이블 이름: Reports
   파티션 키: ReportId
