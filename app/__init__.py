import os
from flask import Flask, send_from_directory
from config import Config

def create_app():
    app = Flask(__name__, template_folder='templates', static_folder='static')
    app.config.from_object(Config)

    # Initialize database
    from app.db import init_db
    init_db()

    # Serve service worker at root for PWA scope
    @app.route('/sw.js')
    def service_worker():
        return send_from_directory(os.path.join(app.root_path, 'static'), 'sw.js',
                                  mimetype='application/javascript')

    from app.routes.auth import auth_bp
    from app.routes.emails import emails_bp
    from app.routes.folders import folders_bp
    from app.routes.whitelist import whitelist_bp
    from app.routes.blacklist import blacklist_bp
    from app.routes.blocklist import blocklist_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(emails_bp)
    app.register_blueprint(folders_bp)
    app.register_blueprint(whitelist_bp)
    app.register_blueprint(blacklist_bp)
    app.register_blueprint(blocklist_bp)
    
    # Register error handlers
    @app.errorhandler(404)
    def not_found_error(error):
        return "Page not found", 404
    
    @app.errorhandler(500)
    def internal_error(error):
        return "Internal server error", 500
    
    return app
