from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app.api_client import MailServerAPI, AuthenticationError, APIError
from app.rate_limiter import login_rate_limit, record_attempt, _get_client_ip

auth_bp = Blueprint('auth', __name__)
api = MailServerAPI()

@auth_bp.route('/login', methods=['GET', 'POST'])
@login_rate_limit
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        client_ip = _get_client_ip()
        
        if not email or not password:
            flash('Email and password are required', 'error')
            return render_template('login.html', email=email)
        
        try:
            token, user = api.login(email, password)
            record_attempt(client_ip, success=True)
            session['token'] = token
            session['user'] = user
            session.permanent = True
            response = redirect(url_for('emails.inbox'))
            response.set_cookie('last_email', email, max_age=365*24*60*60)
            return response
        except AuthenticationError:
            record_attempt(client_ip, success=False)
            flash('Invalid email or password', 'error')
        except APIError as e:
            record_attempt(client_ip, success=False)
            flash(str(e), 'error')
    
    email = request.cookies.get('last_email', '')
    return render_template('login.html', email=email)

@auth_bp.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out', 'info')
    return redirect(url_for('auth.login'))
