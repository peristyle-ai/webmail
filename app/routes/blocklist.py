from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app.api_client import MailServerAPI, AuthenticationError, APIError, require_auth

blocklist_bp = Blueprint('blocklist', __name__)
api = MailServerAPI()

@blocklist_bp.route('/blocklist')
@require_auth
def list_blocklist():
    try:
        result = api.get_sender_blocklist(session['token'])
        if isinstance(result, list):
            entries = result
        else:
            entries = result.get('entries', [])
        return render_template('blocklist.html', entries=entries)
    except AuthenticationError:
        session.clear()
        flash('Session expired', 'warning')
        return redirect(url_for('auth.login'))
    except APIError as e:
        flash(f'Error loading blocklist: {str(e)}', 'error')
        return render_template('blocklist.html', entries=[])

@blocklist_bp.route('/blocklist/add', methods=['POST'])
@require_auth
def add_entry():
    email = request.form.get('email', '').strip().lower()
    domain = request.form.get('domain', '').strip().lower()
    
    if not email and not domain:
        flash('Email or domain is required', 'error')
        return redirect(url_for('blocklist.list_blocklist'))
    
    try:
        api.block_sender(session['token'], email=email or None, domain=domain or None)
        if email:
            flash(f'Blocked sender: {email}', 'success')
        if domain:
            flash(f'Blocked domain: {domain}', 'success')
    except AuthenticationError:
        session.clear()
        flash('Session expired', 'warning')
        return redirect(url_for('auth.login'))
    except APIError as e:
        flash(f'Error adding to blocklist: {str(e)}', 'error')
    
    return redirect(url_for('blocklist.list_blocklist'))

@blocklist_bp.route('/blocklist/<int:entry_id>/remove', methods=['POST'])
@require_auth
def remove_entry(entry_id):
    try:
        api.unblock_sender(session['token'], entry_id)
        flash('Removed from blocklist', 'success')
    except AuthenticationError:
        session.clear()
        flash('Session expired', 'warning')
        return redirect(url_for('auth.login'))
    except APIError as e:
        flash(f'Error removing entry: {str(e)}', 'error')
    
    return redirect(url_for('blocklist.list_blocklist'))
