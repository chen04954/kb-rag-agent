from fastapi.testclient import TestClient

from app.main import app


def test_authentication_flow_and_token_types(clean_database: None) -> None:
    credentials = {"email": "alice@example.com", "password": "correct-horse-123"}

    with TestClient(app) as client:
        signup = client.post("/api/v1/auth/signup", json=credentials)
        assert signup.status_code == 201
        assert signup.json()["email"] == credentials["email"]

        wrong_password = client.post(
            "/api/v1/auth/login",
            json={"email": credentials["email"], "password": "wrong-password"},
        )
        assert wrong_password.status_code == 401

        login = client.post("/api/v1/auth/login", json=credentials)
        assert login.status_code == 200
        tokens = login.json()
        assert tokens["token_type"] == "bearer"

        assert client.get("/api/v1/users/me").status_code == 401

        refresh_headers = {"Authorization": f"Bearer {tokens['refresh_token']}"}
        assert (
            client.get("/api/v1/users/me", headers=refresh_headers).status_code
            == 401
        )

        refreshed = client.get(
            "/api/v1/auth/refresh-token", headers=refresh_headers
        )
        assert refreshed.status_code == 200
        assert refreshed.json()["access_token"]

        access_headers = {"Authorization": f"Bearer {tokens['access_token']}"}
        me = client.get("/api/v1/users/me", headers=access_headers)
        assert me.status_code == 200
        assert me.json()["email"] == credentials["email"]

        logout = client.get("/api/v1/auth/logout", headers=access_headers)
        assert logout.status_code == 200
