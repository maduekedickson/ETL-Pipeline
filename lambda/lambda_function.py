import json
import os
import urllib.parse
import boto3
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

glue_client = boto3.client("glue")
sns_client = boto3.client("sns")

GLUE_JOB_NAME = os.environ.get("GLUE_JOB_NAME", "riteclick-csv-to-json-job")
TARGET_S3_BUCKET = os.environ.get("TARGET_S3_BUCKET", "riteclick-etl-processed-data")
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "")

def lambda_handler(event, context):
    """
    AWS Lambda function triggered by S3 ObjectCreated event on the Source S3 Bucket.
    1. Extracts uploaded CSV object key and bucket name.
    2. Invokes AWS Glue PySpark job to transform CSV -> JSON.
    3. Publishes notification to Amazon SNS Topic.
    """
    logger.info("Received S3 event: %s", json.dumps(event))

    results = []

    for record in event.get("Records", []):
        try:
            source_bucket = record["s3"]["bucket"]["name"]
            # S3 keys in events are URL encoded (e.g. spaces become + or %20)
            raw_key = record["s3"]["object"]["key"]
            source_key = urllib.parse.unquote_plus(raw_key)

            file_size = record["s3"]["object"].get("size", 0)
            event_time = record.get("eventTime", "N/A")

            logger.info(f"Processing S3 event for bucket: {source_bucket}, key: {source_key}")

            # Verify it's a CSV file
            if not source_key.lower().endswith(".csv"):
                logger.info(f"Skipping non-CSV file: {source_key}")
                continue

            # Build Target S3 Output Path
            # e.g., uploads/username/20261014_data.csv -> processed/username/20261014_data/
            filename_with_ext = source_key.split("/")[-1]
            base_filename = os.path.splitext(filename_with_ext)[0]
            
            # Preserve user prefix if present
            path_parts = source_key.split("/")
            if len(path_parts) > 2 and path_parts[0] == "uploads":
                user_subfolder = path_parts[1]
                target_key = f"processed/{user_subfolder}/{base_filename}.json"
                target_s3_path = f"s3://{TARGET_S3_BUCKET}/processed/{user_subfolder}/{base_filename}/"
            else:
                target_key = f"processed/{base_filename}.json"
                target_s3_path = f"s3://{TARGET_S3_BUCKET}/processed/{base_filename}/"

            source_s3_path = f"s3://{source_bucket}/{source_key}"

            # 1. Trigger AWS Glue Job
            logger.info(f"Starting Glue Job '{GLUE_JOB_NAME}' with Source: {source_s3_path}, Target: {target_s3_path}")
            
            glue_response = glue_client.start_job_run(
                JobName=GLUE_JOB_NAME,
                Arguments={
                    "--SOURCE_S3_PATH": source_s3_path,
                    "--TARGET_S3_PATH": target_s3_path,
                    "--TARGET_FILE_NAME": f"{base_filename}.json"
                }
            )
            job_run_id = glue_response.get("JobRunId")
            logger.info(f"AWS Glue Job Run initiated successfully: {job_run_id}")

            # 2. Publish SNS Notification
            sns_message_id = None
            if SNS_TOPIC_ARN:
                email_subject = f"[RiteClick ETL] New Ingestion: {filename_with_ext}"
                email_body = (
                    f"RiteClick Automated ETL Pipeline Alert\n"
                    f"====================================\n\n"
                    f"A new CSV dataset has been uploaded and ETL processing has started.\n\n"
                    f"• File Name: {filename_with_ext}\n"
                    f"• File Size: {file_size} bytes\n"
                    f"• Uploaded At: {event_time}\n"
                    f"• Source S3: {source_s3_path}\n"
                    f"• Target S3 Destination: {target_s3_path}\n"
                    f"• AWS Glue Job Name: {GLUE_JOB_NAME}\n"
                    f"• Glue Job Run ID: {job_run_id}\n\n"
                    f"You will be able to view and download the converted JSON file on the "
                    f"RiteClick web dashboard once the Glue PySpark job finishes.\n\n"
                    f"--\nRiteClick Cloud ETL Automated Service"
                )

                try:
                    sns_res = sns_client.publish(
                        TopicArn=SNS_TOPIC_ARN,
                        Subject=email_subject[:100],  # SNS subject max 100 chars
                        Message=email_body
                    )
                    sns_message_id = sns_res.get("MessageId")
                    logger.info(f"SNS notification published successfully: {sns_message_id}")
                except Exception as sns_err:
                    logger.error(f"Failed to publish SNS notification: {sns_err}")

            results.append({
                "status": "SUCCESS",
                "source_file": source_key,
                "job_run_id": job_run_id,
                "sns_message_id": sns_message_id
            })

        except Exception as e:
            logger.error(f"Error processing record: {e}", exc_info=True)
            results.append({
                "status": "FAILED",
                "error": str(e)
            })

    return {
        "statusCode": 200,
        "body": json.dumps({"processed_records": len(results), "results": results})
    }
