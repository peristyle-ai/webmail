import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from flask import Flask, send_from_directory, session
from config import Config

def format_datetime(value):
    if not value:
        return ''
    try:
        for fmt in ('%a, %d %b %Y %H:%M:%S GMT', '%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%d %H:%M:%S'):
            try:
                dt = datetime.strptime(value.strip(), fmt)
                break
            except ValueError:
                continue
        else:
            return value
    except Exception:
        return value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    tz_name = session.get('user', {}).get('timezone', 'Australia/Sydney')
    try:
        dt = dt.astimezone(ZoneInfo(tz_name))
    except Exception:
        dt = dt.astimezone(ZoneInfo('Australia/Sydney'))
    return dt.strftime('%b %d, %Y %I:%M %p')


def format_short_date(value):
    """Gmail-style short date: today=time, this week=weekday, older=short date."""
    if not value:
        return ''
    # ISO timestamps may carry microseconds (e.g. 2026-09-05T13:57:32.138552+10:00).
    # %z doesn't tolerate fractional seconds, so strip them before parsing.
    s = value.strip()
    if '.' in s and ('+' in s[s.index('.'):] or s.count('-') > 2):
        head, _, tail = s.partition('.')
        # Keep only digits before the next non-digit char (timezone or Z)
        cut = 0
        while cut < len(tail) and tail[cut].isdigit():
            cut += 1
        s = head + tail[cut:]
    try:
        for fmt in ('%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%dT%H:%M:%S', '%a, %d %b %Y %H:%M:%S %Z',
                    '%Y-%m-%d %H:%M:%S'):
            try:
                dt = datetime.strptime(s, fmt)
                break
            except ValueError:
                continue
        else:
            return value
    except Exception:
        return value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    tz_name = session.get('user', {}).get('timezone', 'Australia/Sydney')
    try:
        local_dt = dt.astimezone(ZoneInfo(tz_name))
    except Exception:
        local_dt = dt.astimezone(ZoneInfo('Australia/Sydney'))
    now = datetime.now(local_dt.tzinfo)
    delta_days = (now.date() - local_dt.date()).days
    if delta_days < 0:
        return local_dt.strftime('%b %d')
    if delta_days == 0:
        return local_dt.strftime('%I:%M %p').lstrip('0')
    if delta_days < 7:
        return local_dt.strftime('%a')
    if local_dt.year == now.year:
        return local_dt.strftime('%b %d')
    return local_dt.strftime('%b %d, %Y')

def format_compact(value):
    """Compact `YYYY-MM-DD HH:MM` (24h, integer minutes, no seconds, no microseconds)."""
    if not value:
        return ''
    s = value.strip()
    # Strip microseconds before parsing: %z doesn't tolerate fractional seconds
    if '.' in s:
        head, _, tail = s.partition('.')
        cut = 0
        while cut < len(tail) and tail[cut].isdigit():
            cut += 1
        s = head + tail[cut:]
    # Try the common formats the API may return
    for fmt in ('%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S', '%a, %d %b %Y %H:%M:%S %Z'):
        try:
            dt = datetime.strptime(s, fmt)
            break
        except ValueError:
            continue
    else:
        return value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    try:
        dt = dt.astimezone(ZoneInfo(session.get('user', {}).get('timezone', 'Australia/Sydney')))
    except Exception:
        pass
    return dt.strftime('%Y-%m-%d %H:%M')


def create_app():
    app = Flask(__name__, template_folder='templates', static_folder='static')
    app.config.from_object(Config)
    app.jinja_env.filters['datetime'] = format_datetime
    app.jinja_env.filters['short_date'] = format_short_date
    app.jinja_env.filters['compact'] = format_compact

    @app.context_processor
    def inject_globals():
        return dict(folders=[], current_folder=session.get('current_folder', 'Inbox'))

    # Initialize database
    from app.db import init_db
    init_db()

    # Serve service worker at root for PWA scope
    @app.route('/sw.js')
    def service_worker():
        return send_from_directory(
            os.path.join(app.root_path, 'static'), 'sw.js',
            mimetype='application/javascript')

    from app.routes.auth import auth_bp
    from app.routes.emails import emails_bp
    from app.routes.folders import folders_bp
    from app.routes.whitelist import whitelist_bp
    from app.routes.blacklist import blacklist_bp
    from app.routes.blocklist import blocklist_bp
    from app.routes.api_proxy import api_proxy_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(emails_bp)
    app.register_blueprint(folders_bp)
    app.register_blueprint(whitelist_bp)
    app.register_blueprint(blacklist_bp)
    app.register_blueprint(blocklist_bp)
    app.register_blueprint(api_proxy_bp)
    
    # Register error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        return "Page not found", 404
    
    @app.errorhandler(500)
    def internal_error(error):
        return "Internal server error", 500
    
    return app
