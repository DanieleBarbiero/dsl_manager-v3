from fastapi.testclient import TestClient

from dslm3.web import create_app


def token(client):
    return client.get("/api/bootstrap").json()["token"]


def test_workspace_create_switch_isolation_and_forget(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    app = create_app(first)
    with TestClient(app) as client:
        headers = {"X-DSLM3-Token": token(client)}
        initial = client.get("/api/workspaces").json()
        first_id = initial["active_id"]
        assert len(initial["items"]) == 1

        created = client.post(
            "/api/workspaces",
            headers=headers,
            json={
                "operation": "create",
                "path": str(second),
                "name": "Secondo",
                "activate": True,
            },
        )
        assert created.status_code == 200, created.text
        second_id = created.json()["active_id"]
        assert second_id != first_id
        assert client.get("/api/status").json()["counts"]["sources"] == 0

        uploaded = client.post(
            "/api/upload",
            headers=headers,
            files={"files": ("b.sql", b"CREATE TABLE b(id INT);")},
        )
        assert uploaded.status_code == 200
        assert len(client.get("/api/sources").json()) == 1

        switched = client.post(
            "/api/workspaces",
            headers=headers,
            json={"operation": "switch", "id": first_id},
        )
        assert switched.status_code == 200
        assert client.get("/api/status").json()["counts"]["sources"] == 0

        back = client.post(
            "/api/workspaces",
            headers=headers,
            json={"operation": "switch", "id": second_id},
        )
        assert back.status_code == 200
        assert len(client.get("/api/sources").json()) == 1

        client.post(
            "/api/workspaces",
            headers=headers,
            json={"operation": "switch", "id": first_id},
        )
        forgotten = client.post(
            "/api/workspaces",
            headers=headers,
            json={"operation": "forget", "id": second_id},
        )
        assert forgotten.status_code == 200
        assert second.is_dir()
        assert all(x["id"] != second_id for x in forgotten.json()["items"])


def test_workspace_switch_is_blocked_while_job_is_active(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    app = create_app(first)
    with TestClient(app) as client:
        headers = {"X-DSLM3-Token": token(client)}
        created = client.post(
            "/api/workspaces",
            headers=headers,
            json={
                "operation": "create",
                "path": str(second),
                "name": "Secondo",
                "activate": False,
            },
        )
        second_id = next(
            x["id"] for x in created.json()["items"] if x["path"] == str(second.resolve())
        )
        app.state.jobs["TEST_BUSY"] = {
            "id": "TEST_BUSY",
            "workspace": str(first.resolve()),
            "status": "running",
        }
        blocked = client.post(
            "/api/workspaces",
            headers=headers,
            json={"operation": "switch", "id": second_id},
        )
        assert blocked.status_code == 409
        assert blocked.json()["reason"] == "workspace_busy"
        app.state.jobs.pop("TEST_BUSY")
