#!/usr/bin/env python3
import sys
sys.path.insert(0, '/opt/py_pg_accounts_external/git/py_pg_client')

from app import create_app
from config import Config

app = create_app()

if __name__ == '__main__':
    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG)
