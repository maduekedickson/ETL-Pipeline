import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "riteclick-super-secret-key-change-me")
    FLASK_ENV = os.getenv("FLASK_ENV", "production")
    DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "t")
    PORT = int(os.getenv("PORT", 5050))

    # AWS Settings
    AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
    DYNAMODB_USERS_TABLE = os.getenv("DYNAMODB_USERS_TABLE", "RiteClick_Users")
    SOURCE_S3_BUCKET = os.getenv("SOURCE_S3_BUCKET", "riteclick-etl-source-data")
    TARGET_S3_BUCKET = os.getenv("TARGET_S3_BUCKET", "riteclick-etl-processed-data")
    GLUE_JOB_NAME = os.getenv("GLUE_JOB_NAME", "riteclick-csv-to-json-job")
    SNS_TOPIC_ARN = os.getenv("SNS_TOPIC_ARN", "")

    # Security Cookies
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("FLASK_ENV") == "production"
    MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100 MB max file upload
