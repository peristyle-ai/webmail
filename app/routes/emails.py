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
    
    headers_normalized = headers.replace('\r\n', '\n').replace('\r', '\n')
    
    # Pattern 1: From: "Name" <email> or From: Name <email>
    from_match = re.search(r'From:\s*"([^"]+)"\s*<([^>]+)>', headers_normalized)
    if from_match:
        return {'email': from_match.group(2).strip(), 'name': from_match.group(1).strip()}
    
    # Pattern 2: From: Name <email> (no quotes)
    from_match = re.search(r'From:\s*([^<\n]+?)\s*<([^>]+)>', headers_normalized)
    if from_match:
        return {'email': from_match.group(2).strip(), 'name': from_match.group(1).strip()}
    
    # Pattern 3: From: <email> or From: email (no name)
    from_match = re.search(r'From:\s*<?([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})>?', headers_normalized, re.IGNORECASE)
    if from_match:
        return {'email': from_match.group(1).strip(), 'name': None}
    
    # Fallback: find first email in headers
    email_match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', headers_normalized)
    if email_match:
        return {'email': email_match.group(0), 'name': None}
    
    return None

def extract_recipient_from_headers(headers):
    """Extract recipient email from email headers"""
    if not headers:
        return None
    
    headers_normalized = headers.replace('\r\n', '\n').replace('\r', '\n')
    
    # Pattern 1: To: "Name" <email>
    to_match = re.search(r'To:\s*"([^"]+)"\s*<([^>]+)>', headers_normalized)
    if to_match:
        return {'email': to_match.group(2).strip(), 'name': to_match.group(1).strip()}
    
    # Pattern 2: To: Name <email> (no quotes)
    to_match = re.search(r'To:\s*([^<\n]+?)\s*<([^>]+)>', headers_normalized)
    if to_match:
        return {'email': to_match.group(2).strip(), 'name': to_match.group(1).strip()}
    
    # Pattern 3: To: <email> or To: email (no name)
    to_match = re.search(r'To:\s*<?([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})>?', headers_normalized, re.IGNORECASE)
    if to_match:
        return {'email': to_match.group(1).strip(), 'name': None}
    
    return None

@emails_bp.route('/')
@require_auth
def index():
    return redirect(url_for('emails.inbox'))

@emails_bp.route('/inbox')
@require_auth
def inbox():
    try:
        folder = request.args.get('folder')
        page = request.args.get('page', 1, type=int)
        limit = 20
        
        folders_data = api.get_folders(session['token'])
        if isinstance(folders_data, dict):
            folders_list = folders_data.get('folders', [])
        else:
            folders_list = folders_data
        
        if not folder:
            folder = 'Inbox'
        
        session['current_folder'] = folder
        
        emails_data = api.get_emails(session['token'], folder=folder, page=1, limit=1000)
        
        if isinstance(emails_data, list):
            all_emails = emails_data
        else:
            all_emails = emails_data.get('emails', [])
        
        total_emails = len(all_emails)
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        emails_list = all_emails[start_idx:end_idx]
        
        for email in emails_list:
            if not email.get('sender') and email.get('headers'):
                sender = extract_sender_from_headers(email['headers'])
                if sender:
                    email['sender'] = sender
        
        unread_count = sum(1 for e in emails_list if not e.get('is_read'))
        
        return render_template('inbox.html', 
                             emails=emails_list,
                             folders=folders_list,
                             current_folder=folder,
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
        return redirect(url_for('emails.inbox'))

@emails_bp.route('/emails/<int:email_id>')
@require_auth
def email_detail(email_id):
    try:
        email = api.get_email(session['token'], email_id)
        folders_data = api.get_folders(session['token'])
        
        if isinstance(folders_data, list):
            folders_list = folders_data
        else:
            folders_list = folders_data.get('folders', [])
        
        if email and not email.get('sender') and email.get('headers'):
            sender = extract_sender_from_headers(email['headers'])
            if sender:
                email['sender'] = sender
        
        if email and not email.get('recipient') and email.get('headers'):
            recipient = extract_recipient_from_headers(email['headers'])
            if recipient:
                email['recipient'] = recipient
        
        html_content = email.get('html') if email else None

        if not html_content and email and email.get('body'):
            _, html_body = parse_mime_body(email.get('body', ''))
            html_content = html_body

        if html_content:
            email['body_html'] = html_content
        
        attachments = []
        try:
            attachments_data = api.get_attachments(session['token'], email_id)
            if isinstance(attachments_data, list):
                attachments = attachments_data
        except APIError:
            pass
        
        return render_template('email_detail.html', 
                             email=email or {},
                             folders=folders_list,
                             attachments=attachments)
    except AuthenticationError:
        session.clear()
        flash('Session expired. Please log in again.', 'warning')
        return redirect(url_for('auth.login'))
    except APIError as e:
        flash(str(e), 'error')
        return redirect(url_for('emails.inbox'))

@emails_bp.route('/attachments/<int:attachment_id>')
@require_auth
def download_attachment(attachment_id):
    try:
        import requests as req_lib
        headers = {'Authorization': f'Bearer {session["token"]}'}
        response = req_lib.get(
            f'{api.base_url}/api/attachments/{attachment_id}',
            headers=headers,
            stream=True
        )
        if response.status_code == 200:
            content_disp = response.headers.get('Content-Disposition', '')
            if 'filename="' in content_disp:
                start = content_disp.index('filename="') + len('filename="')
                end = content_disp.index('"', start)
                filename = content_disp[start:end]
            elif 'filename=' in content_disp:
                start = content_disp.index('filename=') + len('filename=')
                rest = content_disp[start:]
                filename = rest.split(';')[0].strip().strip('"\'')
            content_type = response.headers.get('Content-Type', 'application/octet-stream')
            from flask import Response
            from urllib.parse import quote
            encoded_filename = quote(filename)
            return Response(
                response.iter_content(chunk_size=8192),
                content_type=content_type,
                headers={
                    'Content-Disposition': f"attachment; filename=\"{filename}\"; filename*=UTF-8''{encoded_filename}"
                }
            )
        else:
            flash('Attachment not available for download', 'error')
            return redirect(request.referrer or url_for('emails.inbox'))
    except Exception as e:
        flash(f'Error downloading attachment: {str(e)}', 'error')
        return redirect(request.referrer or url_for('emails.inbox'))

@emails_bp.route('/compose', methods=['GET', 'POST'])
@require_auth
def compose():
    forwarded_attachments = []

    if request.method == 'POST':
        to = request.form.get('to', '').strip()
        cc = request.form.get('cc', '').strip()
        subject = request.form.get('subject', '').strip()
        body = request.form.get('body', '').strip()
        files = request.files.getlist('attachments')
        forward_email_id = request.form.get('forward_email_id', '').strip()

        if forward_email_id:
            try:
                forwarded_attachments = api.get_attachments(session['token'], int(forward_email_id)) or []
            except Exception:
                forwarded_attachments = []

        if not to or not subject:
            flash('To and Subject are required', 'error')
            return render_template(
                'compose.html',
                to=to,
                cc=cc,
                subject=subject,
                body=body,
                forward_email_id=forward_email_id,
                forwarded_attachments=forwarded_attachments,
            )

        try:
            result = api.send_email(session['token'], to, subject, body, cc=cc or None)
            email_id = result.get('id') if result else None
            forward_copy_failed = False

            if email_id and files:
                for f in files:
                    if f and f.filename:
                        try:
                            api.upload_attachment(session['token'], email_id, f)
                        except Exception:
                            pass

            if email_id and forward_email_id:
                for attachment in forwarded_attachments:
                    attachment_id = attachment.get('id')
                    if not attachment_id:
                        continue
                    try:
                        api.copy_attachment(session['token'], attachment_id, email_id)
                    except Exception:
                        forward_copy_failed = True

            if forward_copy_failed:
                flash('Email sent, but one or more forwarded attachments could not be copied.', 'warning')
            else:
                flash('Email sent successfully!', 'success')
            return redirect(url_for('emails.inbox'))
        except AuthenticationError:
            session.clear()
            flash('Session expired. Please log in again.', 'warning')
            return redirect(url_for('auth.login'))
        except APIError as e:
            flash(str(e), 'error')
            return render_template(
                'compose.html',
                to=to,
                cc=cc,
                subject=subject,
                body=body,
                forward_email_id=forward_email_id,
                forwarded_attachments=forwarded_attachments,
            )

    to = request.args.get('to', '')
    cc = request.args.get('cc', '')
    subject = request.args.get('subject', '')
    body = request.args.get('body', '')
    forward_email_id = request.args.get('forward_email_id', '').strip()

    if forward_email_id:
        try:
            forwarded_attachments = api.get_attachments(session['token'], int(forward_email_id)) or []
        except Exception:
            forwarded_attachments = []

    return render_template(
        'compose.html',
        to=to,
        cc=cc,
        subject=subject,
        body=body,
        forward_email_id=forward_email_id,
        forwarded_attachments=forwarded_attachments,
    )

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
            # Try sender object first
            sender = email.get('sender')
            if sender and sender.get('email'):
                return sender['email']
            # Fallback: extract from headers
            if email.get('headers'):
                sender = extract_sender_from_headers(email['headers'])
                if sender and sender.get('email'):
                    return sender['email']
            # Last resort: use raw headers string to find From
            headers = email.get('headers', '')
            if headers and 'From:' in headers:
                import re
                from_match = re.search(r'From:\s*(?:"?[^"<\n]+"?\s*)?<?([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})>?', headers, re.IGNORECASE)
                if from_match:
                    return from_match.group(1).lower()
    except Exception as e:
        print(f"Error getting sender: {e}")
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
            flash(f'Cannot block: email {email_id} has no sender info (headers may be missing)', 'error')
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
        elif sender_email:
            flash(f'Cannot block domain: sender email has no @ symbol', 'error')
        else:
            flash(f'Cannot block: email {email_id} has no sender info (headers may be missing)', 'error')
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

@emails_bp.route('/emails/bulk-move', methods=['POST'])
@require_auth
def bulk_move():
    email_ids_str = request.form.get('email_ids', '')
    folder_id = request.form.get('folder_id', type=int)
    
    if not email_ids_str:
        flash('No emails selected', 'error')
        return redirect(url_for('emails.inbox'))
    
    if not folder_id:
        flash('Please select a folder', 'error')
        return redirect(url_for('emails.inbox'))
    
    email_ids = [int(id) for id in email_ids_str.split(',') if id.isdigit()]
    if not email_ids:
        flash('Invalid selection', 'error')
        return redirect(url_for('emails.inbox'))
    
    moved_count = 0
    errors = []
    
    for email_id in email_ids:
        try:
            api.move_email(session['token'], email_id, folder_id)
            moved_count += 1
        except AuthenticationError:
            session.clear()
            flash('Session expired', 'warning')
            return redirect(url_for('auth.login'))
        except Exception as e:
            errors.append(str(e))
    
    if moved_count > 0:
        flash(f'Moved {moved_count} email(s)', 'success')
    if errors:
        flash('Some emails could not be moved: ' + '; '.join(errors), 'error')
    
    return redirect(url_for('emails.inbox'))

@emails_bp.route('/emails/<int:email_id>/reply')
@require_auth
def reply(email_id):
    try:
        email = api.get_email(session['token'], email_id)
        
        if not email:
            flash('Email not found', 'error')
            return redirect(url_for('emails.inbox'))
        
        # Extract sender from headers if not in response
        if not email.get('sender') and email.get('headers'):
            sender = extract_sender_from_headers(email['headers'])
            if sender:
                email['sender'] = sender
        
        # Build reply
        to = email.get('sender', {}).get('email', '') if email.get('sender') else ''
        subject = email.get('subject', '')
        if subject and not subject.startswith('Re: '):
            subject = f"Re: {subject}"
        elif not subject:
            subject = "Re: (No subject)"
        
        # Quote original
        from app import format_datetime
        sender_email = email.get('sender', {}).get('email', 'Unknown') if email.get('sender') else 'Unknown'
        sent_at = format_datetime(email.get('created_at', '')) or email.get('created_at', '')
        body_text = email.get('body', '')
        quoted_body = f"\n\nOn {sent_at}, {sender_email} wrote:\n> {body_text.replace(chr(10), chr(10) + '> ')}"
        
        return redirect(url_for('emails.compose', to=to, subject=subject, body=quoted_body))
    except AuthenticationError:
        session.clear()
        flash('Session expired', 'warning')
        return redirect(url_for('auth.login'))
    except APIError as e:
        flash(str(e), 'error')
        return redirect(url_for('emails.inbox'))

@emails_bp.route('/emails/<int:email_id>/forward')
@require_auth
def forward(email_id):
    try:
        email = api.get_email(session['token'], email_id)
        
        # Build forward
        subject = email.get('subject', '')
        if not subject.startswith('Fw: '):
            subject = f"Fw: {subject}"
        
        # Quote original
        quoted_body = f"\n\n---------- Forwarded message ----------\nFrom: {email.get('sender', {}).get('email', '')}\nDate: {email.get('created_at', '')}\nSubject: {email.get('subject', '')}\n\n{email.get('body', '')}"
        
        return redirect(url_for('emails.compose', subject=subject, body=quoted_body, forward_email_id=email_id))
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
        
        # Enrich emails with sender info from headers
        for email in emails_list:
            if not email.get('sender') and email.get('headers'):
                sender = extract_sender_from_headers(email['headers'])
                if sender:
                    email['sender'] = sender
        
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
