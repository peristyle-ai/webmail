"""In-memory rate limiter for the login endpoint.

Single-process Flask app, so in-memory is sufficient. Tracks failed
login attempts per IP and locks out after repeated failures.

Limits:
  - 5 failed attempts per IP per 15-minute window → 15-minute lockout
  - Successful login resets the counter
"""

import time
import threading
from collections import defaultdict
from functools import wraps

from flask import request, flash, render_template

_lock = threading.Lock()

# {ip: [(timestamp, success), ...]}
_attempts: dict[str, list[tuple[float, bool]]] = defaultdict(list)

# {ip: lockout_until_timestamp}
_lockouts: dict[str, float] = {}

MAX_ATTEMPTS = 5
WINDOW_SECONDS = 15 * 60       # 15 minutes
LOCKOUT_SECONDS = 15 * 60      # 15 minutes


def _get_client_ip() -> str:
    """Get the real client IP, respecting X-Forwarded-For from Cloudflare Tunnel."""
    # Cloudflare Tunnel sets CF-Connecting-IP; fall back to X-Forwarded-For
    return (
        request.headers.get('CF-Connecting-IP')
        or request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
        or request.remote_addr
        or 'unknown'
    )


def _cleanup_old_attempts(ip: str, now: float):
    """Remove attempts older than the window."""
    cutoff = now - WINDOW_SECONDS
    _attempts[ip] = [(ts, ok) for ts, ok in _attempts[ip] if ts > cutoff]


def is_locked_out(ip: str) -> bool:
    """Check if an IP is currently locked out."""
    with _lock:
        until = _lockouts.get(ip, 0)
        if until > time.time():
            return True
        # Expired lockout — clean up
        if ip in _lockouts:
            del _lockouts[ip]
        return False


def record_attempt(ip: str, success: bool):
    """Record a login attempt. On success, reset the counter."""
    now = time.time()
    with _lock:
        if success:
            _attempts.pop(ip, None)
            _lockouts.pop(ip, None)
            return

        _cleanup_old_attempts(ip, now)
        _attempts[ip].append((now, False))

        failed = sum(1 for _, ok in _attempts[ip] if not ok)
        if failed >= MAX_ATTEMPTS:
            _lockouts[ip] = now + LOCKOUT_SECONDS
            _attempts.pop(ip, None)  # Reset after lockout


def remaining_lockout_seconds(ip: str) -> int:
    """How many seconds left in the lockout (0 if not locked)."""
    with _lock:
        until = _lockouts.get(ip, 0)
        remaining = until - time.time()
        return max(0, int(remaining))


def login_rate_limit(f):
    """Decorator: rate-limit the login POST endpoint."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if request.method == 'POST':
            ip = _get_client_ip()
            if is_locked_out(ip):
                secs = remaining_lockout_seconds(ip)
                mins = secs // 60 + 1
                flash(
                    f'Too many failed login attempts. Try again in {mins} minute{"s" if mins != 1 else ""}.',
                    'error',
                )
                return render_template('login.html', email=''), 429
        return f(*args, **kwargs)
    return wrapper
