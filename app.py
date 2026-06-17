"""
Student Authentication Service with Prometheus Monitoring
-----------------------------------------------------------
A small Flask microservice that demonstrates:
  - Authentication (register / login / session check)
  - Observability (Prometheus metrics)
  - Logging (info, error, and security-style logs)
  - Health checking for container orchestration

Data is stored in-memory (a Python dict) — no database required.
"""

import logging
import time
import uuid
from datetime import datetime, timezone

from flask import Flask, jsonify, request
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
from werkzeug.security import generate_password_hash, check_password_hash

# --------------------------------------------------------------------------
# App setup
# --------------------------------------------------------------------------
app = Flask(__name__)

# --------------------------------------------------------------------------
# Logging configuration
# --------------------------------------------------------------------------
# Logs go to both the console (so `docker logs` shows them) and a file
# (so you have persistent evidence for your report / screenshots).
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("app.log"),
    ],
)
logger = logging.getLogger("auth-service")

# --------------------------------------------------------------------------
# In-memory "database"
# --------------------------------------------------------------------------
# users: { username: {"password_hash": str, "created_at": str} }
users = {}

# sessions: { session_token: {"username": str, "created_at": str} }
sessions = {}

# Tracks consecutive failed login attempts per username (for the
# "security-style" lockout logging requirement).
failed_attempts = {}
MAX_FAILED_ATTEMPTS = 3

# --------------------------------------------------------------------------
# Prometheus metrics
# --------------------------------------------------------------------------
# 1. Total API requests (labelled by endpoint + method so you can break
#    down traffic per route in Grafana).
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total number of HTTP requests received",
    ["method", "endpoint", "http_status"],
)

# 2. Every login attempt, regardless of outcome.
LOGIN_ATTEMPTS = Counter(
    "login_attempts_total",
    "Total number of login attempts",
)

# 3. Successful vs failed logins broken out as separate series.
LOGIN_SUCCESS = Counter(
    "login_success_total",
    "Total number of successful logins",
)
LOGIN_FAILURE = Counter(
    "login_failure_total",
    "Total number of failed logins",
)

# 4. Response time histogram -> lets Grafana compute p50/p90/p99 latency
#    and average response time.
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["endpoint"],
)

# 5. Active sessions gauge (bonus) — number of currently logged-in users.
ACTIVE_SESSIONS = Gauge(
    "active_sessions",
    "Number of currently active (logged-in) sessions",
)

# Registrations, tracked too since it's useful for the dashboard story.
REGISTRATION_COUNT = Counter(
    "registrations_total",
    "Total number of successful user registrations",
)


# --------------------------------------------------------------------------
# Request-level instrumentation (runs around every request automatically)
# --------------------------------------------------------------------------
@app.before_request
def _start_timer():
    request._start_time = time.time()


@app.after_request
def _record_metrics(response):
    # Skip instrumenting the /metrics endpoint itself to avoid noise.
    if request.path != "/metrics":
        latency = time.time() - getattr(request, "_start_time", time.time())
        REQUEST_LATENCY.labels(endpoint=request.path).observe(latency)
        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=request.path,
            http_status=response.status_code,
        ).inc()
    return response


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def now_iso():
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------
@app.route("/health", methods=["GET"])
def health():
    """Simple liveness probe used by Docker / Prometheus."""
    return jsonify({"status": "healthy", "timestamp": now_iso()}), 200


@app.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    if not username or not password:
        logger.error("Registration failed: missing username or password")
        return jsonify({"success": False, "message": "username and password are required"}), 400

    if username in users:
        logger.warning(f"Registration failed: username '{username}' already exists")
        return jsonify({"success": False, "message": "username already exists"}), 409

    users[username] = {
        "password_hash": generate_password_hash(password),
        "created_at": now_iso(),
    }
    REGISTRATION_COUNT.inc()
    logger.info(f"User registered: {username}")

    return jsonify({"success": True, "message": "user registered successfully"}), 201


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    LOGIN_ATTEMPTS.inc()

    # Lockout check first (security-style logging requirement)
    if failed_attempts.get(username, 0) >= MAX_FAILED_ATTEMPTS:
        logger.warning(f"User '{username}' locked after {MAX_FAILED_ATTEMPTS} attempts")
        LOGIN_FAILURE.inc()
        return jsonify({"success": False, "message": "account temporarily locked"}), 423

    user = users.get(username)

    if not user:
        logger.error(f"Login failed: invalid user '{username}'")
        failed_attempts[username] = failed_attempts.get(username, 0) + 1
        LOGIN_FAILURE.inc()
        return jsonify({"success": False, "message": "invalid username or password"}), 401

    if not check_password_hash(user["password_hash"], password):
        failed_attempts[username] = failed_attempts.get(username, 0) + 1
        logger.error(f"Login failed: wrong password for user '{username}'")

        if failed_attempts[username] >= MAX_FAILED_ATTEMPTS:
            logger.warning(f"User '{username}' failed login attempt {failed_attempts[username]} times")
            logger.warning(f"User '{username}' locked after {MAX_FAILED_ATTEMPTS} attempts")

        LOGIN_FAILURE.inc()
        return jsonify({"success": False, "message": "invalid username or password"}), 401

    # Successful login: reset failed attempt counter, create session
    failed_attempts[username] = 0
    token = str(uuid.uuid4())
    sessions[token] = {"username": username, "created_at": now_iso()}
    ACTIVE_SESSIONS.set(len(sessions))

    LOGIN_SUCCESS.inc()
    logger.info(f"Login success: {username}")

    return jsonify({"success": True, "message": "login successful", "session_token": token}), 200


@app.route("/session", methods=["GET"])
def session_check():
    """Checks whether a given session token corresponds to a logged-in user."""
    token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()

    if not token or token not in sessions:
        return jsonify({"logged_in": False}), 200

    session_data = sessions[token]
    return jsonify({
        "logged_in": True,
        "username": session_data["username"],
        "since": session_data["created_at"],
    }), 200


@app.route("/logout", methods=["POST"])
def logout():
    """Bonus endpoint: ends a session and updates the active sessions gauge."""
    token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()

    if token in sessions:
        username = sessions[token]["username"]
        del sessions[token]
        ACTIVE_SESSIONS.set(len(sessions))
        logger.info(f"User logged out: {username}")
        return jsonify({"success": True, "message": "logged out"}), 200

    return jsonify({"success": False, "message": "invalid session"}), 400


@app.route("/metrics", methods=["GET"])
def metrics():
    """Exposed for Prometheus to scrape."""
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)