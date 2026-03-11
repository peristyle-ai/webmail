import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # Mail Server API
    MAIL_SERVER_API_URL = os.environ.get('MAIL_SERVER_API_URL') or 'http://localhost:5003'
    
    # Database
    DATABASE_URL = os.environ.get('DATABASE_URL') or 'postgresql://postgres:1234@localhost:5432/mail_server_client'
    
    # Flask
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    PORT = int(os.environ.get('PORT', 5005))
    HOST = os.environ.get('HOST', '127.0.0.1')
    
    # Session
    PERMANENT_SESSION_LIFETIME = 86400  # 24 hours, matching JWT token
    SESSION_COOKIE_SECURE = False  # Set to True in production with HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
