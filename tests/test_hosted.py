import json
import secrets

from fastapi.testclient import TestClient
import pytest

from options_demo.app import create_app
from options_demo.store import ReportStore
from options_demo.tws import TWSUnavailable


@pytest.fixture
def hosted(monkeypatch, tmp_path):
    monkeypatch.setenv("OPTIONS_SOURCE", "tws")
    monkeypatch.setenv("OPTIONS_REPORT_DIR", str(tmp_path))
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    monkeypatch.setattr("options_demo.app.reachable", lambda: False)
    return tmp_path


def sample():
    return {"symbol": "AAPL", "source": "tws", "summary": "Saved quote summary.", "metadata": {"quote_time": "2026-01-02T15:00:00Z"}, "generated_at": "2026-01-02T15:00:05Z"}


def offline(*args):
    raise TWSUnavailable("TWS connectivity is not available.")


def test_success_persists_then_disconnect_returns_same_run(hosted, monkeypatch):
    monkeypatch.setattr("options_demo.app.analyze", lambda *args: sample())
    with TestClient(create_app()) as c:
        fresh = c.post("/api/chat", json={"message": "AAPL"}).json()
        assert fresh["report"]["availability"]["cached"] is False
    original = (hosted / "AAPL.json").read_bytes()
    monkeypatch.setattr("options_demo.app.analyze", offline)
    with TestClient(create_app()) as c:  # persistence survives service restart
        result = c.post("/api/chat", json={"message": "AAPL"})
        assert result.status_code == 200
        data = result.json()
        assert "TWS connectivity is not available" in data["text"]
        assert "Displaying last run" in data["text"]
        assert data["report"]["availability"]["cached"] is True
        assert data["report"]["generated_at"] == sample()["generated_at"]
        assert c.get("/api/status").json()["tws_reachable"] is False
        assert c.get("/api/last").json()["report"]["symbol"] == "AAPL"
    assert (hosted / "AAPL.json").read_bytes() == original


def test_no_wrong_symbol_or_synthetic_fallback(hosted, monkeypatch):
    ReportStore(str(hosted)).save(sample())
    monkeypatch.setattr("options_demo.app.analyze", offline)
    with TestClient(create_app()) as c:
        response = c.post("/api/chat", json={"message": "NVDA"})
        assert response.status_code == 503
        assert "No saved run for NVDA" in response.json()["detail"]
        assert "report" not in response.json()


def test_public_gateway_and_limits(monkeypatch):
    key = secrets.token_urlsafe(32)
    monkeypatch.setenv("OPTIONS_PUBLIC", "1")
    monkeypatch.setenv("OPTIONS_GATEWAY_KEY", key)
    with TestClient(create_app()) as c:
        assert c.get("/api/status").status_code == 401
        headers = {"X-Demo-Gateway": key, "X-Demo-Client": "test-client"}
        assert c.get("/api/status", headers=headers).status_code == 200
        assert c.post("/api/chat", content='x'*4097, headers=dict(headers, **{"Content-Type": "application/json"})).status_code == 413
        for _ in range(12):
            assert c.post("/api/chat", json={"message": "help"}, headers=headers).status_code == 200
        assert c.post("/api/chat", json={"message": "help"}, headers=headers).status_code == 429


def test_public_mode_requires_key(monkeypatch):
    monkeypatch.setenv("OPTIONS_PUBLIC", "1")
    monkeypatch.delenv("OPTIONS_GATEWAY_KEY", raising=False)
    with pytest.raises(RuntimeError):
        create_app()


def test_store_never_saves_synthetic(hosted):
    ReportStore(str(hosted)).save(dict(sample(), source="synthetic"))
    assert list(hosted.glob('*.json')) == []
