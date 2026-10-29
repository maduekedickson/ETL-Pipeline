import sys
import boto3
from urllib.parse import urlparse
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql import SparkSession

# Initialize Glue context and Spark session
args = getResolvedOptions(sys.argv, [
    "JOB_NAME",
    "SOURCE_S3_PATH",
    "TARGET_S3_PATH"
])

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args["JOB_NAME"], args)

source_s3_path = args["SOURCE_S3_PATH"]
target_s3_path = args["TARGET_S3_PATH"]

print(f"Starting Glue ETL Job: {args['JOB_NAME']}")
print(f"Reading CSV from: {source_s3_path}")
print(f"Output Target: {target_s3_path}")

# Read CSV with Spark DataFrame
df = spark.read \
    .option("header", "true") \
    .option("inferSchema", "true") \
    .option("multiLine", "true") \
    .option("quote", "\"") \
    .option("escape", "\"") \
    .csv(source_s3_path)

row_count = df.count()
print(f"Successfully loaded CSV with {row_count} rows and {len(df.columns)} columns.")
print("Schema:")
df.printSchema()

# Write DataFrame as single cohesive JSON file to target destination
temp_target_path = target_s3_path.rstrip("/") + "_temp/"

# Coalesce to 1 to produce a single consolidated JSON output file
df.coalesce(1).write \
    .mode("overwrite") \
    .json(temp_target_path)

print("Temporary JSON files written. Consolidating into final destination...")

# Helper to rename part-00000 to a clean filename in the target location
def consolidate_part_file(temp_s3_uri, final_s3_uri):
    parsed_temp = urlparse(temp_s3_uri)
    parsed_target = urlparse(final_s3_uri)
    
    bucket = parsed_temp.netloc
    temp_prefix = parsed_temp.path.lstrip("/")
    target_prefix = parsed_target.path.lstrip("/")

    s3 = boto3.client("s3")
    response = s3.list_objects_v2(Bucket=bucket, Prefix=temp_prefix)

    part_key = None
    for obj in response.get("Contents", []):
        key = obj["Key"]
        if "/part-" in key and key.endswith(".json"):
            part_key = key
            break

    if part_key:
        # Determine final key name
        base_name = temp_prefix.rstrip("/").split("/")[-1].replace("_temp", "")
        final_key = f"{target_prefix.rstrip('/')}/{base_name}.json"
        
        print(f"Copying {part_key} to {final_key} in bucket {bucket}")
        s3.copy_object(
            Bucket=bucket,
            CopySource={"Bucket": bucket, "Key": part_key},
            Key=final_key
        )

        # Cleanup temp directory
        for obj in response.get("Contents", []):
            s3.delete_object(Bucket=bucket, Key=obj["Key"])
        print(f"Cleanup finished. Final JSON dataset ready at: s3://{bucket}/{final_key}")
    else:
        print("No part-* file found; keeping standard Spark partitioned output.")

try:
    consolidate_part_file(temp_target_path, target_s3_path)
except Exception as e:
    print(f"Consolidation note: {e}. Writing standard Spark format to target.")
    df.coalesce(1).write.mode("overwrite").json(target_s3_path)

job.commit()
print("Glue Job successfully completed!")
