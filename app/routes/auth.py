from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app.api_client import MailServerAPI, AuthenticationError, APIError

auth_bp = Blueprint('auth', __name__)
api = MailServerAPI()

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        
        if not email or not password:
            flash('Email and password are required', 'error')
            return render_template('login.html', email=email)
        
        try:
            token, user = api.login(email, password)
            session['token'] = token
            session['user'] = user
            session.permanent = True
            return redirect(url_for('emails.inbox'))
        except AuthenticationError:
            flash('Invalid email or password', 'error')
        except APIError as e:
            flash(str(e), 'error')
    
    # Pre-fill with authorized user email
    return render_template('login.html', email='the operator@example.com.au')

@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('auth.login'))
