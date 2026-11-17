from fastapi.testclient import TestClient
import pytest
from options_demo.app import create_app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    monkeypatch.setenv("OPTIONS_SOURCE", "synthetic")
    with TestClient(create_app()) as c:
        yield c


def test_chat_report_and_followup(client):
    response = client.post("/api/chat", json={"message": "flow AAPL"})
    assert response.status_code == 200
    data = response.json()
    assert data["report"]["symbol"] == "AAPL"
    followup = client.post("/api/chat", json={"message": "why", "report_id": data["report_id"]})
    assert followup.status_code == 200
    assert "highest-scoring" in followup.json()["text"]
    assert "report" not in followup.json()


def test_local_boundaries(client):
    assert client.post("/api/chat", json={"message": "AAPL"}, headers={"Origin": "https://example.com"}).status_code == 403
    assert client.post("/api/chat", content="message=AAPL").status_code == 415
    assert client.get("/", headers={"Host": "attacker.test"}).status_code == 400
    assert client.get("/").headers["x-frame-options"] == "DENY"


def test_bad_requests_and_missing_report(client):
    assert client.post("/api/chat", json={"message": "../file"}).status_code == 400
    assert client.post("/api/chat", json={"message": "AAPL", "scenario": "live"}).status_code == 422
    assert client.post("/api/chat", json={"message": "quality"}).status_code == 400
    assert client.post("/api/chat", json={"message": "help"}).status_code == 200


def test_no_broker_details_in_failures(client, monkeypatch):
    def fail(*args):
        raise RuntimeError("private account detail")
    monkeypatch.setattr("options_demo.app.analyze", fail)
    response = client.post("/api/chat", json={"message": "AAPL"})
    assert response.status_code == 503
    assert "private account" not in response.text
