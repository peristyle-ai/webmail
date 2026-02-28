from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
from app.api_client import MailServerAPI, AuthenticationError, APIError, require_auth
import bleach
import re
import base64
from email import policy
from email.parser import BytesParser

emails_bp = Blueprint('emails', __name__)
api = MailServerAPI()

ALLOWED_TAGS = [
    'html', 'body', 'head', 'meta', 'title', 'link', 'style',
    'p', 'br', 'strong', 'em', 'u', 'a', 'ul', 'ol', 'li', 
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 
    'blockquote', 'pre', 'code',
    'table', 'thead', 'tbody', 'tfoot', 'tr', 'td', 'th', 'caption',
    'span', 'div', 'img', 
    'hr', 'sub', 'sup', 'small', 'mark',
    'article', 'section', 'header', 'footer', 'main', 'aside',
    'figure', 'figcaption',
    'font', 'center', 'nobr'
]
ALLOWED_ATTRIBUTES = {
    'body': ['style', 'bgcolor', 'text', 'link', 'vlink', 'alink'],
    'html': ['lang', 'xmlns'],
    'meta': ['charset', 'name', 'content', 'http-equiv'],
    'link': ['href', 'rel', 'type'],
    'style': ['type'],
    'a': ['href', 'title', 'target', 'rel', 'style', 'class'],
    'img': ['src', 'alt', 'width', 'height', 'style', 'class', 'border'],
    'table': ['width', 'cellpadding', 'cellspacing', 'border', 'style', 'class', 'bgcolor', 'align'],
    'td': ['colspan', 'rowspan', 'width', 'style', 'class', 'align', 'valign', 'bgcolor'],
    'th': ['colspan', 'rowspan', 'width', 'style', 'class', 'align', 'valign', 'bgcolor'],
    'tr': ['style', 'class', 'bgcolor', 'align', 'valign'],
    'div': ['style', 'class', 'align'],
    'span': ['style', 'class'],
    'p': ['style', 'class', 'align'],
    'h1': ['style', 'class', 'align'],
    'h2': ['style', 'class', 'align'],
    'h3': ['style', 'class', 'align'],
    'h4': ['style', 'class', 'align'],
    'h5': ['style', 'class', 'align'],
    'h6': ['style', 'class', 'align'],
    'blockquote': ['style', 'class'],
    'figure': ['style', 'class'],
    'figcaption': ['style', 'class'],
    'font': ['face', 'size', 'color', 'style'],
    'ul': ['style', 'class', 'type'],
    'ol': ['style', 'class', 'type', 'start'],
    'li': ['style', 'class'],
}

def parse_mime_body(body_content, content_type=None):
    """Parse MIME content and extract HTML/text body."""
    if not body_content:
        return '', ''
    
    if isinstance(body_content, str):
        body_bytes = body_content.encode('utf-8')
    else:
        body_bytes = body_content
    
    try:
        parser = BytesParser(policy=policy.default)
        msg = parser.parsebytes(body_bytes)
        
        if msg.is_multipart():
            html_body = ''
            text_body = ''
            
            for part in msg.walk():
                content_type_part = part.get_content_type()
                payload = part.get_payload(decode=True)
                
                if payload:
                    try:
                        decoded = payload.decode('utf-8', errors='replace')
                    except:
                        try:
                            decoded = payload.decode('latin-1', errors='replace')
                        except:
                            decoded = str(payload)
                    
                    if content_type_part == 'text/html' and not html_body:
                        html_body = decoded
                    elif content_type_part == 'text/plain' and not text_body:
                        text_body = decoded
            
            return html_body or text_body, html_body
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                try:
                    return payload.decode('utf-8', errors='replace'), ''
                except:
                    return str(payload), ''
            return '', ''
    except Exception as e:
        print(f"Error parsing MIME: {e}")
        return body_content, ''

def extract_sender_from_headers(headers):
    """Extract sender email from email headers"""
    if not headers:
        return None
    
    # Normalize line endings and handle multiline headers
    headers_normalized = headers.replace('\r\n', '\n').replace('\r', '\n')
    
    # Look for From: header - handle various formats:
    # From: Name <email@domain.com>
    # From: "Name" <email@domain.com>
    # From: email@domain.com
    # From: "Name"<email@domain.com> (no space)
    from_match = re.search(r'From:\s*(?:"?([^"<\n]+)"?\s*)?<?([^>\s\n]+@[^>\s\n]+)>?', headers_normalized)
    if from_match:
        email = from_match.group(2).strip() if from_match.group(2) else None
        name = from_match.group(1).strip() if from_match.group(1) else None
        if email:
            return {'email': email, 'name': name}
    
    # Try simpler pattern for just email anywhere in headers
    email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', headers_normalized)
    if email_match:
        return {'email': email_match.group(0), 'name': None}
    
    return None

@emails_bp.route('/')
@require_auth
def index():
    return redirect(url_for('emails.inbox'))

@emails_bp.route('/inbox')
@require_auth
def inbox():
    try:
        folder_id = request.args.get('folder_id', type=int)
        page = request.args.get('page', 1, type=int)
        limit = 20
        
        emails_data = api.get_emails(session['token'], folder_id=folder_id, page=page, limit=limit)
        folders_data = api.get_folders(session['token'])
        
        # Handle both list and dict responses
        if isinstance(emails_data, list):
            emails_list = emails_data
            total_emails = len(emails_data)
        else:
            emails_list = emails_data.get('emails', [])
            total_emails = emails_data.get('total', len(emails_list))
        
        # Handle folders response
        if isinstance(folders_data, list):
            folders_list = folders_data
        else:
            folders_list = folders_data.get('folders', [])
        
        # Enrich emails with sender info from headers
        for email in emails_list:
            if not email.get('sender') and email.get('headers'):
                sender = extract_sender_from_headers(email['headers'])
                if sender:
                    email['sender'] = sender
        
        # Get unread count
        unread_count = sum(1 for e in emails_list if not e.get('is_read'))
        
        return render_template('inbox.html', 
                             emails=emails_list,
                             folders=folders_list,
                             current_folder=folder_id,
                             page=page,
                             total=total_emails,
                             limit=limit,
                             unread_count=unread_count)
    except AuthenticationError:
        session.clear()
        flash('Session expired. Please log in again.', 'warning')
        return redirect(url_for('auth.login'))
    except APIError as e:
        flash(str(e), 'error')
        return render_template('inbox.html', emails=[], folders=[], current_folder=None, page=1, total=0, limit=20, unread_count=0)

@emails_bp.route('/emails/<int:email_id>')
@require_auth
def email_detail(email_id):
    try:
        email = api.get_email(session['token'], email_id)
        folders_data = api.get_folders(session['token'])
        
        # Handle folders response
        if isinstance(folders_data, list):
            folders_list = folders_data
        else:
            folders_list = folders_data.get('folders', [])
        
        # Enrich email with sender info from headers if missing
        if email and not email.get('sender') and email.get('headers'):
            sender = extract_sender_from_headers(email['headers'])
            if sender:
                email['sender'] = sender
        
        # Use HTML from API response (body_html field maps to 'html' in response)
        html_content = email.get('html') if email else None
        
        # Fallback to MIME parsing if no HTML from API
        if not html_content and email and email.get('body'):
            _, html_body = parse_mime_body(email.get('body', ''))
            html_content = html_body
        
        # Don't sanitize - preserve full styling for email rendering
        # Security: emails are external content, browsers handle safely
        if html_content:
            email['body_html'] = html_content
        
        return render_template('email_detail.html', 
                             email=email or {},
                             folders=folders_list)
    except AuthenticationError:
        session.clear()
        flash('Session expired. Please log in again.', 'warning')
        return redirect(url_for('auth.login'))
    except APIError as e:
        flash(str(e), 'error')
        return redirect(url_for('emails.inbox'))

@emails_bp.route('/compose', methods=['GET', 'POST'])
@require_auth
def compose():
    if request.method == 'POST':
        to = request.form.get('to', '').strip()
        subject = request.form.get('subject', '').strip()
        body = request.form.get('body', '').strip()
        
        if not to or not subject:
            flash('To and Subject are required', 'error')
            return render_template('compose.html', to=to, subject=subject, body=body)
        
        try:
            result = api.send_email(session['token'], to, subject, body)
            flash('Email sent successfully!', 'success')
            return redirect(url_for('emails.inbox'))
        except AuthenticationError:
            session.clear()
            flash('Session expired. Please log in again.', 'warning')
            return redirect(url_for('auth.login'))
        except APIError as e:
            flash(str(e), 'error')
            return render_template('compose.html', to=to, subject=subject, body=body)
    
    to = request.args.get('to', '')
    subject = request.args.get('subject', '')
    body = request.args.get('body', '')
    
    return render_template('compose.html', to=to, subject=subject, body=body)

def add_to_blocklist(email_address=None, domain=None):
    """Block sender or domain on mail server"""
    try:
        token = session.get('token')
        if token:
            api.block_sender(token, email=email_address, domain=domain)
    except Exception as e:
        print(f"Error blocking on server: {e}")

def get_sender_email_from_email_id(email_id):
    """Get sender email from an email by ID"""
    try:
        email = api.get_email(session['token'], email_id)
        if email:
            sender = email.get('sender')
            if sender and sender.get('email'):
                return sender['email']
    except:
        pass
    return None

@emails_bp.route('/emails/<int:email_id>/block-sender', methods=['POST'])
@require_auth
def block_sender(email_id):
    try:
        sender_email = get_sender_email_from_email_id(email_id)
        if sender_email:
            add_to_blocklist(email_address=sender_email)
            api.delete_email(session['token'], email_id)
            flash(f'Blocked sender: {sender_email}', 'success')
        else:
            flash('Could not determine sender email', 'error')
    except AuthenticationError:
        session.clear()
        flash('Session expired', 'warning')
        return redirect(url_for('auth.login'))
    except Exception as e:
        flash(str(e), 'error')
    return redirect(url_for('emails.inbox'))

@emails_bp.route('/emails/<int:email_id>/block-domain', methods=['POST'])
@require_auth
def block_domain(email_id):
    try:
        sender_email = get_sender_email_from_email_id(email_id)
        if sender_email and '@' in sender_email:
            domain = sender_email.split('@')[-1]
            add_to_blocklist(domain=domain)
            api.delete_email(session['token'], email_id)
            flash(f'Blocked domain: {domain}', 'success')
        else:
            flash('Could not determine sender domain', 'error')
    except AuthenticationError:
        session.clear()
        flash('Session expired', 'warning')
        return redirect(url_for('auth.login'))
    except Exception as e:
        flash(str(e), 'error')
    return redirect(url_for('emails.inbox'))

@emails_bp.route('/emails/bulk-block-sender', methods=['POST'])
@require_auth
def bulk_block_sender():
    email_ids_str = request.form.get('email_ids', '')
    if not email_ids_str:
        flash('No emails selected', 'error')
        return redirect(url_for('emails.inbox'))
    
    email_ids = [int(id) for id in email_ids_str.split(',') if id.isdigit()]
    if not email_ids:
        flash('Invalid selection', 'error')
        return redirect(url_for('emails.inbox'))
    
    blocked_senders = set()
    deleted_count = 0
    errors = []
    
    for email_id in email_ids:
        try:
            sender_email = get_sender_email_from_email_id(email_id)
            if sender_email:
                add_to_blocklist(email_address=sender_email)
                blocked_senders.add(sender_email)
            api.delete_email(session['token'], email_id)
            deleted_count += 1
        except AuthenticationError:
            session.clear()
            flash('Session expired', 'warning')
            return redirect(url_for('auth.login'))
        except Exception as e:
            errors.append(str(e))
    
    if blocked_senders:
        flash(f'Blocked {len(blocked_senders)} sender(s), deleted {deleted_count} email(s)', 'success')
    if errors:
        flash('Some errors: ' + '; '.join(errors), 'error')
    
    return redirect(url_for('emails.inbox'))

@emails_bp.route('/emails/bulk-block-domain', methods=['POST'])
@require_auth
def bulk_block_domain():
    email_ids_str = request.form.get('email_ids', '')
    if not email_ids_str:
        flash('No emails selected', 'error')
        return redirect(url_for('emails.inbox'))
    
    email_ids = [int(id) for id in email_ids_str.split(',') if id.isdigit()]
    if not email_ids:
        flash('Invalid selection', 'error')
        return redirect(url_for('emails.inbox'))
    
    blocked_domains = set()
    deleted_count = 0
    errors = []
    
    for email_id in email_ids:
        try:
            sender_email = get_sender_email_from_email_id(email_id)
            if sender_email and '@' in sender_email:
                domain = sender_email.split('@')[-1]
                add_to_blocklist(domain=domain)
                blocked_domains.add(domain)
            api.delete_email(session['token'], email_id)
            deleted_count += 1
        except AuthenticationError:
            session.clear()
            flash('Session expired', 'warning')
            return redirect(url_for('auth.login'))
        except Exception as e:
            errors.append(str(e))
    
    if blocked_domains:
        flash(f'Blocked {len(blocked_domains)} domain(s), deleted {deleted_count} email(s)', 'success')
    if errors:
        flash('Some errors: ' + '; '.join(errors), 'error')
    
    return redirect(url_for('emails.inbox'))

@emails_bp.route('/emails/<int:email_id>/reply')
@require_auth
def reply(email_id):
    try:
        email = api.get_email(session['token'], email_id)
        
        # Build reply
        to = email.get('sender', {}).get('email', '')
        subject = f"Re: {email.get('subject', '')}"
        if not subject.startswith('Re: '):
            subject = f"Re: {subject}"
        
        # Quote original
        quoted_body = f"\n\nOn {email.get('created_at', '')}, {email.get('sender', {}).get('email', '')} wrote:\n> {email.get('body', '').replace(chr(10), chr(10) + '> ')}"
        
        return redirect(url_for('emails.compose', to=to, subject=subject, body=quoted_body))
    except (AuthenticationError, APIError) as e:
        flash(str(e), 'error')
        return redirect(url_for('emails.email_detail', email_id=email_id))

@emails_bp.route('/emails/<int:email_id>/forward')
@require_auth
def forward(email_id):
    try:
        email = api.get_email(session['token'], email_id)
        
        # Build forward
        subject = f"Fw: {email.get('subject', '')}"
        if not subject.startswith('Fw: '):
            subject = f"Fw: {subject}"
        
        # Quote original
        quoted_body = f"\n\n---------- Forwarded message ----------\nFrom: {email.get('sender', {}).get('email', '')}\nDate: {email.get('created_at', '')}\nSubject: {email.get('subject', '')}\n\n{email.get('body', '')}"
        
        return redirect(url_for('emails.compose', subject=subject, body=quoted_body))
    except (AuthenticationError, APIError) as e:
        flash(str(e), 'error')
        return redirect(url_for('emails.email_detail', email_id=email_id))

@emails_bp.route('/emails/<int:email_id>/read', methods=['POST'])
@require_auth
def mark_read(email_id):
    try:
        api.mark_read(session['token'], email_id)
        flash('Email marked as read', 'success')
    except AuthenticationError:
        session.clear()
        flash('Session expired', 'warning')
    except APIError as e:
        flash(str(e), 'error')
    
    return redirect(request.referrer or url_for('emails.inbox'))

@emails_bp.route('/emails/<int:email_id>/star', methods=['POST'])
@require_auth
def toggle_star(email_id):
    try:
        result = api.toggle_star(session['token'], email_id)
        status = 'starred' if result.get('is_starred') else 'unstarred'
        flash(f'Email {status}', 'success')
    except AuthenticationError:
        session.clear()
        flash('Session expired', 'warning')
    except APIError as e:
        flash(str(e), 'error')
    
    return redirect(request.referrer or url_for('emails.inbox'))

@emails_bp.route('/emails/<int:email_id>/delete', methods=['POST'])
@require_auth
def delete_email(email_id):
    try:
        api.delete_email(session['token'], email_id)
        flash('Email deleted', 'success')
    except AuthenticationError:
        session.clear()
        flash('Session expired', 'warning')
    except APIError as e:
        flash(str(e), 'error')
    
    return redirect(url_for('emails.inbox'))

@emails_bp.route('/emails/bulk-delete', methods=['POST'])
@require_auth
def bulk_delete():
    email_ids_str = request.form.get('email_ids', '')
    if not email_ids_str:
        flash('No emails selected', 'error')
        return redirect(url_for('emails.inbox'))
    
    email_ids = [int(id) for id in email_ids_str.split(',') if id.isdigit()]
    if not email_ids:
        flash('Invalid selection', 'error')
        return redirect(url_for('emails.inbox'))
    
    deleted_count = 0
    errors = []
    for email_id in email_ids:
        try:
            api.delete_email(session['token'], email_id)
            deleted_count += 1
        except AuthenticationError:
            session.clear()
            flash('Session expired. Please log in again.', 'warning')
            return redirect(url_for('auth.login'))
        except APIError as e:
            errors.append(str(e))
    
    if deleted_count > 0:
        flash(f'{deleted_count} email(s) deleted', 'success')
    if errors:
        flash('Some emails could not be deleted: ' + '; '.join(errors), 'error')
    
    return redirect(url_for('emails.inbox'))

@emails_bp.route('/emails/<int:email_id>/move', methods=['POST'])
@require_auth
def move_email(email_id):
    folder_id = request.form.get('folder_id', type=int)
    if not folder_id:
        flash('Please select a folder', 'error')
        return redirect(request.referrer or url_for('emails.inbox'))
    
    try:
        api.move_email(session['token'], email_id, folder_id)
        flash('Email moved', 'success')
    except AuthenticationError:
        session.clear()
        flash('Session expired', 'warning')
    except APIError as e:
        flash(str(e), 'error')
    
    return redirect(request.referrer or url_for('emails.inbox'))

@emails_bp.route('/search')
@require_auth
def search():
    query = request.args.get('q', '').strip()
    if not query:
        return redirect(url_for('emails.inbox'))
    
    try:
        folder_id = request.args.get('folder_id', type=int)
        flag = request.args.get('flag')
        page = request.args.get('page', 1, type=int)
        limit = 20
        
        results = api.search_emails(session['token'], query, folder_id=folder_id, flag=flag, page=page, limit=limit)
        folders_data = api.get_folders(session['token'])
        
        # Handle both list and dict responses
        if isinstance(results, list):
            emails_list = results
            total_results = len(results)
        else:
            emails_list = results.get('emails', [])
            total_results = results.get('total', len(emails_list))
        
        # Handle folders response
        if isinstance(folders_data, list):
            folders_list = folders_data
        else:
            folders_list = folders_data.get('folders', [])
        
        return render_template('inbox.html',
                             emails=emails_list,
                             folders=folders_list,
                             current_folder=None,
                             page=page,
                             total=total_results,
                             limit=limit,
                             search_query=query,
                             is_search=True)
    except AuthenticationError:
        session.clear()
        flash('Session expired. Please log in again.', 'warning')
        return redirect(url_for('auth.login'))
    except APIError as e:
        flash(str(e), 'error')
        return redirect(url_for('emails.inbox'))
