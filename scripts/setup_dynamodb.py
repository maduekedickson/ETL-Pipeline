import os
import sys
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

TABLE_NAME = os.getenv("DYNAMODB_USERS_TABLE", "RiteClick_Users")
REGION = os.getenv("AWS_REGION", "us-east-1")

def create_users_table():
    """Create DynamoDB Users table with email as Partition Key and GSI on username."""
    dynamodb = boto3.client("dynamodb", region_name=REGION)
    print(f"Connecting to DynamoDB in region: {REGION}")

    try:
        print(f"Checking if table '{TABLE_NAME}' already exists...")
        response = dynamodb.describe_table(TableName=TABLE_NAME)
        print(f"Table '{TABLE_NAME}' already exists. Status: {response['Table']['TableStatus']}")
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] != "ResourceNotFoundException":
            print(f"Unexpected error: {e}")
            return False

    print(f"Table '{TABLE_NAME}' does not exist. Creating now...")

    try:
        table = dynamodb.create_table(
            TableName=TABLE_NAME,
            KeySchema=[
                {"AttributeName": "email", "KeyType": "HASH"}  # Partition key
            ],
            AttributeDefinitions=[
                {"AttributeName": "email", "AttributeType": "S"},
                {"AttributeName": "username", "AttributeType": "S"}
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "UsernameIndex",
                    "KeySchema": [
                        {"AttributeName": "username", "KeyType": "HASH"}
                    ],
                    "Projection": {
                        "ProjectionType": "ALL"
                    }
                }
            ],
            BillingMode="PAY_PER_REQUEST"  # On-demand serverless pricing
        )

        print(f"Table creation requested. Waiting for ACTIVE status...")
        waiter = dynamodb.get_waiter("table_exists")
        waiter.wait(TableName=TABLE_NAME)
        print(f"Table '{TABLE_NAME}' created and ACTIVE successfully!")
        return True
    except Exception as e:
        print(f"Failed to create table: {e}")
        return False

if __name__ == "__main__":
    success = create_users_table()
    if not success:
        sys.exit(1)
