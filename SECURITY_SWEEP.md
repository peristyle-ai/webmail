# Security Sweep — py_pg_client (Email Client Web UI)

**Date:** 2026-09-15
**Scope:** Full security audit of the py_pg_client Flask web application
**Repository:** `/opt/py_pg_accounts_external/git/py_pg_client`
**Auditor:** Automated security review (Drycha)

---

## 1. Executive Summary

py_pg_client is a Flask-based web email client that serves as the front-end for the py_pg_email mail server. It provides a browser-based UI for reading, composing, and managing email, along with administrative interfaces for domain whitelisting, IP blacklisting, and sender blocklisting.

The client has undergone three dedicated security hardening passes (commits `4510f46`, `636de21`, `93a99f5`) addressing mixed-content exposure, XSS via email HTML injection, and transport-layer security. The current security posture is **reasonable for a single-user, self-hosted deployment** behind a Cloudflare Tunnel, but several gaps remain that should be addressed before any multi-user or internet-facing deployment.

**Key strengths:**
- No direct database access for email data — all operations proxied through the authenticated mail server API
- Sandboxed iframe rendering for email content with client-side HTML sanitization
- TLS verification on all upstream API connections
- Strong SECRET_KEY enforcement (no fallback)

**Key risks:**
- No CSRF protection on any form (Flask-WTF is in requirements but not used)
- `SESSION_COOKIE_SECURE = False` — session cookies sent over plain HTTP
- No Content Security Policy headers
- No rate limiting on the login endpoint
- Client-side HTML sanitizer is regex-based (not a full parser)
- Local database (whitelist/blocklist) uses raw SQL with string interpolation risk mitigated only by parameterized queries

---

## 2. Security Architecture Overview

### 2.1 Client-Server Relationship

```
Browser (HTTPS via Cloudflare Tunnel)
  │
  ▼
py_pg_client (Flask, port 5005, bound to 192.168.4.41)
  │  ├─ Server-side API calls (requests library, TLS-verified)
  │  └─ /api/* proxy blueprint (same-origin forwarding)
  ▼
py_pg_email (Flask API + SMTP, port 5003, HTTPS with self-signed cert)
  │
  ▼
PostgreSQL (mail_server database)
```

### 2.2 Trust Boundaries

| Boundary | Description | Trust Level |
|----------|-------------|-------------|
| Browser ↔ Client | HTTPS via Cloudflare Tunnel; session cookie auth | Untrusted input |
| Client ↔ Mail Server API | HTTPS with self-signed cert; JWT Bearer auth | Semi-trusted (same LAN) |
| Client ↔ Local PostgreSQL | Direct psycopg2 connection for whitelist/blocklist/preferences | Trusted (localhost) |
| Email Content | Arbitrary HTML from external senders | Fully untrusted |

### 2.3 Data Flow

1. **Authentication:** User submits credentials → client forwards to mail server `/auth/login` → receives JWT → stored in Flask session cookie
2. **Email retrieval:** Client makes server-side API calls using JWT from session → renders in templates
3. **Browser JS API calls:** `/api/*` proxy blueprint forwards to mail server, attaching JWT from session
4. **Admin operations:** Whitelist/blocklist routes use local PostgreSQL directly (not the mail server API)

---

## 3. Authentication & Session Management

### 3.1 Mechanism

- **Type:** Flask session-based (server-side signed cookies)
- **Token storage:** JWT from mail server stored in `session['token']`
- **Session lifetime:** 24 hours (`PERMANENT_SESSION_LIFETIME = 86400`), matching JWT expiry
- **Login route:** `/login` (GET/POST)
- **Logout route:** `/logout` — calls `session.clear()`

### 3.2 Session Cookie Configuration

| Setting | Value | Assessment |
|---------|-------|------------|
| `SESSION_COOKIE_SECURE` | `False` | ⚠️ **Risk** — cookie transmitted over HTTP. Should be `True` when served behind Cloudflare Tunnel (HTTPS). |
| `SESSION_COOKIE_HTTPONLY` | `True` | ✅ Prevents JavaScript access to session cookie |
| `SESSION_COOKIE_SAMESITE` | `'Lax'` | ✅ Mitigates CSRF on top-level navigation; does not protect against POST-based CSRF from same-site subdomains |
| `PERMANENT_SESSION_LIFETIME` | `86400` (24h) | ✅ Reasonable; matches JWT lifetime |

### 3.3 SECRET_KEY

- **Current:** 64-character random hex (rotated in commit `93a99f5`)
- **Previous:** `'dev-secret-key-change-in-production'` (hardcoded fallback — **removed**)
- **Enforcement:** `config.py` raises `RuntimeError` if `SECRET_KEY` is not set
- **Storage:** `.env` file (mode 600, excluded from git via `.gitignore`)

### 3.4 Route Protection

All protected routes use the `@require_auth` decorator (defined in `app/api_client.py`), which checks for `session['token']` and redirects to `/login` if absent. This covers:

- `/inbox`, `/emails/*`, `/threads/*`, `/compose`, `/search`
- `/folders/*`
- `/whitelist/*`, `/blacklist/*`, `/blocklist/*`
- `/api/*` (proxy blueprint returns 401 JSON if no session token)

### 3.5 Login Security Gaps

- **No rate limiting:** The `/login` endpoint accepts unlimited POST attempts. A brute-force attack against the mail server's `/auth/login` is possible through the client.
- **No CAPTCHA:** No challenge-response mechanism.
- **No account lockout:** Failed attempts are not tracked or throttled.
- **Password field:** Uses `autocomplete="current-password"` (correct) but no `minlength` or complexity requirements enforced client-side.

---

## 4. Transport Security

### 4.1 HTTPS & TLS Verification (Commit `93a99f5`)

**Before:** All API calls to the mail server were made over plain HTTP with no certificate verification.

**After:**
- `MAIL_SERVER_API_URL` updated to `https://192.168.4.41:5003`
- `_TLS_VERIFY` module-level constant in `api_client.py` controls certificate verification:
  - Reads `MAIL_SERVER_TLS_VERIFY` env var
  - Auto-discovers `../py_pg_email/certs/server.crt` (self-signed cert)
  - Falls back to system CA bundle if cert not found
  - Can be explicitly disabled with `MAIL_SERVER_TLS_VERIFY=false` (not recommended)
- All `requests.request()` calls pass `verify=_TLS_VERIFY`
- The `/api/*` proxy blueprint also passes `verify=_TLS_VERIFY` (added in same commit)

**Files changed:** `app/api_client.py`, `app/routes/api_proxy.py`, `config.py`

### 4.2 Mixed-Content Prevention (Commit `4510f46`)

**Problem:** When the client is served over HTTPS (via Cloudflare Tunnel), browser `fetch()` calls to the bare HTTP API (`http://192.168.4.41:5003/api/...`) are blocked as mixed content.

**Solution:** Same-origin proxy blueprint (`app/routes/api_proxy.py`):
- Catches all `GET/POST/PUT/PATCH/DELETE` under `/api/<path>`
- Forwards to `MAIL_SERVER_API_URL/api/<path>` with JWT from session
- Strips browser `Authorization` header — always uses session JWT
- Returns 401 if no session, 502 on upstream failure
- Only forwards safe headers (`Content-Type`, `Accept`, `If-Match`, `If-None-Match`)
- Only copies back safe response headers (`Content-Type`, `Cache-Control`, `ETag`, `Last-Modified`)
- Does NOT forward `Set-Cookie` from upstream (prevents session fixation)

### 4.3 Client TLS Termination

The client itself runs HTTP on port 5005. TLS is terminated at the Cloudflare Tunnel edge. This means:
- Traffic between browser and Cloudflare is encrypted
- Traffic between Cloudflare and the client is encrypted (Cloudflare Tunnel)
- Traffic between client and mail server is encrypted (HTTPS with self-signed cert)

---

## 5. Content Security

### 5.1 HTML Sanitization (Commit `636de21`)

**Mechanism:** Client-side JavaScript sanitizer (`window.sanitizeEmailHtml`) defined in `base.html` `<head>`, applied before injecting email HTML into sandboxed iframes via `srcdoc`.

**Removes:**
- `<script>...</script>` blocks (including self-closing and `src=` variants)
- Inline event handlers (`onclick=`, `onerror=`, `onload=`, `onmouseover=`, etc.)
- `javascript:` URLs in `href`, `src`, `action`, `formaction`, `cite`, `longdesc` attributes

**Used in:** `email_detail.html`, `thread_detail.html`

**Limitations:**
- Regex-based, not a full HTML parser — can be bypassed by malformed HTML, nested contexts, or novel attribute encodings
- Does not strip `<style>` blocks or CSS-based attacks (`expression()`, `url(javascript:...)` — though modern browsers ignore these)
- Does not sanitize SVG-based XSS vectors
- The `bleach` library is in `requirements.txt` and `ALLOWED_TAGS`/`ALLOWED_ATTRIBUTES` are defined in `emails.py`, but `bleach.clean()` is **not called** — server-side sanitization was removed in commit `dfa13ae` to preserve full email styling

### 5.2 Iframe Sandboxing

Email content is rendered in `<iframe>` elements with the `sandbox` attribute:

```
sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox"
```

**Allowed:**
- `allow-same-origin` — required for iframe resize measurement via `contentDocument.body.scrollHeight`
- `allow-popups` / `allow-popups-to-escape-sandbox` — allows links to open in new tabs (via `<base target="_blank">`)

**Blocked (implicitly):**
- `allow-scripts` — **not set**, so JavaScript execution is blocked inside the iframe
- `allow-forms` — form submission blocked
- `allow-modals` — `alert()`, `confirm()`, etc. blocked
- `allow-top-navigation` — cannot navigate the parent page

### 5.3 Template Auto-Escaping

Jinja2 auto-escaping is enabled by default for all templates. All user-controlled data rendered in templates (email subjects, sender names, folder names, flash messages) is automatically HTML-escaped unless explicitly marked `| safe`. No instances of `| safe` or `{% autoescape false %}` were found in the template codebase.

### 5.4 Content Security Policy

**No CSP headers are set.** The application does not use Flask-Talisman or set `Content-Security-Policy` headers manually. This means:
- No restriction on script sources (Tailwind CDN and Font Awesome CDN are loaded externally)
- No `frame-ancestors` directive (clickjacking protection absent)
- No `object-src`, `base-uri`, or `form-action` restrictions

---

## 6. API Security

### 6.1 Proxy Pattern

The `/api/*` proxy blueprint (`app/routes/api_proxy.py`) acts as a security gateway:

- **Authentication enforcement:** Returns 401 JSON if no session token exists
- **Authorization header control:** Strips any browser-supplied `Authorization` header; always injects the session JWT
- **Method whitelist:** Only `GET`, `POST`, `PUT`, `PATCH`, `DELETE` are forwarded; others return 405
- **Header filtering:** Only whitelisted request/response headers are forwarded
- **No redirect following:** `allow_redirects=False` prevents open-redirect via upstream
- **Timeout:** 30-second timeout on upstream requests

### 6.2 Server-Side API Client

The `MailServerAPI` class (`app/api_client.py`):
- All methods pass `verify=_TLS_VERIFY` for certificate validation
- `AuthenticationError` raised on 401 (triggers session clear + redirect to login)
- `APIError` raised on other HTTP errors
- JWT passed as `Bearer` token in `Authorization` header

### 6.3 Local Database Access

Three routes access the local PostgreSQL database directly (not through the mail server API):

- **Whitelist** (`app/routes/whitelist.py`): Domain whitelist CRUD
- **Blocklist** (`app/routes/blocklist.py`): Sender blocklist CRUD (via mail server API, not local DB)
- **Blacklist** (`app/routes/blacklist.py`): IP blacklist (via mail server API)

The local database (`app/db.py`) uses **parameterized queries** exclusively (`cursor.execute(query, params)`), which prevents SQL injection. The runtime database role (`py_pg_client_external_app`) has DML-only privileges — DDL operations (CREATE TABLE) are tolerated via `InsufficientPrivilege` exception handling (commit `42f999e`).

---

## 7. Known Issues & Mitigations

### 7.1 Active Issues

| # | Issue | Severity | Status | Mitigation |
|---|-------|----------|--------|------------|
| 1 | **No CSRF protection** | Medium | Open | Flask-WTF is in `requirements.txt` but not initialized. All state-changing forms (delete, move, block, compose) are vulnerable to cross-site request forgery. `SESSION_COOKIE_SAMESITE='Lax'` provides partial mitigation for top-level navigation but not for POST requests from same-site contexts. |
| 2 | **`SESSION_COOKIE_SECURE = False`** | Medium | Open | Session cookie is not marked `Secure`, meaning it can be transmitted over plain HTTP. Should be `True` when deployed behind HTTPS (Cloudflare Tunnel). |
| 3 | **No Content Security Policy** | Medium | Open | No CSP headers. Application loads external CDN resources (Tailwind, Font Awesome) without SRI hashes. Clickjacking protection absent. |
| 4 | **No login rate limiting** | Medium | Open | Unlimited login attempts. No CAPTCHA, lockout, or delay mechanism. |
| 5 | **Regex-based HTML sanitizer** | Low-Medium | Accepted | Client-side sanitizer uses regex, not a full HTML parser. Bypass possible with malformed HTML. Mitigated by iframe sandbox (no `allow-scripts`). |
| 6 | **No SRI on CDN resources** | Low | Open | Tailwind CSS and Font Awesome loaded from CDNs without Subresource Integrity hashes. A compromised CDN could inject malicious JS/CSS. |
| 7 | **Attachment download lacks TLS verify** | Low | Open | The `download_attachment` route in `emails.py` uses `requests.get()` without `verify=_TLS_VERIFY` (line: `response = req_lib.get(...)`). This is inconsistent with the rest of the codebase. |
| 8 | **Service worker caches pages** | Low | Accepted | `sw.js` caches `/`, `/inbox`, and `/static/manifest.json`. Authenticated pages are cached client-side. No sensitive data in cached responses beyond what the user already sees. Auth pages are excluded. |

### 7.2 Historical Issues (Resolved)

| # | Issue | Severity | Resolution | Commit |
|---|-------|----------|------------|--------|
| 1 | Hardcoded SECRET_KEY fallback | **Critical** | Removed fallback; raises `RuntimeError` if not set | `93a99f5` |
| 2 | Plain HTTP API connections | **High** | Updated to HTTPS; TLS cert verification on all requests | `93a99f5` |
| 3 | Mixed-content blocking | **High** | Same-origin `/api/*` proxy blueprint | `4510f46` |
| 4 | XSS via email HTML in srcdoc | **High** | Client-side sanitization + sandboxed iframe | `636de21` |
| 5 | Server-side bleach sanitization removed | Medium | Replaced by client-side sanitization + iframe sandbox (defense-in-depth) | `dfa13ae` → `636de21` |

---

## 8. Deployment Security Checklist

### 8.1 Pre-Deployment

- [ ] Set `SESSION_COOKIE_SECURE = True` in `config.py`
- [ ] Verify `SECRET_KEY` is a random 64+ character string (not the old dev key)
- [ ] Verify `MAIL_SERVER_API_URL` uses `https://`
- [ ] Verify `MAIL_SERVER_TLS_VERIFY` is not set to `false`
- [ ] Confirm `.env` file permissions are `600` and owned by the service user
- [ ] Confirm `.env` is in `.gitignore` (it is)
- [ ] Verify `FLASK_DEBUG = false` in `.env`

### 8.2 Recommended (Not Yet Implemented)

- [ ] Initialize Flask-WTF CSRF protection (`CSRFProtect(app)`)
- [ ] Add `Content-Security-Policy` header (at minimum: `default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com`)
- [ ] Add `X-Frame-Options: DENY` or `Content-Security-Policy: frame-ancestors 'none'`
- [ ] Add `X-Content-Type-Options: nosniff`
- [ ] Add `Referrer-Policy: strict-origin-when-cross-origin`
- [ ] Add rate limiting on `/login` (e.g., Flask-Limiter: 5 attempts per minute)
- [ ] Add SRI hashes to CDN `<script>` and `<link>` tags
- [ ] Fix `download_attachment` route to pass `verify=_TLS_VERIFY`
- [ ] Consider replacing regex-based `sanitizeEmailHtml` with DOMPurify (client-side, battle-tested)

### 8.3 Operational

- [ ] Run client via `systemctl --user` service (not manual `python run.py`)
- [ ] Monitor `journalctl --user -u email-client.service` for errors
- [ ] Rotate `SECRET_KEY` periodically (invalidates all sessions)
- [ ] Keep `requirements.txt` dependencies updated (especially `flask`, `requests`, `jinja2`)
- [ ] Review Cloudflare Tunnel configuration for appropriate access controls

---

## 9. Incident History

### 9.1 SECRET_KEY Exposure (Pre-`93a99f5`)

**Discovery:** During Phase D migration (2026-09-13), the SECRET_KEY was found to be the hardcoded string `'dev-secret-key-change-in-production'` — a well-known default that appears in Flask documentation and tutorials.

**Impact:** Anyone with knowledge of the default key could forge Flask session cookies, potentially impersonating any logged-in user without knowing their password.

**Resolution:** Rotated to a random 64-character hex string. `config.py` now raises `RuntimeError` at startup if `SECRET_KEY` is not set, preventing future fallback to a default.

### 9.2 Unencrypted API Communication (Pre-`93a99f5`)

**Discovery:** All API calls from the client to the mail server were made over plain HTTP (`http://192.168.4.41:5003`), exposing JWT tokens and email content to network sniffing on the LAN.

**Resolution:** Updated `MAIL_SERVER_API_URL` to `https://`, implemented `_TLS_VERIFY` with auto-discovery of the mail server's self-signed certificate, and added `verify=_TLS_VERIFY` to all `requests` calls.

### 9.3 Mixed-Content Blocking (Pre-`4510f46`)

**Discovery:** When the client was deployed behind Cloudflare Tunnel (HTTPS at the browser), JavaScript `fetch()` calls to the HTTP API were blocked by browsers as mixed content, rendering the thread-view bulk actions non-functional.

**Resolution:** Created the `/api/*` same-origin proxy blueprint, eliminating all browser-to-API direct HTTP calls.

### 9.4 XSS via Email HTML (Pre-`636de21`)

**Discovery:** Email HTML content was injected into sandboxed iframes via `srcdoc` without sanitization. While the iframe sandbox blocked script execution, browsers logged console warnings for every blocked `<script>` tag, and the attack surface remained for any future sandbox relaxation.

**Resolution:** Added `window.sanitizeEmailHtml()` client-side sanitizer that strips `<script>` blocks, inline event handlers, and `javascript:` URLs before `srcdoc` injection. The iframe sandbox remains as a second layer of defense.

---

## Appendix A: File Inventory (Security-Relevant)

| File | Role | Security Relevance |
|------|------|-------------------|
| `config.py` | Configuration | SECRET_KEY enforcement, session cookie settings |
| `app/api_client.py` | API client | TLS verification, JWT handling, auth decorator |
| `app/routes/api_proxy.py` | API proxy | Same-origin forwarding, header filtering, auth enforcement |
| `app/routes/auth.py` | Authentication | Login/logout, session management |
| `app/routes/emails.py` | Email routes | HTML sanitization constants, attachment handling, input validation |
| `app/templates/base.html` | Base template | `sanitizeEmailHtml()` definition, CDN resource loading |
| `app/templates/email_detail.html` | Email view | Iframe sandboxing, content injection |
| `app/templates/thread_detail.html` | Thread view | Iframe sandboxing, per-message content injection |
| `app/db.py` | Local database | Parameterized queries, connection management |
| `.env` | Environment | Secrets storage (SECRET_KEY, DATABASE_URL) |
| `app/static/sw.js` | Service worker | Caching strategy, auth page exclusion |

## Appendix B: Dependency Security

| Package | Version Constraint | Security Notes |
|---------|-------------------|----------------|
| `flask` | `>=2.0.0` | Session management, template auto-escaping |
| `requests` | `>=2.28.0` | TLS verification support |
| `psycopg2-binary` | `>=2.9.0` | Parameterized query support |
| `flask-wtf` | `>=1.0.0` | **Installed but not used** — CSRF protection available |
| `bleach` | `>=6.0.0` | **Installed but not used** — server-side sanitization removed in `dfa13ae` |
| `jinja2` | (via flask) | Auto-escaping enabled by default |
| `email-validator` | `>=1.3.0` | Available but not used for input validation |

---

*End of security sweep. This document should be updated after each security-relevant change to the codebase.*
