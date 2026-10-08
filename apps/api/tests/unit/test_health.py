from fastapi.testclient import TestClient

from lung.main import create_app


def test_health_returns_ok() -> None:
    client = TestClient(create_app())
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
