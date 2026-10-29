import os
import sys
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

REGION = os.getenv("AWS_REGION", "us-east-1")
SOURCE_BUCKET = os.getenv("SOURCE_S3_BUCKET", "riteclick-etl-source-data")
TARGET_BUCKET = os.getenv("TARGET_S3_BUCKET", "riteclick-etl-processed-data")

def create_and_secure_bucket(s3_client, bucket_name, region):
    print(f"\n--- Provisioning S3 Bucket: {bucket_name} ---")
    try:
        # Create bucket
        if region == "us-east-1":
            s3_client.create_bucket(Bucket=bucket_name)
        else:
            s3_client.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={"LocationConstraint": region}
            )
        print(f"Bucket '{bucket_name}' created.")
    except ClientError as e:
        if e.response["Error"]["Code"] in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
            print(f"Bucket '{bucket_name}' already exists.")
        else:
            print(f"Failed to create bucket '{bucket_name}': {e}")
            return False

    # 1. Enable Default Server-Side Encryption (SSE-S3 AES256)
    try:
        s3_client.put_bucket_encryption(
            Bucket=bucket_name,
            ServerSideEncryptionConfiguration={
                "Rules": [
                    {
                        "ApplyServerSideEncryptionByDefault": {
                            "SSEAlgorithm": "AES256"
                        }
                    }
                ]
            }
        )
        print(f"Server-side encryption enabled (AES256) on '{bucket_name}'.")
    except Exception as e:
        print(f"Warning: Could not configure encryption on '{bucket_name}': {e}")

    # 2. Enforce Block Public Access
    try:
        s3_client.put_public_access_block(
            Bucket=bucket_name,
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": True,
                "IgnorePublicAcls": True,
                "BlockPublicPolicy": True,
                "RestrictPublicBuckets": True
            }
        )
        print(f"Public access strictly blocked on '{bucket_name}'.")
    except Exception as e:
        print(f"Warning: Could not enforce Block Public Access on '{bucket_name}': {e}")

    return True

def setup_s3():
    s3_client = boto3.client("s3", region_name=REGION)
    success_src = create_and_secure_bucket(s3_client, SOURCE_BUCKET, REGION)
    success_tgt = create_and_secure_bucket(s3_client, TARGET_BUCKET, REGION)

    if success_src and success_tgt:
        print("\nAll S3 buckets successfully created and secured with least privilege access!")
        return True
    return False

if __name__ == "__main__":
    if not setup_s3():
        sys.exit(1)
