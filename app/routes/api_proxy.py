"""Same-origin proxy to the py_pg_email API.

The client runs behind a Cloudflare Tunnel that terminates TLS, so all
browser fetches must go to the same origin (https://email.example.com).
Calling the bare HTTP API URL (http://192.168.4.41:5003/api/...) would
be blocked by the browser as mixed content.

This blueprint catches every GET/POST/PUT/DELETE under /api/* and
forwards it to MAIL_SERVER_API_URL/api/* using the JWT from the Flask
session, then copies the response back. The JS only ever sees same-origin
HTTPS URLs.

Only routes that need to be hit from browser JS are exposed. Mail-server
admin endpoints (whitelist, blacklist, etc.) are not proxied - those go
through the server-side MailServerAPI wrapper which uses requests and
isn't subject to the browser mixed-content rule.
"""

from __future__ import annotations

from flask import Blueprint, request, Response, session

from config import Config
from app.api_client import _TLS_VERIFY

api_proxy_bp = Blueprint('api_proxy', __name__, url_prefix='/api')


# Methods we forward. PATCH is in here for things like /threads/<id>/star
# if/when the server adds it. Anything else returns 405.
_ALLOWED_METHODS = frozenset(['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])

# Headers we forward from the browser request (in addition to Content-Type
# which is always forwarded). Authorization is intentionally excluded -
# we set our own from the session.
_FORWARD_REQUEST_HEADERS = (
    'Content-Type',
    'Accept',
    'If-Match',
    'If-None-Match',
)

# Response headers we copy back. Set-Cookie and friends are excluded -
# the proxy is the only thing that should write the session cookie.
_FORWARD_RESPONSE_HEADERS = (
    'Content-Type',
    'Cache-Control',
    'ETag',
    'Last-Modified',
)


def _session_token_or_401():
    """Return the Bearer token from the session, or None if not logged in."""
    token = session.get('token')
    if not token:
        return None
    return token


@api_proxy_bp.route('/<path:api_path>', methods=list(_ALLOWED_METHODS))
def proxy(api_path: str):
    """Forward the request to <MAIL_SERVER_API_URL>/api/<api_path>."""
    token = _session_token_or_401()
    if not token:
        return Response(
            '{"error":"unauthenticated"}', status=401, mimetype='application/json',
        )

    upstream_base = Config.MAIL_SERVER_API_URL.rstrip('/')
    upstream_url = f"{upstream_base}/api/{api_path}"

    # Build the upstream request from the browser's request.
    import requests
    fwd_headers = {'Authorization': f'Bearer {token}'}
    for h in _FORWARD_REQUEST_HEADERS:
        v = request.headers.get(h)
        if v:
            fwd_headers[h] = v

    # Stream the body if any (JSON, form, etc.)
    data = request.get_data() if request.content_length else None

    try:
        upstream = requests.request(
            method=request.method,
            url=upstream_url,
            headers=fwd_headers,
            params=request.args.to_dict(flat=False),
            data=data,
            allow_redirects=False,
            timeout=30,
            verify=_TLS_VERIFY,
        )
    except requests.exceptions.RequestException as exc:
        return Response(
            '{"error":"upstream unreachable: %s"}' % str(exc).replace('"', "'"),
            status=502, mimetype='application/json',
        )

    resp_headers = {
        h: upstream.headers[h] for h in _FORWARD_RESPONSE_HEADERS
        if h in upstream.headers
    }
    return Response(upstream.content, status=upstream.status_code, headers=resp_headers)
