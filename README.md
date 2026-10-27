# PyPG Client - Gmail-like Email Web Client

A web-based email client that provides a Gmail-like interface for the PyPG mail server running on port 5003. PWA-enabled for mobile use.

## Features

### Core Email Management
- **Authentication**: JWT-based login/logout with session management
- **Inbox View**: List emails with sender, subject, preview, date
- **Email Reading**: Full email display with HTML/text support (sandboxed iframe)
- **Compose**: Create and send new emails
- **Reply/Forward**: Email threading actions with pre-filled content
- **Mark Read/Unread**: Toggle read status
- **Star/Unstar**: Toggle starred status
- **Delete**: Move emails to trash
- **Move to Folder**: Change email folder
- **Bulk Actions**: Select multiple emails to move, delete, or block sender/domain

### PWA Support
- **Installable**: Add to home screen on mobile devices
- **Service Worker**: Offline caching for faster loading
- **Mobile-First Design**: Responsive layout with hamburger menu, bottom nav, touch-friendly targets
- **Apple/Android**: Meta tags for both platforms

### Folder Management
- **Gmail-style folders**: Inbox, Sent, Drafts, Trash, Starred
- **Custom folders**: Create, list, and delete custom folders

### Search
- Search emails by subject, body, sender
- Filter by folder and flags (read/unread/starred)

### Admin Features
- **Domain Whitelist**: Mark domains as "safe" to prevent false positives in spam filtering
  - Add/remove domains
  - Add notes to each domain
  - Check whitelist status per domain
- **IP Blacklist View**: View and manage IPs blocked at the SMTP level
  - View blacklist statistics
  - Check if IP is blacklisted
  - Remove IPs from blacklist (if manually added)

## Technical Stack

- **Framework**: Flask + Jinja2 (server-side rendering)
- **Styling**: TailwindCSS via CDN
- **PWA**: manifest.json, service worker, mobile-first responsive design
- **Database**: PostgreSQL (client-side tables only)
- **API Integration**: RESTful API to mail server on `http://192.168.4.41:5003`
- **Security**: Server-side JWT storage, CSRF protection, XSS prevention via sandboxed iframe

## Setup Instructions

### 1. Prerequisites
- Python 3.12+
- PostgreSQL database
- Mail server running on port 5003

### 2. Installation

```bash
cd ~/git/py_pg_client
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Database Setup

The client uses a separate PostgreSQL database. Create it:

```bash
psql postgresql://postgres:not-a-real-password@localhost:5432/postgres -c "CREATE DATABASE mail_server_client;"
```

The tables will be created automatically on first run.

### 4. Configuration

Default configuration in `config.py`:
- Port: 5005
- Host: 192.168.4.41 (set via `HOST` env var)
- Mail Server API: `http://192.168.4.41:5003`
- Database: postgresql://postgres:not-a-real-password@localhost:5432/mail_server_client

To customize, set environment variables in `.env`:
```bash
HOST=192.168.4.41
DATABASE_URL="postgresql://user:pass@localhost:5432/mail_server_client"
MAIL_SERVER_API_URL="http://192.168.4.41:5003"
SECRET_KEY="your-secret-key"
FLASK_DEBUG="false"
```

### 5. Running the Application

```bash
source venv/bin/activate
python3 run.py
```

The application will be available at: http://192.168.4.41:5005

## Usage

### Login
- Navigate to http://192.168.4.41:5005
- Default user: the operator@example.com.au
- Password: (set in mail server)

### Email Operations
- **Compose**: Click "Compose" button, fill in To/Subject/Body, click Send
- **Read**: Click on email subject in inbox
- **Reply**: Open email, click Reply button
- **Forward**: Open email, click Forward button
- **Star**: Click star icon in email list or Star button in detail view
- **Delete**: Click trash icon or Delete button
- **Move**: Use dropdown in email detail view

### Folder Management
- Click "Manage Folders" in sidebar
- Create new folders
- Delete custom folders (system folders cannot be deleted)

### Domain Whitelist
1. Go to "Domain Whitelist" in sidebar
2. Enter domain name and optional notes
3. Click "Add to Whitelist"
4. View all whitelisted domains and remove as needed

### IP Blacklist
1. Go to "IP Blacklist" in sidebar
2. View blacklist statistics
3. Check if specific IP is blacklisted
4. Remove IPs from blacklist (manual entries only)

## Project Structure

```
~/git/py_pg_client/
├── app/
│   ├── __init__.py              # Flask app initialization
│   ├── api_client.py            # Mail server API wrapper
│   ├── db.py                    # Database connection
│   ├── config.py                # Configuration (moved from root)
│   ├── routes/
│   │   ├── auth.py              # Login/logout
│   │   ├── emails.py            # Inbox, compose, email actions
│   │   ├── folders.py           # Folder management
│   │   ├── whitelist.py         # Domain whitelist
│   │   └── blacklist.py         # IP blacklist view
│   ├── templates/               # Jinja2 HTML templates (mobile-first responsive)
│   │   ├── base.html            # Base layout with sidebar + bottom nav
│   │   ├── login.html           # Login page
│   │   ├── inbox.html           # Email list view
│   │   ├── email_detail.html    # Single email view (sandboxed iframe)
│   │   ├── compose.html         # Email composition
│   │   ├── folders.html         # Folder management
│   │   ├── whitelist.html       # Domain whitelist management
│   │   └── blacklist.html       # IP blacklist view
│   └── static/
│       ├── manifest.json        # PWA manifest
│       ├── sw.js                # Service worker
│       └── icons/               # PWA icons
├── config.py                    # Configuration
├── requirements.txt             # Python dependencies
├── run.py                       # Entry point
└── AGENTS.md                    # Project specifications
```

## Database Schema

### domain_whitelist
- `id` (SERIAL PRIMARY KEY)
- `domain` (VARCHAR 255, UNIQUE)
- `notes` (TEXT)
- `created_at` (TIMESTAMP)

### user_preferences (optional)
- `id` (SERIAL PRIMARY KEY)
- `user_email` (VARCHAR 255)
- `setting_name` (VARCHAR 100)
- `setting_value` (TEXT)

## API Integration

The client integrates with the mail server API:
- **Base URL**: http://192.168.4.41:5003
- **Authentication**: JWT Bearer token
- **Email Access Control**: Users can only see/access emails in folders they own (based on `folders.user_id`)
- **API Response Format**: `sender` and `recipient` are returned as `{email, name}` objects
- **Endpoints Used**:
  - `POST /auth/login` - User authentication
  - `GET /api/emails` - List emails
  - `GET /api/emails/<id>` - Get single email
  - `POST /api/emails` - Send email
  - `POST /api/emails/<id>/read` - Mark as read
  - `POST /api/emails/<id>/star` - Toggle star
  - `DELETE /api/emails/<id>` - Delete email
  - `POST /api/emails/<id>/move` - Move to folder
  - `GET /api/folders` - List folders
  - `POST /api/folders` - Create folder
  - `DELETE /api/folders/<id>` - Delete folder
  - `GET /api/search` - Search emails
  - `GET /api/blacklist/ip` - List blacklisted IPs
  - `DELETE /api/blacklist/ip/<id>` - Remove IP from blacklist
  - `GET /api/blacklist/stats` - Get blacklist statistics
  - `GET /api/blacklist/ip/check/<ip>` - Check if IP is blacklisted

## Security Considerations

1. **JWT Token Storage**: Tokens are stored server-side in Flask sessions, never exposed to client-side JavaScript
2. **Session Security**: Secure session cookies with HttpOnly flag
3. **XSS Prevention**: User input is escaped in templates using Jinja2 auto-escaping
4. **HTML Sanitization**: Email HTML bodies are rendered in a sandboxed iframe to prevent style leakage
5. **CSRF Protection**: Flask-WTF provides CSRF token protection for forms
6. **Input Validation**: All form inputs are validated before processing

## Testing

### Manual Testing Checklist
- [x] Login/logout works
- [x] Can view inbox with correct emails
- [x] Can open and read email
- [x] Can compose and send email
- [x] Reply and forward work
- [x] Star/unstar works
- [x] Mark read/unread works
- [x] Delete works
- [x] Can create custom folders
- [x] Can move emails between folders
- [x] Search works
- [x] Domain whitelist: add/remove/list works
- [x] Blacklist view shows data from server
- [x] Can remove IPs from blacklist
- [x] All actions have proper feedback

### Server Tests
All 133 mail server tests pass.

## Success Criteria

- [x] Runs on port 5005
- [x] Can login with the operator@example.com.au credentials
- [x] Can view inbox and read emails
- [x] Can compose and send emails
- [x] Can manage folders
- [x] Can search emails
- [x] Domain whitelist feature works
- [x] IP blacklist view works
- [x] Clean, Gmail-like UI
- [x] All 133 server tests still pass

## Troubleshooting

### Mail Server Not Running
```bash
cd ~/git/py_pg_email
source venv/bin/activate
python3 run.py
```

### Database Connection Issues
Verify PostgreSQL is running and database exists:
```bash
psql postgresql://postgres:not-a-real-password@localhost:5432/mail_server_client -c "\dt"
```

### Port Already in Use
Change port in `config.py` or kill existing process:
```bash
lsof -ti:5005 | xargs kill -9
```

## License

Internal use only - mailrelay email system.
