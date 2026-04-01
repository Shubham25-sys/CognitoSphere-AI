from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect, CSRFError
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from openai import OpenAI, AuthenticationError, RateLimitError, APIConnectionError, APIStatusError
from dotenv import load_dotenv
from datetime import timedelta, datetime, timezone
import os
import re
import random
import string

load_dotenv()

app = Flask(__name__)

# ── Security Config ────────────────────────────────────────
app.secret_key = os.environ.get("SECRET_KEY", "fallback-change-in-production")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///users.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 280,
    "pool_pre_ping": True,
}
app.config["WTF_CSRF_TIME_LIMIT"] = 3600
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=24)
app.config["SESSION_COOKIE_SECURE"] = False   # Set True when using HTTPS

# ── Mail Config (Gmail SMTP) ───────────────────────────────
app.config["MAIL_SERVER"]         = "smtp.gmail.com"
app.config["MAIL_PORT"]           = 587
app.config["MAIL_USE_TLS"]        = True
app.config["MAIL_USERNAME"]       = os.environ.get("MAIL_USERNAME", "")
app.config["MAIL_PASSWORD"]       = os.environ.get("MAIL_PASSWORD", "")
app.config["MAIL_DEFAULT_SENDER"] = os.environ.get("MAIL_USERNAME", "")

# ── Extensions ─────────────────────────────────────────────
db      = SQLAlchemy(app)
mail    = Mail(app)
csrf    = CSRFProtect(app)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["300 per day", "60 per hour"],
    storage_uri="memory://",
)

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to access CognitoSphere AI."

# ── OpenAI ─────────────────────────────────────────────────
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))

# Account lockout tracker  {ip: {"count": n, "locked_until": datetime}}
_failed_logins: dict = {}
MAX_ATTEMPTS    = 5
LOCKOUT_MINUTES = 15


# ── Helpers ────────────────────────────────────────────────
def is_locked_out(ip: str) -> tuple[bool, int]:
    record = _failed_logins.get(ip)
    if not record:
        return False, 0
    if record["locked_until"] and datetime.now(timezone.utc) < record["locked_until"]:
        remaining = int((record["locked_until"] - datetime.now(timezone.utc)).total_seconds())
        return True, remaining
    return False, 0

def record_failed_login(ip: str):
    record = _failed_logins.setdefault(ip, {"count": 0, "locked_until": None})
    record["count"] += 1
    if record["count"] >= MAX_ATTEMPTS:
        record["locked_until"] = datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES)

def clear_failed_logins(ip: str):
    _failed_logins.pop(ip, None)

# OTP store: {email: {"otp": str, "expires": datetime, "attempts": int}}
_otp_store: dict      = {}
OTP_EXPIRY_MINUTES    = 10
MAX_OTP_ATTEMPTS      = 3

def generate_otp() -> str:
    return "".join(random.choices(string.digits, k=6))

def send_otp_email(to_email: str, username: str, otp: str):
    msg = Message(
        subject="CognitoSphere AI — Password Reset OTP",
        recipients=[to_email],
    )
    msg.html = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
                 background:#0d1117;color:#e6edf3;padding:40px 0;margin:0;">
      <div style="max-width:480px;margin:0 auto;background:#161b22;
                  border:1px solid #30363d;border-radius:12px;padding:36px;">
        <div style="text-align:center;margin-bottom:24px;">
          <div style="font-size:48px;">🤖</div>
          <h1 style="font-size:20px;font-weight:700;color:#e6edf3;margin:8px 0 4px;">
            CognitoSphere AI</h1>
          <p style="color:#8b949e;font-size:14px;margin:0;">Password Reset Request</p>
        </div>
        <p style="color:#e6edf3;font-size:15px;margin:0 0 8px;">
          Hi <strong>{username}</strong>,</p>
        <p style="color:#8b949e;font-size:14px;margin:0 0 20px;">
          Use the OTP below to reset your password.
          It expires in <strong style="color:#e6edf3;">{OTP_EXPIRY_MINUTES} minutes</strong>.</p>
        <div style="background:#21262d;border:1px solid #388bfd;border-radius:10px;
                    padding:24px;text-align:center;margin:0 0 20px;">
          <span style="font-size:40px;font-weight:700;letter-spacing:14px;
                       color:#58a6ff;font-family:monospace;">{otp}</span>
        </div>
        <p style="color:#8b949e;font-size:13px;margin:0 0 4px;">
          ⚠️ Never share this OTP with anyone.</p>
        <p style="color:#8b949e;font-size:13px;margin:0;">
          If you didn't request a password reset, ignore this email.</p>
        <hr style="border:none;border-top:1px solid #30363d;margin:24px 0;">
        <p style="color:#6e7681;font-size:12px;text-align:center;margin:0;">
          CognitoSphere AI · Powered by GPT-4o mini</p>
      </div>
    </body>
    </html>"""
    mail.send(msg)


def valid_username(username: str) -> bool:
    return bool(re.match(r"^[a-zA-Z0-9_]{3,30}$", username))

def valid_email(email: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email))

def strong_password(password: str) -> str | None:
    if len(password) < 8:
        return "Password must be at least 8 characters."
    if not re.search(r"[A-Z]", password):
        return "Password must contain at least one uppercase letter."
    if not re.search(r"[0-9]", password):
        return "Password must contain at least one number."
    return None


# ── Security Headers ───────────────────────────────────────
@app.after_request
def set_security_headers(response):
    response.headers["X-Content-Type-Options"]  = "nosniff"
    response.headers["X-Frame-Options"]          = "DENY"
    response.headers["X-XSS-Protection"]         = "1; mode=block"
    response.headers["Referrer-Policy"]           = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"]        = "geolocation=(), microphone=(), camera=()"
    response.headers["Cache-Control"]             = "no-store, no-cache, must-revalidate"
    response.headers["Content-Security-Policy"]   = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
        "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
        "font-src 'self' https://cdnjs.cloudflare.com; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "frame-ancestors 'none';"
    )
    return response


# ── CSRF Error Handler ─────────────────────────────────────
@app.errorhandler(CSRFError)
def csrf_error(e):
    flash("Session expired. Please try again.", "error")
    return redirect(request.referrer or url_for("login"))

# ── Rate Limit Error Handler ───────────────────────────────
@app.errorhandler(429)
def rate_limit_error(_):
    flash("Too many requests. Please wait a moment and try again.", "error")
    return redirect(request.referrer or url_for("login"))


# ── Models ─────────────────────────────────────────────────
class User(UserMixin, db.Model):
    id       = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(30), unique=True, nullable=False)
    email    = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False)
    sessions = db.relationship("ChatSession", backref="user", lazy=True,
                                cascade="all, delete-orphan")
    queries  = db.relationship("UserQuery", backref="user", lazy=True,
                                cascade="all, delete-orphan")

class UserQuery(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    subject    = db.Column(db.String(100), nullable=False)
    message    = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

class ChatSession(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    title      = db.Column(db.String(100), default="New Chat")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    messages   = db.relationship("ChatMessage", backref="session", lazy=True,
                                  cascade="all, delete-orphan", order_by="ChatMessage.id")

class ChatMessage(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("chat_session.id"), nullable=False)
    role       = db.Column(db.String(10), nullable=False)   # "user" | "assistant"
    content    = db.Column(db.Text, nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ── Auth Routes ────────────────────────────────────────────
@app.route("/register", methods=["GET", "POST"])
@limiter.limit("10 per hour")
def register():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm  = request.form.get("confirm_password", "")

        if not valid_username(username):
            flash("Username must be 3–30 characters (letters, numbers, underscores only).", "error")
            return render_template("register.html")

        if not valid_email(email):
            flash("Please enter a valid email address.", "error")
            return render_template("register.html")

        pw_error = strong_password(password)
        if pw_error:
            flash(pw_error, "error")
            return render_template("register.html")

        if password != confirm:
            flash("Passwords do not match.", "error")
            return render_template("register.html")

        if User.query.filter_by(username=username).first():
            flash("Username already taken.", "error")
            return render_template("register.html")

        if User.query.filter_by(email=email).first():
            flash("Email already registered.", "error")
            return render_template("register.html")

        hashed = generate_password_hash(password, method="pbkdf2:sha256", salt_length=16)
        user = User(username=username, email=email, password=hashed)
        db.session.add(user)
        db.session.commit()
        flash("Account created! Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("20 per hour")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        ip = get_remote_address()
        locked, seconds = is_locked_out(ip)
        if locked:
            mins = max(1, seconds // 60)
            flash(f"Too many failed attempts. Try again in {mins} minute(s).", "error")
            return render_template("login.html")

        email    = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        remember = request.form.get("remember") == "on"

        user = User.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.password, password):
            record_failed_login(ip)
            remaining = MAX_ATTEMPTS - _failed_logins.get(ip, {}).get("count", 0)
            if remaining > 0:
                flash(f"Invalid email or password. {remaining} attempt(s) remaining.", "error")
            else:
                flash(f"Account locked for {LOCKOUT_MINUTES} minutes due to too many failed attempts.", "error")
            return render_template("login.html")

        clear_failed_logins(ip)
        login_user(user, remember=remember)
        next_page = request.args.get("next", "")
        if next_page and not next_page.startswith("/"):
            next_page = ""
        return redirect(next_page or url_for("index"))

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


# ── Forgot Password Routes ────────────────────────────────
@app.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("10 per hour")
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()

        if not valid_email(email):
            flash("Please enter a valid email address.", "error")
            return render_template("forgot_password.html")

        user = User.query.filter_by(email=email).first()
        # Always show success message to prevent email enumeration
        if user:
            otp = generate_otp()
            _otp_store[email] = {
                "otp_hash": generate_password_hash(otp, method="pbkdf2:sha256", salt_length=8),
                "expires":  datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRY_MINUTES),
                "attempts": 0,
            }
            try:
                send_otp_email(email, user.username, otp)
            except Exception as mail_err:
                app.logger.error("Mail send failed: %s", mail_err)
                flash(f"Failed to send OTP email: {mail_err}", "error")
                return render_template("forgot_password.html")

        session["fp_email"] = email
        flash(f"If {email} is registered, an OTP has been sent.", "info")
        return redirect(url_for("verify_otp"))

    return render_template("forgot_password.html")


@app.route("/verify-otp", methods=["GET", "POST"])
@limiter.limit("10 per hour")
def verify_otp():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    email = session.get("fp_email")
    if not email:
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        entered_otp = request.form.get("otp", "").strip()
        record      = _otp_store.get(email)

        if not record:
            flash("OTP expired or not requested. Please try again.", "error")
            return redirect(url_for("forgot_password"))

        if datetime.now(timezone.utc) > record["expires"]:
            _otp_store.pop(email, None)
            flash("OTP has expired. Please request a new one.", "error")
            return redirect(url_for("forgot_password"))

        if record["attempts"] >= MAX_OTP_ATTEMPTS:
            _otp_store.pop(email, None)
            flash("Too many wrong attempts. Please request a new OTP.", "error")
            return redirect(url_for("forgot_password"))

        if not check_password_hash(record["otp_hash"], entered_otp):
            record["attempts"] += 1
            left = MAX_OTP_ATTEMPTS - record["attempts"]
            flash(f"Incorrect OTP. {left} attempt(s) remaining.", "error")
            return render_template("verify_otp.html", masked_email=_mask_email(email))

        # OTP verified — allow password reset
        _otp_store.pop(email, None)
        session["fp_verified"] = True
        return redirect(url_for("reset_password_page"))

    return render_template("verify_otp.html", masked_email=_mask_email(email))


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password_page():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if not session.get("fp_verified") or not session.get("fp_email"):
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm  = request.form.get("confirm_password", "")

        pw_error = strong_password(password)
        if pw_error:
            flash(pw_error, "error")
            return render_template("reset_password.html")

        if password != confirm:
            flash("Passwords do not match.", "error")
            return render_template("reset_password.html")

        email = session.get("fp_email")
        user  = User.query.filter_by(email=email).first()
        if user:
            user.password = generate_password_hash(password, method="pbkdf2:sha256", salt_length=16)
            db.session.commit()

        session.pop("fp_email",     None)
        session.pop("fp_verified",  None)
        flash("Password reset successful! Please log in.", "success")
        return redirect(url_for("login"))

    return render_template("reset_password.html")


def _mask_email(email: str) -> str:
    """Show first 2 chars (or less) + *** + domain: sh***@gmail.com"""
    local, domain = email.split("@", 1)
    return local[:min(2, len(local))] + "***@" + domain


# ── Profile Routes ────────────────────────────────────────
@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        new_username = request.form.get("username", "").strip()

        if not valid_username(new_username):
            flash("Username must be 3–30 characters (letters, numbers, underscores only).", "error")
            return render_template("profile.html", user=current_user)

        if new_username == current_user.username:
            flash("That is already your username.", "info")
            return render_template("profile.html", user=current_user)

        if User.query.filter_by(username=new_username).first():
            flash("Username already taken.", "error")
            return render_template("profile.html", user=current_user)

        current_user.username = new_username
        db.session.commit()
        flash("Username updated successfully!", "success")
        return redirect(url_for("profile"))

    return render_template("profile.html", user=current_user)


@app.route("/profile/stats", methods=["GET"])
@login_required
def profile_stats():
    from datetime import date, timedelta

    uid = current_user.id

    total_sessions = ChatSession.query.filter_by(user_id=uid).count()

    total_messages = (ChatMessage.query
                      .join(ChatSession)
                      .filter(ChatSession.user_id == uid,
                              ChatMessage.role == "user")
                      .count())

    total_ai = (ChatMessage.query
                .join(ChatSession)
                .filter(ChatSession.user_id == uid,
                        ChatMessage.role == "assistant")
                .count())

    # Sessions created per day — last 7 days
    today  = date.today()
    labels = []
    daily  = []
    for i in range(6, -1, -1):
        day   = today - timedelta(days=i)
        count = ChatSession.query.filter(
            ChatSession.user_id == uid,
            db.func.date(ChatSession.created_at) == day
        ).count()
        labels.append(day.strftime("%b %d"))
        daily.append(count)

    return jsonify({
        "total_sessions":    total_sessions,
        "total_messages":    total_messages,
        "total_ai":          total_ai,
        "chart_labels":      labels,
        "chart_daily":       daily,
    })


@app.route("/profile/query", methods=["POST"])
@login_required
@csrf.exempt
def submit_query():
    data    = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid request."}), 400

    subject = data.get("subject", "").strip()
    message = data.get("message", "").strip()

    if not subject:
        return jsonify({"error": "Subject is required."}), 400
    if not message:
        return jsonify({"error": "Message is required."}), 400
    if len(subject) > 100:
        return jsonify({"error": "Subject must be under 100 characters."}), 400
    if len(message) > 1000:
        return jsonify({"error": "Message must be under 1000 characters."}), 400

    q = UserQuery(user_id=current_user.id, subject=subject, message=message)
    db.session.add(q)
    db.session.commit()

    try:
        admin_email = app.config["MAIL_USERNAME"]
        msg = Message(
            subject=f"[CognitoSphere Query] {subject}",
            sender=(current_user.username, admin_email),
            reply_to=current_user.email,
            recipients=[admin_email],
            body=(
                f"From: {current_user.username} <{current_user.email}>\n\n"
                f"Subject: {subject}\n\n"
                f"Message:\n{message}\n"
            )
        )
        mail.send(msg)
    except Exception as e:
        app.logger.error(f"Query email failed: {e}")

    return jsonify({"status": "submitted"})


@app.route("/profile/delete", methods=["POST"])
@login_required
@csrf.exempt
def delete_account():
    data = request.get_json(silent=True)
    if not data or data.get("confirm") != "DELETE":
        return jsonify({"error": "Type DELETE to confirm."}), 400

    user = db.session.get(User, current_user.id)
    logout_user()
    db.session.delete(user)
    db.session.commit()
    return jsonify({"status": "deleted"})


# ── Main Page ──────────────────────────────────────────────
@app.route("/")
@login_required
def index():
    return render_template("index.html", username=current_user.username)


# ── Session Routes ─────────────────────────────────────────
@app.route("/sessions", methods=["GET"])
@login_required
def get_sessions():
    sessions = ChatSession.query\
        .filter_by(user_id=current_user.id)\
        .order_by(ChatSession.created_at.desc()).all()
    return jsonify([{
        "id":         s.id,
        "title":      s.title,
        "created_at": s.created_at.strftime("%b %d")
    } for s in sessions])


@app.route("/sessions", methods=["POST"])
@login_required
@csrf.exempt
def create_session():
    s = ChatSession(user_id=current_user.id)
    db.session.add(s)
    db.session.commit()
    return jsonify({"id": s.id, "title": s.title, "created_at": s.created_at.strftime("%b %d")})


@app.route("/sessions/<int:session_id>", methods=["GET"])
@login_required
def get_session(session_id):
    s = ChatSession.query.filter_by(id=session_id, user_id=current_user.id).first()
    if not s:
        return jsonify({"error": "Session not found."}), 404
    return jsonify({
        "id":       s.id,
        "title":    s.title,
        "messages": [{"role": m.role, "content": m.content} for m in s.messages]
    })


@app.route("/sessions/<int:session_id>", methods=["DELETE"])
@login_required
@csrf.exempt
def delete_session(session_id):
    s = ChatSession.query.filter_by(id=session_id, user_id=current_user.id).first()
    if not s:
        return jsonify({"error": "Session not found."}), 404
    db.session.delete(s)
    db.session.commit()
    return jsonify({"status": "deleted"})


# ── Chat Route ─────────────────────────────────────────────
@app.route("/chat", methods=["POST"])
@login_required
@limiter.limit("60 per hour")
@csrf.exempt
def chat():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid request."}), 400

    user_message = data.get("message", "").strip()
    session_id   = data.get("session_id")

    if not user_message:
        return jsonify({"error": "Empty message."}), 400
    if len(user_message) > 4000:
        return jsonify({"error": "Message too long (max 4000 characters)."}), 400
    if not session_id:
        return jsonify({"error": "No session ID provided."}), 400

    s = ChatSession.query.filter_by(id=session_id, user_id=current_user.id).first()
    if not s:
        return jsonify({"error": "Session not found."}), 404

    # Build full history from DB + new message
    history = [{"role": m.role, "content": m.content} for m in s.messages]
    history.append({"role": "user", "content": user_message})

    messages = [{
        "role":    "system",
        "content": (
            "You are a helpful, friendly, and knowledgeable AI assistant. "
            "Answer questions clearly and concisely. Use markdown formatting "
            "when it helps readability (code blocks, bullet points, etc.)."
        ),
    }] + history

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7,
            max_tokens=1500,
        )
    except AuthenticationError:
        return jsonify({"error": "Invalid API key. Please update your .env file."}), 401
    except RateLimitError:
        return jsonify({"error": "Rate limit exceeded. Please wait a moment."}), 429
    except APIConnectionError:
        return jsonify({"error": "Cannot connect to OpenAI. Check your internet connection."}), 503
    except APIStatusError as e:
        return jsonify({"error": f"OpenAI error: {e.message}"}), e.status_code

    assistant_message = response.choices[0].message.content

    # Persist both messages
    db.session.add(ChatMessage(session_id=s.id, role="user",      content=user_message))
    db.session.add(ChatMessage(session_id=s.id, role="assistant", content=assistant_message))

    # Auto-title from the first user message
    new_title = None
    if s.title == "New Chat":
        s.title   = user_message[:50] + ("\u2026" if len(user_message) > 50 else "")
        new_title = s.title

    db.session.commit()

    return jsonify({
        "reply":         assistant_message,
        "title_updated": new_title,
        "usage": {
            "prompt_tokens":     response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
        }
    })


@app.route("/reset", methods=["POST"])
@login_required
@csrf.exempt
def reset():
    return jsonify({"status": "ok"})


# ── Init DB & Run ──────────────────────────────────────────
with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=False, port=5000)
