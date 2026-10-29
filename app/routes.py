import io
import re
from flask import (
    Blueprint, render_template, request, redirect,
    url_for, flash, session, current_app, jsonify, send_file, Response
)
from app.auth import hash_password, check_password, login_required, get_current_user
from app.aws_services import (
    get_user_by_email, get_user_by_username, create_user,
    update_last_login, upload_source_file, list_target_json_files,
    get_target_json_content, generate_presigned_download_url,
    get_recent_glue_runs
)

main_bp = Blueprint("main", __name__)

EMAIL_REGEX = re.compile(r"^[\w\.-]+@[\w\.-]+\.\w+$")

# ============================================================================
# Public Pages
# ============================================================================

@main_bp.route("/")
def index():
    """RiteClick Landing Page."""
    user = get_current_user()
    return render_template("index.html", user=user)

@main_bp.route("/signup", methods=["GET", "POST"])
def signup():
    """User Registration Route."""
    if get_current_user():
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        # Form Validations
        if not username or len(username) < 3:
            flash("Username must be at least 3 characters long.", "danger")
            return render_template("signup.html", username=username, email=email)

        if not email or not EMAIL_REGEX.match(email):
            flash("Please enter a valid email address.", "danger")
            return render_template("signup.html", username=username, email=email)

        if len(password) < 8:
            flash("Password must be at least 8 characters long.", "danger")
            return render_template("signup.html", username=username, email=email)

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return render_template("signup.html", username=username, email=email)

        # Check existing user
        if get_user_by_email(email):
            flash("An account with this email already exists. Please log in.", "warning")
            return redirect(url_for("main.login"))

        if get_user_by_username(username):
            flash("This username is already taken. Please choose another one.", "warning")
            return render_template("signup.html", username="", email=email)

        # Hash with bcrypt
        password_hash = hash_password(password)

        # Store in DynamoDB
        success, message = create_user(username, email, password_hash)
        if success:
            flash("Account created successfully! You can now log in.", "success")
            return redirect(url_for("main.login"))
        else:
            flash(f"Registration failed: {message}", "danger")
            return render_template("signup.html", username=username, email=email)

    return render_template("signup.html")

@main_bp.route("/login", methods=["GET", "POST"])
def login():
    """User Login Route."""
    if get_current_user():
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        login_identifier = request.form.get("identifier", "").strip()
        password = request.form.get("password", "")

        if not login_identifier or not password:
            flash("Please fill in both identifier and password.", "danger")
            return render_template("login.html", identifier=login_identifier)

        # Check by email first, then by username
        user = None
        if EMAIL_REGEX.match(login_identifier):
            user = get_user_by_email(login_identifier)
        else:
            user = get_user_by_username(login_identifier)

        if not user or not check_password(password, user.get("password_hash", "")):
            flash("Invalid email/username or password.", "danger")
            return render_template("login.html", identifier=login_identifier)

        # Set session
        session["user"] = {
            "username": user["username"],
            "email": user["email"],
            "role": user.get("role", "user")
        }
        update_last_login(user["email"])

        flash(f"Welcome back, {user['username']}!", "success")
        next_url = request.args.get("next")
        if next_url and next_url.startswith("/"):
            return redirect(next_url)
        return redirect(url_for("main.dashboard"))

    return render_template("login.html")

@main_bp.route("/logout")
def logout():
    """Clear session and log out."""
    session.pop("user", None)
    flash("You have been successfully logged out.", "info")
    return redirect(url_for("main.login"))

# ============================================================================
# Authenticated Application Routes
# ============================================================================

@main_bp.route("/dashboard")
@login_required
def dashboard():
    """User Overview Dashboard."""
    user = get_current_user()
    processed_files = list_target_json_files()
    glue_runs = get_recent_glue_runs(current_app.config["GLUE_JOB_NAME"])

    return render_template(
        "dashboard.html",
        user=user,
        recent_files=processed_files[:5],
        total_files=len(processed_files),
        glue_runs=glue_runs,
        config=current_app.config
    )

@main_bp.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    """File Upload Route for authenticated users."""
    user = get_current_user()

    if request.method == "POST":
        if "file" not in request.files:
            flash("No file part in the request.", "danger")
            return redirect(request.url)

        file = request.files["file"]

        if file.filename == "":
            flash("No file selected for upload.", "warning")
            return redirect(request.url)

        if not file.filename.lower().endswith(".csv"):
            flash("Invalid file format. Only CSV (.csv) files are supported for ETL processing.", "danger")
            return redirect(request.url)

        # Upload to Source S3 bucket
        success, result = upload_source_file(file.stream, file.filename, user["username"])
        if success:
            flash(
                f"File '{file.filename}' uploaded successfully to S3 bucket '{current_app.config['SOURCE_S3_BUCKET']}'! "
                f"S3 Event has triggered Lambda, which started the AWS Glue CSV→JSON job and sent an SNS alert.",
                "success"
            )
            return redirect(url_for("main.processed"))
        else:
            flash(f"Upload failed: {result}", "danger")
            return redirect(request.url)

    return render_template("upload.html", user=user, bucket=current_app.config["SOURCE_S3_BUCKET"])

@main_bp.route("/processed")
@login_required
def processed():
    """Browse converted JSON files in Target S3 bucket."""
    user = get_current_user()
    files = list_target_json_files()
    return render_template(
        "processed.html",
        user=user,
        files=files,
        target_bucket=current_app.config["TARGET_S3_BUCKET"]
    )

@main_bp.route("/view-json/<path:file_key>")
@login_required
def view_json(file_key):
    """Interactive JSON viewer and inspector."""
    user = get_current_user()
    success, parsed_data, raw_text = get_target_json_content(file_key)

    if not success:
        flash(f"Unable to read JSON object: {raw_text}", "danger")
        return redirect(url_for("main.processed"))

    record_count = 0
    if isinstance(parsed_data, list):
        record_count = len(parsed_data)
    elif isinstance(parsed_data, dict):
        record_count = 1

    return render_template(
        "view_json.html",
        user=user,
        file_key=file_key,
        filename=file_key.split("/")[-1],
        parsed_data=parsed_data,
        raw_text=raw_text,
        record_count=record_count
    )

@main_bp.route("/download-json/<path:file_key>")
@login_required
def download_json(file_key):
    """Direct file download from Target S3 bucket."""
    # Method 1: Try presigned URL redirect for optimal S3 streaming
    presigned_url = generate_presigned_download_url(file_key)
    if presigned_url:
        return redirect(presigned_url)

    # Method 2: Fallback stream directly through Flask
    success, _, raw_text = get_target_json_content(file_key)
    if not success:
        flash("File download failed.", "danger")
        return redirect(url_for("main.processed"))

    filename = file_key.split("/")[-1]
    return Response(
        raw_text,
        mimetype="application/json",
        headers={"Content-Disposition": f"attachment;filename={filename}"}
    )

@main_bp.route("/api/health")
def health_check():
    """API health check."""
    return jsonify({
        "status": "healthy",
        "service": "RiteClick ETL Portal",
        "region": current_app.config.get("AWS_REGION")
    })
