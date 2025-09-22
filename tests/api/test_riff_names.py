from fastapi.testclient import TestClient
import godadder.gpoc as gpoc


def test_riff_names_success():
    calls = {}

    class FakeAgent(gpoc.NameRiffAgent):
        def riff(self, base: str, count: int):
            calls["args"] = (base, count)
            return [f"{base}-{i+1}.ai" for i in range(count)]

    app = gpoc.app
    app.dependency_overrides[gpoc.get_riff_agent] = lambda: FakeAgent()
    client = TestClient(app)

    resp = client.post("/riff-names", json={"base": "Acme", "count": 3})
    assert resp.status_code == 200
    data = resp.json()
    assert data == {"names": ["Acme-1.ai", "Acme-2.ai", "Acme-3.ai"]}
    assert calls["args"] == ("Acme", 3)


def test_riff_names_validation_error():
    app = gpoc.app
    client = TestClient(app)
    # Missing 'base' and 'count'
    resp = client.post("/riff-names", json={})
    assert resp.status_code == 422

    # Invalid count (must be >=1)
    resp2 = client.post("/riff-names", json={"base": "Acme", "count": 0})
    assert resp2.status_code == 422
