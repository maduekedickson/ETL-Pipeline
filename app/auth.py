import functools
import bcrypt
from flask import session, redirect, url_for, flash, request

def hash_password(plain_password: str) -> str:
    """Hash password using bcrypt."""
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), salt)
    return hashed.decode("utf-8")

def check_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plain password against bcrypt hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8")
        )
    except Exception:
        return False

def login_required(view):
    """Decorator to protect routes requiring authenticated session."""
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if not session.get("user"):
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("main.login", next=request.url))
        return view(**kwargs)
    return wrapped_view

def get_current_user():
    """Retrieve current logged in user from session."""
    return session.get("user")
