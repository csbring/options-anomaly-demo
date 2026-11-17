import json
from options_demo.narration import narrate


def test_no_model_is_offline(monkeypatch):
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    assert narrate({}, "why")[0] is None


def test_remote_endpoint_is_refused(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "example")
    monkeypatch.setenv("OLLAMA_URL", "https://external.example")
    assert narrate({}, "why")[0] is None


def test_narration_only_receives_report_fields(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "example")
    monkeypatch.setenv("OLLAMA_URL", "http://127.0.0.1:11434")
    sent = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, size): return b'{"message":{"content":"Synthetic example."}}'
    def request(req, timeout):
        sent.append(json.loads(req.data))
        return Response()
    monkeypatch.setattr("options_demo.narration.urlopen", request)
    report = {k: [] for k in ["symbol", "source_label", "model_basis", "flagged", "calls", "puts", "quality_pass", "rows"]}
    report["private"] = "must not send"
    assert narrate(report, "why")[0] == "Synthetic example."
    assert "must not send" not in json.dumps(sent)
