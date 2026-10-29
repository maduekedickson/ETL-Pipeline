import datetime
import json
import logging
import os
import boto3
from botocore.exceptions import ClientError, NoCredentialsError, EndpointConnectionError
from flask import current_app

logger = logging.getLogger(__name__)

# Local development fallback storage
LOCAL_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data_local")
LOCAL_USERS_FILE = os.path.join(LOCAL_DATA_DIR, "users.json")
LOCAL_SOURCE_DIR = os.path.join(LOCAL_DATA_DIR, "source_s3")
LOCAL_TARGET_DIR = os.path.join(LOCAL_DATA_DIR, "target_s3")

def _ensure_local_dirs():
    os.makedirs(LOCAL_DATA_DIR, exist_ok=True)
    os.makedirs(LOCAL_SOURCE_DIR, exist_ok=True)
    os.makedirs(LOCAL_TARGET_DIR, exist_ok=True)
    if not os.path.exists(LOCAL_USERS_FILE):
        with open(LOCAL_USERS_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)

def _load_local_users():
    _ensure_local_dirs()
    try:
        with open(LOCAL_USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def _save_local_users(users):
    _ensure_local_dirs()
    with open(LOCAL_USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2)

def get_boto3_client(service_name: str):
    """
    Get a boto3 client configured with the application AWS region.
    When running on EC2 with an attached IAM role, credentials are automatically
    discovered from the instance metadata.
    """
    region = current_app.config.get("AWS_REGION", "us-east-1")
    return boto3.client(service_name, region_name=region)

def get_boto3_resource(service_name: str):
    """Get a boto3 resource configured with the application AWS region."""
    region = current_app.config.get("AWS_REGION", "us-east-1")
    return boto3.resource(service_name, region_name=region)

# ============================================================================
# DynamoDB User Operations
# ============================================================================

def get_users_table():
    """Returns the DynamoDB Table resource."""
    table_name = current_app.config["DYNAMODB_USERS_TABLE"]
    dynamodb = get_boto3_resource("dynamodb")
    return dynamodb.Table(table_name)

def get_user_by_email(email: str):
    """Fetch user item by email (supports both simple PK and composite HASH+RANGE)."""
    clean_email = email.strip().lower()
    try:
        from boto3.dynamodb.conditions import Key
        table = get_users_table()
        # Query handles tables with both Partition Key and Sort Key
        response = table.query(
            KeyConditionExpression=Key("email").eq(clean_email)
        )
        items = response.get("Items", [])
        if items:
            return items[0]
        
        # Fallback to get_item for simple single-key tables
        try:
            res = table.get_item(Key={"email": clean_email})
            if res.get("Item"):
                return res["Item"]
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Error fetching user by email '{email}': {e}")

    # Fallback to local store
    for u in _load_local_users():
        if u["email"] == clean_email:
            return u
    return None

def get_user_by_username(username: str):
    """Fetch user item by querying username attribute."""
    clean_username = username.strip()
    try:
        from boto3.dynamodb.conditions import Attr
        table = get_users_table()
        # Scan table for username attribute
        response = table.scan(
            FilterExpression=Attr("username").eq(clean_username)
        )
        items = response.get("Items", [])
        if items:
            return items[0]
        
        # Case-insensitive fallback
        scan_all = table.scan()
        for item in scan_all.get("Items", []):
            if item.get("username", "").lower() == clean_username.lower():
                return item
    except Exception as e:
        logger.error(f"Error fetching user by username '{username}': {e}")

    # Fallback to local store
    for u in _load_local_users():
        if u["username"].lower() == clean_username.lower():
            return u
    return None

def create_user(username: str, email: str, password_hash: str):
    """Create a new user entry in DynamoDB or local fallback."""
    clean_email = email.strip().lower()
    clean_username = username.strip()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    item = {
        "email": clean_email,
        "username": clean_username,
        "password_hash": password_hash,
        "created_at": now,
        "last_login": now,
        "role": "user"
    }

    try:
        table = get_users_table()
        table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(email)"
        )
        return True, "User registered successfully in DynamoDB."
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "ConditionalCheckFailedException":
            return False, "An account with this email address already exists."
        logger.warning(f"DynamoDB PutItem error: {e}. Falling back to local store.")
    except (NoCredentialsError, EndpointConnectionError) as e:
        logger.warning(f"AWS credentials not present locally ({e}). Using local store.")
    except Exception as e:
        logger.warning(f"Unexpected error: {e}. Using local store.")

    # Local storage fallback
    users = _load_local_users()
    for u in users:
        if u["email"] == clean_email:
            return False, "An account with this email address already exists."
        if u["username"].lower() == clean_username.lower():
            return False, "This username is already taken. Please choose another one."
    users.append(item)
    _save_local_users(users)
    return True, "User registered successfully."

def update_last_login(email: str):
    """Update last_login timestamp for user."""
    clean_email = email.strip().lower()
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    try:
        table = get_users_table()
        user = get_user_by_email(clean_email)
        if user and "username" in user:
            table.update_item(
                Key={"email": clean_email, "username": user["username"]},
                UpdateExpression="SET last_login = :now",
                ExpressionAttributeValues={":now": now}
            )
        else:
            table.update_item(
                Key={"email": clean_email},
                UpdateExpression="SET last_login = :now",
                ExpressionAttributeValues={":now": now}
            )
        return
    except Exception:
        pass

    users = _load_local_users()
    for u in users:
        if u["email"] == clean_email:
            u["last_login"] = now
            break
    _save_local_users(users)


# ============================================================================
# S3 File Operations
# ============================================================================

def upload_source_file(file_obj, filename: str, username: str):
    """
    Upload a CSV file to the Source S3 bucket.
    Key structure: uploads/{username}/{timestamp}_{filename}
    Also supports local mode: converts CSV to JSON automatically for testing!
    """
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    clean_filename = filename.replace(" ", "_")
    base_name = os.path.splitext(clean_filename)[0]
    s3_key = f"uploads/{username}/{timestamp}_{clean_filename}"

    file_bytes = file_obj.read()
    file_obj.seek(0)

    try:
        s3 = get_boto3_client("s3")
        bucket = current_app.config["SOURCE_S3_BUCKET"]
        s3.upload_fileobj(
            file_obj,
            bucket,
            s3_key,
            ExtraArgs={
                "ContentType": "text/csv",
                "Metadata": {
                    "uploaded_by": username,
                    "original_name": filename,
                    "uploaded_at": timestamp
                }
            }
        )
        return True, s3_key
    except (NoCredentialsError, EndpointConnectionError, ClientError) as e:
        logger.warning(f"S3 upload fallback to local storage: {e}")
        _ensure_local_dirs()

        # Save raw CSV locally
        user_source_dir = os.path.join(LOCAL_SOURCE_DIR, username)
        os.makedirs(user_source_dir, exist_ok=True)
        local_csv_path = os.path.join(user_source_dir, f"{timestamp}_{clean_filename}")
        with open(local_csv_path, "wb") as f:
            f.write(file_bytes)

        # In local testing mode, simulate the Glue CSV->JSON transformation immediately!
        import csv
        try:
            csv_text = file_bytes.decode("utf-8", errors="replace")
            reader = csv.DictReader(csv_text.splitlines())
            json_records = list(reader)

            user_target_dir = os.path.join(LOCAL_TARGET_DIR, "processed", username)
            os.makedirs(user_target_dir, exist_ok=True)
            local_json_path = os.path.join(user_target_dir, f"{timestamp}_{base_name}.json")
            with open(local_json_path, "w", encoding="utf-8") as f:
                json.dump(json_records, f, indent=2)
        except Exception as conv_err:
            logger.error(f"Local CSV conversion error: {conv_err}")

        return True, s3_key
    except Exception as e:
        logger.error(f"Unexpected S3 upload error: {e}")
        return False, str(e)

def list_target_json_files(prefix: str = "processed/"):
    """
    List processed JSON files in the Target S3 bucket or local fallback.
    Returns list of dictionaries containing file metadata.
    """
    files = []
    try:
        s3 = get_boto3_client("s3")
        bucket = current_app.config["TARGET_S3_BUCKET"]
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith("/") or obj["Size"] == 0:
                    continue
                if key.endswith(".json") or "/part-" in key or key.endswith(".txt"):
                    display_name = key.split("/")[-1]
                    files.append({
                        "key": key,
                        "filename": display_name,
                        "size": obj["Size"],
                        "size_formatted": format_file_size(obj["Size"]),
                        "last_modified": obj["LastModified"],
                        "last_modified_str": obj["LastModified"].strftime("%Y-%m-%d %H:%M:%S UTC")
                    })
        files.sort(key=lambda x: x["last_modified"], reverse=True)
        if files:
            return files
    except Exception:
        pass

    # Local fallback
    _ensure_local_dirs()
    for root, _, filenames in os.walk(LOCAL_TARGET_DIR):
        for fname in filenames:
            if fname.endswith(".json"):
                full_path = os.path.join(root, fname)
                rel_path = os.path.relpath(full_path, LOCAL_TARGET_DIR).replace("\\", "/")
                stat = os.stat(full_path)
                mtime = datetime.datetime.fromtimestamp(stat.st_mtime, datetime.timezone.utc)
                files.append({
                    "key": rel_path,
                    "filename": fname,
                    "size": stat.st_size,
                    "size_formatted": format_file_size(stat.st_size),
                    "last_modified": mtime,
                    "last_modified_str": mtime.strftime("%Y-%m-%d %H:%M:%S UTC")
                })
    files.sort(key=lambda x: x["last_modified"], reverse=True)
    return files

def get_target_json_content(file_key: str):
    """
    Download and parse JSON content from the Target S3 bucket or local fallback.
    """
    try:
        s3 = get_boto3_client("s3")
        bucket = current_app.config["TARGET_S3_BUCKET"]
        response = s3.get_object(Bucket=bucket, Key=file_key)
        raw_bytes = response["Body"].read()
        raw_text = raw_bytes.decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw_text)
            return True, parsed, raw_text
        except json.JSONDecodeError:
            lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
            parsed_list = [json.loads(line) for line in lines if line]
            if parsed_list:
                return True, parsed_list, json.dumps(parsed_list, indent=2)
            return True, {"raw_content": raw_text}, raw_text
    except Exception:
        pass

    # Local fallback
    local_file_path = os.path.join(LOCAL_TARGET_DIR, file_key.replace("/", os.sep))
    if os.path.exists(local_file_path):
        try:
            with open(local_file_path, "r", encoding="utf-8") as f:
                raw_text = f.read()
            parsed = json.loads(raw_text)
            return True, parsed, raw_text
        except Exception as e:
            return False, None, str(e)

    return False, None, "File not found."

def generate_presigned_download_url(file_key: str, expiration: int = 3600):
    """Generate a presigned URL to download the processed file directly."""
    try:
        s3 = get_boto3_client("s3")
        bucket = current_app.config["TARGET_S3_BUCKET"]
        url = s3.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": bucket,
                "Key": file_key,
                "ResponseContentDisposition": f'attachment; filename="{file_key.split("/")[-1]}"'
            },
            ExpiresIn=expiration
        )
        return url
    except Exception:
        return None


# ============================================================================
# AWS Glue Job Status Monitoring
# ============================================================================

def get_recent_glue_runs(job_name: str, max_results: int = 5):
    """Fetch status of recent AWS Glue Job runs."""
    glue = get_boto3_client("glue")
    try:
        response = glue.get_job_runs(JobName=job_name, MaxResults=max_results)
        runs = []
        for run in response.get("JobRuns", []):
            runs.append({
                "id": run.get("Id"),
                "status": run.get("JobRunState"),
                "started_on": run.get("StartedOn"),
                "completed_on": run.get("CompletedOn"),
                "execution_time": run.get("ExecutionTime", 0),
                "error_message": run.get("ErrorMessage")
            })
        return runs
    except Exception as e:
        logger.debug(f"Could not fetch Glue job runs for {job_name}: {e}")
        return []

def format_file_size(size_bytes: int) -> str:
    """Format bytes into human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
