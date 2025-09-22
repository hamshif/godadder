import godadder.gpoc as gpoc


def test_extract_user_success(client, monkeypatch):
    class FakeAgent:
        def run(self, prompt: str):
            return gpoc.User(name="Alice", age=30)

    monkeypatch.setattr(gpoc, "user_agent", FakeAgent())

    resp = client.post("/extract-user", json={"text": "Name: Alice, Age: 30"})
    assert resp.status_code == 200
    assert resp.json() == {"name": "Alice", "age": 30}


def test_extract_user_model_error(client, monkeypatch):
    class BadAgent:
        def run(self, prompt: str):
            raise gpoc.HTTPException(status_code=500, detail="AI model error")

    monkeypatch.setattr(gpoc, "user_agent", BadAgent())

    resp = client.post("/extract-user", json={"text": "anything"})
    assert resp.status_code == 500
    assert resp.json()["detail"] == "AI model error"


def test_validation_error_422(client):
    # Missing required field 'text' should trigger validation error
    resp = client.post("/extract-user", json={})
    assert resp.status_code == 422

