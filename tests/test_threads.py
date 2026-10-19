from fastapi.testclient import TestClient


def _register_and_login(client: TestClient, email: str) -> dict[str, str]:
    credentials = {"email": email, "password": "correct-horse-123"}
    assert client.post("/api/v1/auth/signup", json=credentials).status_code == 201
    response = client.post("/api/v1/auth/login", json=credentials)
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _create_kb(client: TestClient, headers: dict[str, str], name: str = "KB") -> str:
    created = client.post(
        "/api/v1/knowledge-bases/",
        json={"name": name, "description": ""},
        headers=headers,
    )
    assert created.status_code == 201
    return created.json()["id"]


def test_threads_are_private_and_support_crud(clean_database: None) -> None:
    from app.main import app

    with TestClient(app) as client:
        alice_headers = _register_and_login(client, "alice@example.com")
        bob_headers = _register_and_login(client, "bob@example.com")
        alice_kb = _create_kb(client, alice_headers, "Alice KB")
        bob_kb = _create_kb(client, bob_headers, "Bob KB")

        alice_created = client.post(
            "/api/v1/threads/",
            json={"title": "Alice handbook", "knowledge_base_id": alice_kb},
            headers=alice_headers,
        )
        bob_created = client.post(
            "/api/v1/threads/",
            json={"title": "Bob handbook", "knowledge_base_id": bob_kb},
            headers=bob_headers,
        )
        assert alice_created.status_code == 201
        assert bob_created.status_code == 201
        alice_id = alice_created.json()["id"]
        bob_id = bob_created.json()["id"]
        assert alice_created.json()["knowledge_base_id"] == alice_kb

        alice_list = client.get(
            f"/api/v1/threads/?knowledge_base_id={alice_kb}",
            headers=alice_headers,
        )
        assert alice_list.status_code == 200
        listed_ids = {item["id"] for item in alice_list.json()}
        assert alice_id in listed_ids
        assert bob_id not in listed_ids

        assert (
            client.get(f"/api/v1/threads/{bob_id}", headers=alice_headers).status_code
            == 404
        )
        assert (
            client.patch(
                f"/api/v1/threads/{bob_id}",
                json={"title": "stolen"},
                headers=alice_headers,
            ).status_code
            == 404
        )
        assert (
            client.delete(
                f"/api/v1/threads/{bob_id}", headers=alice_headers
            ).status_code
            == 404
        )

        updated = client.patch(
            f"/api/v1/threads/{alice_id}",
            json={"title": "Updated title"},
            headers=alice_headers,
        )
        assert updated.status_code == 200
        assert updated.json()["title"] == "Updated title"

        deleted = client.delete(
            f"/api/v1/threads/{alice_id}", headers=alice_headers
        )
        assert deleted.status_code == 204
        assert (
            client.get(
                f"/api/v1/threads/{alice_id}", headers=alice_headers
            ).status_code
            == 404
        )
