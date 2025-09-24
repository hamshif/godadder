from fastapi.testclient import TestClient
import godadder.startup_namer as startup_namer


def test_riff_names_success():
    calls = {}

    class FakeAgent(startup_namer.NameRiffAgent):
        def riff(self, base: str, count: int, model: str | None = None):
            calls["args"] = (base, count, model)
            return [f"{base}-{i+1}.ai" for i in range(count)]

    app = startup_namer.app
    app.dependency_overrides[startup_namer.get_riff_agent] = lambda: FakeAgent()
    client = TestClient(app)

    resp = client.post("/riff-names", json={"base": "Acme", "count": 3})
    assert resp.status_code == 200
    data = resp.json()
    assert data == {"names": ["Acme-1.ai", "Acme-2.ai", "Acme-3.ai"]}
    assert calls["args"] == ("Acme", 3, None)


def test_riff_names_validation_error():
    app = startup_namer.app
    client = TestClient(app)
    # Missing 'base' and 'count'
    resp = client.post("/riff-names", json={})
    assert resp.status_code == 422

    # Invalid count (must be >=1)
    resp2 = client.post("/riff-names", json={"base": "Acme", "count": 0})
    assert resp2.status_code == 422


def test_riff_names_model_override():
    calls = {}

    class FakeAgent(startup_namer.NameRiffAgent):
        def riff(self, base: str, count: int, model: str | None = None):
            calls["args"] = (base, count, model)
            return [f"{base}-{i+1}.ai" for i in range(count)]

    app = startup_namer.app
    app.dependency_overrides[startup_namer.get_riff_agent] = lambda: FakeAgent()
    client = TestClient(app)

    resp = client.post("/riff-names", json={"base": "Acme", "count": 2, "model": "llamaX"})
    assert resp.status_code == 200
    assert resp.json()["names"] == ["Acme-1.ai", "Acme-2.ai"]
    assert calls["args"] == ("Acme", 2, "llamaX")
