"""Regression tests for two webmail client defects, both fixed 2026-11-04.

1. Replies composed in the browser lost their threading headers.
   `GET /emails/<id>/reply` renders a form that posts `in_reply_to` and
   `references` back to `/compose`. The compose route re-renders the form
   when it receives that post -- which it always does, because the reply
   flow posts to compose first and the user then presses Send -- and it
   re-rendered WITHOUT those two values. The final send therefore carried
   no In-Reply-To and no References header, and the recipient's client
   showed the reply as a standalone conversation instead of threading it.

2. Every timestamp rendered an hour ahead of Brisbane.
   Australia/Sydney is UTC+11 for roughly half the year; Australia/Brisbane
   is UTC+10 all year. The client's fallback timezone was Sydney, and
   there is no endpoint that lets a user set one, so that default was the
   effective timezone for nearly every account.

These tests use no network and no mail server: the API client is stubbed.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import app as app_module
from app import create_app
from app.routes import emails as emails_route

# Imported defensively so this module still loads against the unfixed
# code -- a regression test has to RUN against the bug and fail, not
# blow up at import time.
DEFAULT_TIMEZONE = getattr(app_module, 'DEFAULT_TIMEZONE', None)


PARENT_MESSAGE_ID = 'parent-message-id@example.test'
PARENT_REFERENCES = 'older@example.test parent-message-id@example.test'


@pytest.fixture
def app():
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def stub_api(monkeypatch):
    """Replace the mail-server API client with a stub.

    The compose route only calls the server for the attachment policy when
    it re-renders; everything this test cares about is local.
    """

    class StubAPI:
        def get_allowed_attachment_types(self, token):
            return {'allowed_extensions': ['pdf', 'txt'], 'max_file_size': 10485760}

        def get_attachments(self, token, email_id):
            return []

        def get_email(self, token, email_id):
            return {
                'id': email_id,
                'subject': 'test',
                'message_id': PARENT_MESSAGE_ID,
                'references_chain': PARENT_REFERENCES,
                'sender': {'email': 'someone@example.test'},
                'created_at': '2026-11-04T07:04:48+10:00',
                'body': 'original body',
            }

        def send_email(self, *args, **kwargs):
            raise AssertionError('the stub should not send in this test')

    stub = StubAPI()
    monkeypatch.setattr(emails_route, 'api', stub)
    return stub


def _login(client):
    with client.session_transaction() as sess:
        sess['token'] = 'stub-token'
        sess['user'] = {'id': 1, 'email': 'michael@example.test',
                        'timezone': DEFAULT_TIMEZONE or 'Australia/Brisbane'}


def test_reply_redirect_carries_threading_fields(client, stub_api):
    """The reply route must hand compose an In-Reply-To and a References."""
    _login(client)
    resp = client.get('/emails/4242/reply')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert f'name="in_reply_to" value="{PARENT_MESSAGE_ID}"' in html
    assert PARENT_REFERENCES in html


def test_compose_re_render_keeps_threading_fields(client, stub_api):
    """The compose re-render must not drop In-Reply-To / References.

    This is the defect: the reply flow posts to /compose, compose
    re-renders the form, and the re-render used to omit both values --
    so the message that actually went out had no threading headers.
    """
    _login(client)
    resp = client.post('/compose', data={
        'from_forward': '1',
        'to': 'someone@example.test',
        'subject': 'Re: test',
        'body': 'reply body',
        'in_reply_to': PARENT_MESSAGE_ID,
        'references': PARENT_REFERENCES,
    })
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert f'name="in_reply_to" value="{PARENT_MESSAGE_ID}"' in html, \
        'compose re-render dropped the In-Reply-To hidden field'
    assert f'name="references" value="{PARENT_REFERENCES}"' in html, \
        'compose re-render dropped the References hidden field'


def test_compose_validation_error_keeps_threading_fields(client, stub_api):
    """A validation failure re-renders too, and must keep them."""
    _login(client)
    resp = client.post('/compose', data={
        'from_forward': '1',
        'to': '',
        'subject': 'Re: test',
        'body': 'reply body',
        'in_reply_to': PARENT_MESSAGE_ID,
        'references': PARENT_REFERENCES,
    })
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert f'name="in_reply_to" value="{PARENT_MESSAGE_ID}"' in html
    assert f'name="references" value="{PARENT_REFERENCES}"' in html


def test_default_timezone_is_brisbane():
    """Brisbane is UTC+10 all year; Sydney is UTC+11 for part of it."""
    assert DEFAULT_TIMEZONE == 'Australia/Brisbane'


def test_format_datetime_uses_brisbane(app):
    """A timestamp stored at 07:04 Brisbane must render as 07:04."""
    from app import format_datetime
    with app.test_request_context():
        from flask import session
        session['user'] = {'id': 1, 'email': 'michael@example.test'}
        rendered = format_datetime('2026-11-04T07:04:48+10:00')
    assert rendered == 'Nov 04, 2026 07:04 AM', rendered


def test_format_datetime_honours_an_explicit_brisbane_session(app):
    """An account already stored as Brisbane must not shift either."""
    from app import format_datetime
    with app.test_request_context():
        from flask import session
        session['user'] = {'id': 1, 'email': 'michael@example.test',
                           'timezone': 'Australia/Brisbane'}
        rendered = format_datetime('2026-11-04T07:04:48+10:00')
    assert rendered == 'Nov 04, 2026 07:04 AM', rendered
