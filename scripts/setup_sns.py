import os
import sys
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

REGION = os.getenv("AWS_REGION", "us-east-1")
TOPIC_NAME = "riteclick-etl-notifications"

def setup_sns(email_subscriber=None):
    sns = boto3.client("sns", region_name=REGION)
    print(f"Provisioning SNS Topic '{TOPIC_NAME}' in {REGION}...")

    try:
        response = sns.create_topic(
            Name=TOPIC_NAME,
            Attributes={
                "DisplayName": "RiteClick ETL Alerts"
            }
        )
        topic_arn = response["TopicArn"]
        print(f"SNS Topic created successfully!")
        print(f"SNS_TOPIC_ARN={topic_arn}")

        if email_subscriber:
            print(f"Subscribing email '{email_subscriber}' to topic...")
            sub_res = sns.subscribe(
                TopicArn=topic_arn,
                Protocol="email",
                Endpoint=email_subscriber
            )
            print(f"Subscription pending confirmation. Please check inbox for confirmation email.")

        print("\n--> Update your .env and Lambda environment variables with this ARN:")
        print(f"SNS_TOPIC_ARN={topic_arn}")
        return topic_arn
    except ClientError as e:
        print(f"Failed to create SNS topic: {e}")
        return None

if __name__ == "__main__":
    email_arg = sys.argv[1] if len(sys.argv) > 1 else None
    setup_sns(email_arg)
