from unittest.mock import patch

from fastapi.testclient import TestClient

from app.infrastructure.auth import hash_password, reset_admin_password, verify_password


def test_password_hash_is_salted_and_verifiable():
    first = hash_password("correct horse battery staple")
    second = hash_password("correct horse battery staple")

    assert first != second
    assert verify_password("correct horse battery staple", first)
    assert not verify_password("incorrect password", first)


def test_first_run_setup_login_boundary_and_logout():
    import app.main  # noqa: F401
    from nicegui import app

    with patch("app.infrastructure.auth.get_auth_key", return_value=b"a" * 32):
        anonymous = TestClient(app)
        try:
            login_page = anonymous.get("/login")
            assert login_page.status_code == 200
            assert "Create recruiter account" in login_page.text
            assert login_page.text.count('data-password-toggle=') == 2
            assert 'data-password-toggle="password"' in login_page.text
            assert 'data-password-toggle="confirm"' in login_page.text

            protected_page = anonymous.get("/hunts", follow_redirects=False)
            assert protected_page.status_code == 303
            assert protected_page.headers["location"].startswith("/login?next=")

            protected_api = anonymous.get("/api/tts/voices")
            assert protected_api.status_code == 401

            setup = anonymous.post(
                "/auth/setup",
                json={"username": "recruiter", "password": "a secure local password"},
            )
            assert setup.status_code == 200
            assert setup.cookies.get("talenthunt_session")

            authorized_api = anonymous.get("/api/tts/voices")
            assert authorized_api.status_code == 200

            duplicate_setup = anonymous.post(
                "/auth/setup",
                json={"username": "other-admin", "password": "another secure password"},
            )
            assert duplicate_setup.status_code == 400

            logout = anonymous.get("/auth/logout", follow_redirects=False)
            assert logout.status_code == 303
            assert logout.headers["location"] == "/login"
        finally:
            anonymous.close()

        login_client = TestClient(app)
        try:
            login_page = login_client.get("/login")
            assert login_page.text.count('data-password-toggle=') == 1
            assert 'data-password-toggle="password"' in login_page.text
            assert "Forgot password?" in login_page.text
            assert "python -m app.infrastructure.password_recovery" in login_page.text

            failed = login_client.post(
                "/auth/login",
                json={"username": "recruiter", "password": "wrong password value"},
            )
            assert failed.status_code == 401

            success = login_client.post(
                "/auth/login",
                json={"username": "recruiter", "password": "a secure local password"},
            )
            assert success.status_code == 200
            assert login_client.get("/api/tts/voices").status_code == 200

            reset_ok, _ = reset_admin_password("a replacement local password")
            assert reset_ok
            assert login_client.post(
                "/auth/login",
                json={"username": "recruiter", "password": "a secure local password"},
            ).status_code == 401
            assert login_client.post(
                "/auth/login",
                json={"username": "recruiter", "password": "a replacement local password"},
            ).status_code == 200
        finally:
            login_client.close()
