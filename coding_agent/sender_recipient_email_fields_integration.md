# Mail Server API: Sender/Recipient Email Fields - Integration Guide

## Overview

Add `sender_email` and `recipient_email` fields to the email API responses so the email client can display sender and recipient information without parsing headers.

## Current Problems

### Problem 1: Missing sender/recipient email fields

The `/api/emails` and `/api/emails/{id}` endpoints return:
```json
{
  "id": 416,
  "subject": "Test Email",
  "sender_id": 268,
  "recipient_id": 42,
  "headers": "From: sender@example.com\nTo: recipient@example.com\n...",
  "body": "...",
  ...
}
```

**Issues:**
- Client must parse `headers` to extract sender/recipient emails
- Some emails have `headers: null` (test emails, direct DB inserts)
- Inconsistent data - client may show "Unknown" for sender/recipient

### Problem 2: Folder filtering not working

The `/api/emails?folder_id=X` endpoint does not filter by folder correctly. It returns emails from ALL folders regardless of the `folder_id` parameter.

**Current workaround:** Client filters results client-side.

**Fix needed:** Mail server should filter emails by `folder_id` in the database query.

## Proposed Solution

Add `sender_email` and `recipient_email` fields to API responses:

```json
{
  "id": 416,
  "subject": "Test Email",
  "sender_id": 268,
  "sender_email": "sender@example.com",
  "recipient_id": 42,
  "recipient_email": "recipient@example.com",
  "headers": "...",
  "body": "...",
  ...
}
```

## Implementation

### Option 1: Extract at Query Time (Easiest)

Modify the API response formatting to extract emails from headers on-the-fly.

#### File: `app/routes/emails.py` (in py_pg_email)

Add helper functions:

```python
def extract_email_from_headers(headers, field='From'):
    """Extract email address from headers"""
    if not headers:
        return None
    
    import re
    
    # Normalize headers
    headers_normalized = headers.replace('\r\n', '\n').replace('\r', '\n')
    
    # Pattern: Field: Name <email> or Field: email
    pattern = rf'{field}:\s*(?:"?([^"<\n]+)"?\s*)?<?([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{{2,}})>?'
    match = re.search(pattern, headers_normalized, re.IGNORECASE)
    
    if match and match.group(2):
        return match.group(2).lower().strip()
    
    # Fallback: find any email in the field line
    field_match = re.search(rf'{field}:.*?([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{{2,}})', headers_normalized, re.IGNORECASE)
    if field_match:
        return field_match.group(1).lower().strip()
    
    return None

def format_email_response(email):
    """Add sender_email and recipient_email to email dict"""
    if isinstance(email, dict):
        email_dict = dict(email)
    else:
        email_dict = dict(email._asdict()) if hasattr(email, '_asdict') else dict(email)
    
    # Extract sender email from headers if not present
    if 'sender_email' not in email_dict or not email_dict.get('sender_email'):
        email_dict['sender_email'] = extract_email_from_headers(email_dict.get('headers'), 'From')
    
    # Extract recipient email from headers if not present
    if 'recipient_email' not in email_dict or not email_dict.get('recipient_email'):
        email_dict['recipient_email'] = extract_email_from_headers(email_dict.get('headers'), 'To')
    
    return email_dict
```

#### Update endpoints:

```python
@emails_bp.route('/emails', methods=['GET'])
@require_auth
def get_emails():
    # ... existing code to fetch emails ...
    
    # Format each email
    emails_formatted = [format_email_response(email) for email in emails]
    
    return jsonify({
        'emails': emails_formatted,
        'total': total,
        'page': page
    })

@emails_bp.route('/emails/<int:email_id>', methods=['GET'])
@require_auth
def get_email(email_id):
    # ... existing code to fetch email ...
    
    return jsonify(format_email_response(email))
```

### Option 2: Store at Insert Time (Better Performance)

Add columns to the `emails` table and extract emails when storing.

#### Database Migration: `db/add_sender_recipient_email.sql`

```sql
-- Add sender_email and recipient_email columns
ALTER TABLE emails ADD COLUMN IF NOT EXISTS sender_email VARCHAR(255);
ALTER TABLE emails ADD COLUMN IF NOT EXISTS recipient_email VARCHAR(255);

-- Create indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_emails_sender_email ON emails(sender_email);
CREATE INDEX IF NOT EXISTS idx_emails_recipient_email ON emails(recipient_email);

-- Backfill existing emails (optional, may take time for large tables)
UPDATE emails 
SET sender_email = SUBSTRING(headers FROM 'From:\s*(?:"?[^"<\n]+"?\s*)?<?([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})>?')
WHERE sender_email IS NULL AND headers IS NOT NULL;

UPDATE emails 
SET recipient_email = SUBSTRING(headers FROM 'To:\s*(?:"?[^"<\n]+"?\s*)?<?([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})>?')
WHERE recipient_email IS NULL AND headers IS NOT NULL;
```

#### Update schema: `db/schema.sql`

```sql
CREATE TABLE emails (
    id SERIAL PRIMARY KEY,
    sender_id INTEGER REFERENCES users(id),
    sender_email VARCHAR(255),  -- NEW
    recipient_id INTEGER REFERENCES users(id),
    recipient_email VARCHAR(255),  -- NEW
    subject TEXT,
    body TEXT,
    headers TEXT,
    ...
);
```

#### Update email storage: `smtp_server/email_storage.py`

```python
def store_email(self, sender, recipient, subject, body, headers):
    """Store email in database"""
    
    # Extract sender and recipient emails from headers
    sender_email = extract_email_from_headers(headers, 'From') or sender
    recipient_email = extract_email_from_headers(headers, 'To') or recipient
    
    cursor = self.conn.cursor()
    cursor.execute("""
        INSERT INTO emails (sender_id, sender_email, recipient_id, recipient_email, subject, body, headers, ...)
        VALUES (%s, %s, %s, %s, %s, %s, %s, ...)
        RETURNING id
    """, (sender_id, sender_email, recipient_id, recipient_email, subject, body, headers, ...))
    
    email_id = cursor.fetchone()[0]
    self.conn.commit()
    
    return email_id
```

## Recommended Approach

**Use Option 1 (extract at query time)** for immediate fix with zero downtime.

**Migrate to Option 2** later for better performance if needed.

## Testing

```bash
# Login
TOKEN=$(curl -s -X POST http://localhost:5003/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "the operator@example.com.au", "password": "not-a-real-password"}' | jq -r '.token')

# Get single email - should have sender_email and recipient_email
curl -H "Authorization: Bearer $TOKEN" http://localhost:5003/api/emails/416 | jq '{id, subject, sender_email, recipient_email}'

# Get email list - all should have sender_email and recipient_email
curl -H "Authorization: Bearer $TOKEN" "http://localhost:5003/api/emails?limit=5" | jq '.emails[] | {id, subject, sender_email, recipient_email}'
```

## Files to Modify

| File | Change |
|------|--------|
| `app/routes/emails.py` | Add `extract_email_from_headers()` and `format_email_response()` functions |
| `app/routes/emails.py` | Update `get_emails()` and `get_email()` to use `format_email_response()` |
| `db/schema.sql` | (Optional) Add `sender_email` and `recipient_email` columns |
| `db/add_sender_recipient_email.sql` | (Optional) New migration file |
| `smtp_server/email_storage.py` | (Optional) Extract and store emails at insert time |

## Client Changes (Already Done)

The email client (`py_pg_client`) already:
1. Uses `email.sender.email` in templates
2. Falls back to `email.recipient.email` 
3. Shows "Unknown" if not present
4. Has header parsing fallback in `extract_sender_from_headers()`

Once the mail server adds these fields, the client will automatically display them correctly.

## Benefits

1. **Reliable sender/recipient display** - No more "Unknown" when headers are missing
2. **Simpler client code** - No need to parse headers client-side
3. **Consistent data** - Email addresses extracted once at storage time
4. **Better performance** - Can index and query by sender_email/recipient_email
5. **Enables features** - Block sender, search by sender, filter by domain, etc.
