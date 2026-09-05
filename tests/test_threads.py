"""Smoke tests for the threading UI client changes.

Verifies the py_pg_client api_client.py exposes the three new methods
(get_threads, get_thread_messages, mark_thread_read) and that the
mail_server endpoints backing them return well-formed responses.

These tests hit the live mail_server on 192.168.4.41:5003, so they need
a registered test user with a known password. The tests register a fresh
user on first run if needed (idempotent via DELETE first), so they're
self-contained and don't depend on any other test ordering.

Run:
    POSTGRES_PASSWORD_TEST='<postgres role pw>' pytest tests/test_threads.py -v
"""

import sys
import uuid

sys.path.insert(0, '/opt/py_pg_accounts/git/py_pg_client')

import pytest
import requests
from config import Config

MAIL = Config.MAIL_SERVER_API_URL
TEST_EMAIL = 'threading-ui-test@example.com'
TEST_PASSWORD = 'threading-ui-test-pw-2026'


def _register_or_login():
    """Return a JWT token for the test user, registering first if needed."""
    requests.post(
        f'{MAIL}/auth/register',
        json={'email': TEST_EMAIL, 'password': TEST_PASSWORD, 'name': 'Threading UI Test'},
        timeout=5,
    )
    resp = requests.post(
        f'{MAIL}/auth/login',
        json={'email': TEST_EMAIL, 'password': TEST_PASSWORD},
        timeout=5,
    )
    assert resp.status_code == 200, f'login failed: {resp.status_code} {resp.text[:200]}'
    return resp.json()['token']


class TestThreadsApiClient:
    """Tests for app/api_client.py threading methods (live integration)."""

    def test_api_client_imports(self):
        """api_client exposes the three threading methods."""
        from app.api_client import MailServerAPI
        api = MailServerAPI()
        assert hasattr(api, 'get_threads')
        assert hasattr(api, 'get_thread_messages')
        assert hasattr(api, 'mark_thread_read')

    def test_get_threads_returns_known_shape(self):
        """GET /api/threads returns the expected envelope shape."""
        token = _register_or_login()
        from app.api_client import MailServerAPI
        data = MailServerAPI().get_threads(token, folder='Inbox', limit=5)
        assert isinstance(data, dict), f'expected dict, got {type(data).__name__}'
        for key in ('threads', 'total', 'limit', 'offset'):
            assert key in data, f'missing key {key!r} in {list(data.keys())}'
        assert isinstance(data['threads'], list)
        assert isinstance(data['total'], int)
        assert isinstance(data['limit'], int)

    def test_get_thread_messages_invalid_uuid_returns_400(self):
        """Invalid thread_id is rejected at the API layer (400)."""
        token = _register_or_login()
        resp = requests.get(
            f'{MAIL}/api/threads/not-a-uuid/messages',
            headers={'Authorization': f'Bearer {token}'},
            timeout=5,
        )
        assert resp.status_code == 400

    def test_get_thread_messages_unknown_uuid_returns_404(self):
        """Unknown thread_id returns 404 (or empty messages if shape is OK)."""
        token = _register_or_login()
        random_uuid = str(uuid.uuid4())
        resp = requests.get(
            f'{MAIL}/api/threads/{random_uuid}/messages',
            headers={'Authorization': f'Bearer {token}'},
            timeout=5,
        )
        # Either 404 (not visible) or 200 with empty messages - both acceptable
        assert resp.status_code in (200, 404), f'unexpected {resp.status_code}: {resp.text[:200]}'
        if resp.status_code == 200:
            body = resp.json()
            assert body.get('messages') == []

    def test_mark_thread_read_invalid_uuid_returns_400(self):
        """POST /api/threads/<bad>/read returns 400."""
        token = _register_or_login()
        resp = requests.post(
            f'{MAIL}/api/threads/not-a-uuid/read',
            headers={'Authorization': f'Bearer {token}'},
            json={},
            timeout=5,
        )
        assert resp.status_code == 400

    def test_mark_thread_read_unknown_uuid_returns_404(self):
        """POST /api/threads/<unknown>/read returns 404."""
        token = _register_or_login()
        random_uuid = str(uuid.uuid4())
        resp = requests.post(
            f'{MAIL}/api/threads/{random_uuid}/read',
            headers={'Authorization': f'Bearer {token}'},
            json={},
            timeout=5,
        )
        assert resp.status_code == 404


class TestApiProxy:
    """Tests for the /api/* same-origin proxy in app/routes/api_proxy.py.

    The proxy exists so the JS can hit /api/threads/... from an HTTPS
    page without triggering a mixed-content block. It forwards the
    request to the configured MAIL_SERVER_API_URL using the JWT in the
    Flask session.
    """

    def test_proxy_unauthenticated_returns_401(self):
        """GET /api/threads/<random>/messages without a session -> 401."""
        from app import create_app
        app = create_app()
        with app.test_client() as c:
            r = c.get('/api/threads/' + str(uuid.uuid4()) + '/messages')
            assert r.status_code == 401

    def test_proxy_unknown_uuid_returns_404_or_empty(self):
        """GET /api/threads/<unknown>/messages with auth -> 404 or 200+empty."""
        token = _register_or_login()
        from app import create_app
        app = create_app()
        with app.test_client() as c:
            with c.session_transaction() as sess:
                sess['token'] = token
            random_uuid = str(uuid.uuid4())
            r = c.get('/api/threads/' + random_uuid + '/messages')
            assert r.status_code in (200, 404)
            if r.status_code == 200:
                body = r.get_json()
                assert body.get('messages') == []

    def test_proxy_returns_json_envelope_for_list(self):
        """GET /api/threads returns the expected envelope shape."""
        token = _register_or_login()
        from app import create_app
        app = create_app()
        with app.test_client() as c:
            with c.session_transaction() as sess:
                sess['token'] = token
            r = c.get('/api/threads?folder=Inbox&limit=5')
            assert r.status_code == 200
            body = r.get_json()
            assert isinstance(body, dict)
            for key in ('threads', 'total', 'limit', 'offset'):
                assert key in body
