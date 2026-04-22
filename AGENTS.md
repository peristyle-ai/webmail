# PyPG Client - AI Agent Instructions

## Overview

A Gmail-like web email client (PWA-enabled) connecting to the mail server at `py_pg_email` (port 5003). This client runs on port 5005.

## Project Structure

```
~/git/py_pg_client/
├── app/
│   ├── __init__.py              # Flask app initialization + blueprints + SW route
│   ├── api_client.py            # Mail server API wrapper
│   ├── db.py                    # Database connection
│   ├── routes/
│   │   ├── auth.py              # Login/logout
│   │   ├── emails.py            # Inbox, compose, email actions
│   │   ├── folders.py           # Folder management
│   │   ├── whitelist.py         # Domain whitelist
│   │   └── blacklist.py         # IP blacklist view
│   ├── templates/               # Jinja2 HTML templates (mobile-first responsive)
│   └── static/
│       ├── manifest.json        # PWA manifest
│       ├── sw.js                # Service worker
│       └── icons/               # PWA icons (192x192, 512x512)
├── tests/                       # Test files
├── config.py                    # Configuration
├── requirements.txt             # Python dependencies
├── run.py                       # Entry point
└── AGENTS.md                    # This file
```

## Running the Application

### Development
```bash
cd ~/git/py_pg_client
source venv/bin/activate
python3 run.py
```

### Production (systemd)
```bash
systemctl --user daemon-reload
systemctl --user enable --now email-client.service
```

Service file: `~/.config/systemd/user/email-client.service`

Commands:
- `systemctl --user status email-client.service` - check status
- `systemctl --user restart email-client.service` - restart
- `systemctl --user stop email-client.service` - stop
- `journalctl --user -u email-client.service` - view logs

The application runs on `http://192.168.4.41:5005`. Authorized user: `the operator@example.com.au`

## Build/Lint/Test Commands

### Install Dependencies
**IMPORTANT**: Always activate the virtual environment before running pip:
```bash
source venv/bin/activate
pip install -r requirements.txt
pip install pytest>=7.0.0 pytest-flask>=1.2.0 pytest-cov>=4.0.0 flake8>=6.0.0 black>=23.0.0 mypy>=1.0.0
```

### Running Tests
```bash
# Run all tests
pytest

# Run single test file
pytest tests/test_connectivity.py

# Run single test
pytest tests/test_connectivity.py::TestConnectivity::test_mail_server_reachable

# Run specific test function by name pattern
pytest -k "test_mail_server" -v

# Run with coverage
pytest --cov=app --cov-report=term-missing
```

### Linting & Type Checking
```bash
flake8 app/ --max-line-length=100 --ignore=E501,W503
black --check app/
black app/  # auto-fix
mypy app/ --ignore-missing-imports
```

## Code Style Guidelines

### General Principles
- **Clean and minimal** - Flask + Jinja2 server-side rendering
- **Follow existing patterns** - Match the coding style in the codebase
- **Security-first** - Never expose JWT tokens to client-side JS

### Imports (order: stdlib, third-party, local)
```python
import os
import json
from functools import wraps

from flask import Blueprint, render_template, request, redirect, url_for, session, flash
import requests

from app.api_client import MailServerAPI, AuthenticationError, APIError
from config import Config
```

### Formatting
- Line length: 100 characters max
- Indentation: 4 spaces (no tabs)
- Blank lines: 2 between top-level definitions, 1 between functions

### Naming Conventions
| Type | Convention | Example |
|------|------------|---------|
| Files | snake_case | `api_client.py` |
| Classes | PascalCase | `MailServerAPI` |
| Functions/variables | snake_case | `get_emails()` |
| Constants | UPPER_SNAKE_CASE | `MAX_PAGE_SIZE = 100` |
| Blueprint names | snake_case + `_bp` suffix | `auth_bp` |

### Type Hints
```python
def get_emails(self, token: str, folder_id: int | None = None, page: int = 1) -> dict:
    """Get list of emails."""
    pass
```

### Error Handling
- Use custom exception classes (`AuthenticationError`, `APIError`)
- Catch specific exceptions, not bare `Exception`
- Return meaningful error messages via `flash`

```python
class AuthenticationError(Exception):
    pass

class APIError(Exception):
    pass

try:
    token, user = api.login(email, password)
except AuthenticationError:
    flash('Invalid credentials', 'error')
except APIError as e:
    flash(str(e), 'error')
```

### Routes/Blueprint Patterns
```python
from flask import Blueprint, render_template, request, redirect, url_for

auth_bp = Blueprint('auth', __name__)
api = MailServerAPI()

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        # ... logic
    return render_template('login.html')
```

### Authentication Decorator
```python
def require_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'token' not in session:
            flash('Please log in to access this page', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function
```

### Template Guidelines
- Use Jinja2 auto-escaping (default) for XSS prevention
- Sanitize HTML email bodies by rendering in sandboxed iframe
- Mobile-first responsive design with Tailwind CSS
- PWA-enabled: manifest.json, service worker, mobile meta tags

### Security
- Store JWT in Flask session (server-side), never localStorage
- Validate all user inputs
- Use parameterized queries via psycopg2
- Bind to specific IP via `HOST` env var (defaults to 127.0.0.1, set to 192.168.4.41 for production)

## API Integration

### Base Configuration
- Mail Server URL: `http://192.168.4.41:5003`
- Client URL: `http://192.168.4.41:5005`
- All endpoints require JWT Bearer token (except `/health`)

### Email Access Control
- Email visibility is based on **folder ownership**: users can only see/access emails in folders they own (`WHERE f.user_id = current_user_id`)
- API responses return `sender` and `recipient` as objects `{email, name}`, not flat fields
- Local delivery creates separate copies: one in sender's Sent folder, one in recipient's Inbox

### Common Patterns
```python
# Store token in session
session['token'] = token
session['user'] = user
session.permanent = True

# Use in API calls
headers = {'Authorization': f'Bearer {session["token"]}'}
response = requests.get(f'{API_URL}/api/emails', headers=headers)

# Handle 401
if response.status_code == 401:
    return redirect(url_for('auth.login'))
```

### Key Endpoints Used
- `POST /auth/login` - Authentication
- `GET/POST/DELETE /api/emails` - Email CRUD
- `GET/POST/DELETE /api/folders` - Folder management
- `GET /api/search` - Search
- `GET/DELETE /api/blacklist/ip` - Blacklist management

## Dependencies
```
flask>=2.0.0 requests>=2.28.0 psycopg2-binary>=2.9.0 python-dotenv>=0.19.0
flask-wtf>=1.0.0 wtforms>=3.0.0 flask-login>=0.6.0 email-validator>=1.3.0 bleach>=6.0.0
pytest>=7.0.0 pytest-flask>=1.2.0 pytest-cov>=4.0.0 flake8>=6.0.0 black>=23.0.0 mypy>=1.0.0
```

## Common Pitfalls

1. **Don't** store JWT in localStorage (use server-side session)
2. **Don't** expose mail server API credentials to browser
3. **Do** handle token expiration gracefully (redirect to login)
4. **Do** validate all user inputs
5. **Do** use parameterized queries for DB operations
6. **Don't** use `0.0.0.0` as HOST — bind to specific IP (`192.168.4.41`)

## Questions?
1. Check API guide: `~/git/py_pg_email/coding_agent/API_INTEGRATION_GUIDE.md`
2. Review API docs: `~/git/py_pg_email/API_DOCUMENTATION.md`
