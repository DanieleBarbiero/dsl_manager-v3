import time
from fastapi.testclient import TestClient
from dslm3.web import create_app


def test_web_real_flow_and_local_security(tmp_path):
    app = create_app(tmp_path / "web")
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        assert "DSL Manager" in client.get("/").text
        token = client.get("/api/bootstrap").json()["token"]
        headers = {"X-DSLM3-Token": token}
        assert client.post("/api/action", json={"operation": "vega"}).status_code == 403
        assert (
            client.post(
                "/api/action",
                headers={**headers, "Origin": "https://evil.example"},
                json={"operation": "vega"},
            ).status_code
            == 403
        )
        assert (
            client.get(
                "/api/download", params={"path": "artifacts/../../project.json"}
            ).status_code
            == 400
        )
        fixture = tmp_path / "web" / "ai" / "outbox" / "windows-path.txt"
        fixture.parent.mkdir(parents=True, exist_ok=True)
        fixture.write_bytes(b"ok")
        downloaded = client.get(
            "/api/download", params={"path": r"ai\outbox\windows-path.txt"}
        )
        assert downloaded.status_code == 200
        assert downloaded.content == b"ok"

        assert (
            client.post(
                "/api/upload",
                headers=headers,
                files={"files": ("a.sql", b"CREATE TABLE a(id INT);")},
            ).status_code
            == 200
        )
        for op, args in [
            ("pipeline", {}),
            ("config", {"profile": "conservative"}),
            ("auto_review", {}),
            ("merge", {}),
            ("snapshot", {}),
        ]:
            response = client.post(
                "/api/action", headers=headers, json={"operation": op, "args": args}
            )
            assert response.status_code == 200
            job = response.json()["job_id"]
            for _ in range(300):
                value = client.get("/api/jobs/" + job).json()
                if value["status"] not in ["queued", "running"]:
                    break
                time.sleep(0.05)
            assert value["status"] == "success", value
        assert client.get("/api/status").json()["counts"]["effective_objects"] == 2
        snapshots = client.get("/api/snapshots").json()
        assert snapshots
        file = client.get(
            "/api/download", params={"path": f"artifacts/{snapshots[0]['id']}/dsl.json"}
        )
        assert (
            file.status_code == 200 and file.json()["metadata"]["counts"]["facts"] == 2
        )
        for path in [
            "sources",
            "evidence",
            "candidates",
            "knowledge",
            "temporal",
            "plans",
            "packages",
            "config",
            "runs",
        ]:
            assert client.get("/api/" + path).status_code == 200
