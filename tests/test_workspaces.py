from fastapi.testclient import TestClient

from dslm3.service import Application
from dslm3.web import create_app


def token(client):
    return client.get("/api/bootstrap").json()["token"]


def test_empty_workspaces_container_does_not_create_a_workspace(tmp_path):
    root = tmp_path / "workspaces"
    app = create_app(root)
    assert not root.exists()
    with TestClient(app) as client:
        bootstrap = client.get("/api/bootstrap").json()
        listed = client.get("/api/workspaces").json()
        assert bootstrap["workspace"] is None
        assert bootstrap["workspaces"] == str(root.resolve())
        assert listed["active_id"] is None
        assert listed["items"] == []
        assert not root.exists()


def test_create_without_activation_works_from_empty_container(tmp_path):
    root = tmp_path / "workspaces"
    target = tmp_path / "external"
    app = create_app(root)
    with TestClient(app) as client:
        headers = {"X-DSLM3-Token": token(client)}
        created = client.post(
            "/api/workspaces",
            headers=headers,
            json={
                "operation": "create",
                "path": str(target),
                "name": "External",
                "activate": False,
            },
        )
        assert created.status_code == 200, created.text
        assert created.json()["active_id"] is None
        assert created.json()["workspace"]["path"] == str(target.resolve())
        assert target.is_dir()
        assert not root.exists()


def test_existing_child_workspace_is_discovered_and_activated(tmp_path):
    root = tmp_path / "workspaces"
    vega = root / "vega"
    Application(vega)
    app = create_app(root)
    with TestClient(app) as client:
        bootstrap = client.get("/api/bootstrap").json()
        listed = client.get("/api/workspaces").json()
        assert bootstrap["workspace"] == str(vega.resolve())
        assert listed["active_id"] == listed["items"][0]["id"]
        assert listed["items"][0]["path"] == str(vega.resolve())
        assert listed["items"][0]["discovered"] is True
        assert client.get("/api/status").status_code == 200
        assert not (root / "registry.sqlite3").exists()
        assert not (root / "project.json").exists()


def test_workspace_create_switch_isolation_and_forget(tmp_path):
    root = tmp_path / "workspaces"
    first = root / "first"
    second = tmp_path / "external_second"
    Application(first)
    app = create_app(root)
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
    root = tmp_path / "workspaces"
    first = root / "first"
    second = tmp_path / "external_second"
    Application(first)
    app = create_app(root)
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
