import sys
sys.path.insert(0, '/opt/py_pg_accounts/git/py_pg_client')

import pytest
import requests
from config import Config

class TestConnectivity:
    def test_mail_server_reachable(self):
        """Test that the mail server API is reachable."""
        response = requests.get(f"{Config.MAIL_SERVER_API_URL}/health", timeout=5)
        assert response.status_code == 200
        print(f"Mail server is reachable at {Config.MAIL_SERVER_API_URL}")

    def test_mail_server_login_endpoint_exists(self):
        """Test that the login endpoint exists."""
        response = requests.post(
            f"{Config.MAIL_SERVER_API_URL}/auth/login",
            json={"email": "test@test.com", "password": "test"},
            timeout=5
        )
        # Should return 401 (invalid credentials) not 404 (not found)
        assert response.status_code == 401
        print("Login endpoint exists and responds correctly")
