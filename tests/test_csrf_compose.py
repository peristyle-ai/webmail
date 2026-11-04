"""Regression tests for the compose CSRF failure, fixed 2026-11-04.

Two defects, both in the webmail client:

1. The compose page's "refresh the CSRF token before submitting" script
   bound itself to `document.querySelector('form')`. base.html renders a
   SEARCH form before the content block, so that selector returned the
   search box and the compose form never got the handler. The compose
   form therefore always submitted the token that was rendered into the
   page.

2. A CSRF rejection was a bare "400 Bad Request -- The CSRF tokens do
   not match." Because CSRFProtect runs as a before_request hook the
   route never executed, so the user lost everything they had typed and
   got no indication that nothing had been sent.

The second defect is the one that bit: the session was replaced under a
page that had been open (the user signed in again), so the token in the
form no longer matched the one in the session.

These tests use no network and no mail server: the API client is stubbed.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from app import create_app
from app.routes import emails as emails_route


@pytest.fixture
def app():
    app = create_app()
    app.config['TESTING'] = True
    # CSRF must be ON for these tests -- that is the behaviour under test.
    app.config['WTF_CSRF_ENABLED'] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def stub_api(monkeypatch):
    """Replace the mail-server API client with a stub.

    Records the sends it was asked to make so a test can assert that
    nothing was sent.
    """
    class StubAPI:
        def __init__(self):
            self.sent = []

        def get_allowed_attachment_types(self, token):
            return {'allowed_extensions': ['pdf', 'txt'], 'max_file_size': 10485760}

        def get_attachments(self, token, email_id):
            return []

        def get_email(self, token, email_id):
            return {'id': email_id, 'subject': 'test', 'sender': {'email': 'a@example.test'}}

        def send_email(self, token, to, subject, body, **kwargs):
            self.sent.append({'to': to, 'subject': subject, 'body': body, **kwargs})
            return {'id': 4242}

    stub = StubAPI()
    monkeypatch.setattr(emails_route, 'api', stub)
    return stub


def _login(client):
    with client.session_transaction() as sess:
        sess['token'] = 'stub-token'
        sess['user'] = {'id': 1, 'email': 'michael@example.test',
                        'timezone': 'Australia/Brisbane'}


def _compose_token(client):
    """Fetch the compose page and return the CSRF token it rendered."""
    resp = client.get('/compose')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    marker = 'name="csrf_token" value="'
    start = html.index(marker) + len(marker)
    return html[start:html.index('"', start)]


def test_compose_form_has_a_stable_id(client, stub_api):
    """The compose form needs an id the refresh script can target.

    Without one the script falls back to querySelector('form'), which
    matches base.html's search form instead.
    """
    _login(client)
    html = client.get('/compose').get_data(as_text=True)
    assert 'id="composeForm"' in html, \
        'the compose form has no id, so the token-refresh script cannot target it'
    assert "document.getElementById('composeForm')" in html, \
        'the token-refresh script still binds to the first form in the document'


def test_stale_csrf_token_does_not_lose_the_message(client, stub_api):
    """A CSRF rejection must re-render the compose form, keeping the text.

    This is the defect: the user composed a message, the session was
    replaced under the open page, the POST was rejected, and the bare
    400 discarded everything they had typed.
    """
    _login(client)
    token = _compose_token(client)

    # The session is replaced: the raw token in the session changes, so
    # the token rendered into the page no longer matches.
    with client.session_transaction() as sess:
        sess['csrf_token'] = 'a-different-raw-token'

    resp = client.post('/compose', data={
        'to': 'recipient@example.test',
        'subject': 'the subject the user typed',
        'body': 'the body the user typed',
        'csrf_token': token,
    })

    assert resp.status_code == 200, \
        f'expected the compose form to be re-rendered, got {resp.status_code}'
    html = resp.get_data(as_text=True)
    assert 'the subject the user typed' in html, 'the subject was lost'
    assert 'the body the user typed' in html, 'the body was lost'
    assert 'recipient@example.test' in html, 'the recipient was lost'
    assert 'Nothing was sent' in html or 'nothing was sent' in html, \
        'the user was not told that nothing was sent'


def test_csrf_rejection_sends_nothing(client, stub_api):
    """A rejected POST must not reach the mail server at all."""
    _login(client)
    token = _compose_token(client)

    with client.session_transaction() as sess:
        sess['csrf_token'] = 'a-different-raw-token'

    client.post('/compose', data={
        'to': 'recipient@example.test',
        'subject': 'must not go out',
        'body': 'must not go out',
        'csrf_token': token,
    })

    assert stub_api.sent == [], f'the mail server was called: {stub_api.sent}'


def test_re_rendered_form_carries_a_usable_token(client, stub_api):
    """After a rejection, the re-rendered form must be submittable.

    Otherwise the user presses Send again and gets the same 400 -- the
    fix would be cosmetic.
    """
    _login(client)
    token = _compose_token(client)

    with client.session_transaction() as sess:
        sess['csrf_token'] = 'a-different-raw-token'

    resp = client.post('/compose', data={
        'to': 'recipient@example.test',
        'subject': 'retry me',
        'body': 'retry me',
        'csrf_token': token,
    })
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    fresh = _compose_token(client)

    resp2 = client.post('/compose', data={
        'to': 'recipient@example.test',
        'subject': 'retry me',
        'body': 'retry me',
        'csrf_token': fresh,
    })
    assert resp2.status_code in (200, 302), \
        f'the re-rendered form was not submittable: {resp2.status_code}'
    assert len(stub_api.sent) == 1, f'expected one send, got {stub_api.sent}'
    assert stub_api.sent[0]['subject'] == 'retry me'


def test_csrf_rejection_on_other_routes_is_not_silent(client, stub_api):
    """Other POSTs must not be swallowed by the compose recovery."""
    _login(client)
    with client.session_transaction() as sess:
        sess['csrf_token'] = 'a-different-raw-token'

    resp = client.post('/folders/create', data={'name': 'x', 'csrf_token': 'stale'})
    assert resp.status_code == 400, \
        f'expected a 400 on a non-compose route, got {resp.status_code}'
    # The compose recovery must not hijack unrelated routes: they get a
    # plain explanation, not a re-rendered compose form.
    assert b'id="composeForm"' not in resp.data, \
        'the compose form was re-rendered on an unrelated route'
    assert b'Session expired' in resp.data, \
        'the user was not told why the request failed'
