import os
import pytest
import requests


BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")


def _server_available() -> bool:
    try:
        r = requests.get(f"{BASE_URL}/openapi.json", timeout=1.5)
        return r.status_code == 200
    except Exception:
        return False


@pytest.mark.integration
def test_live_riff_names():
    if not _server_available():
        pytest.skip(
            "Start the server first: `PYENV_VERSION=godadder uvicorn --app-dir src godadder.startup_namer:app --reload`"
        )

    payload = {"base": "Aurorify", "count": 3}
    resp = requests.post(f"{BASE_URL}/riff-names", json=payload, timeout=30)
    # When running with `-s`, this will show the API response in the console
    print("status:", resp.status_code)
    print("json:", resp.text)

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)
    assert "names" in data
    assert isinstance(data["names"], list)
    assert len(data["names"]) == payload["count"]
    assert all(isinstance(x, str) and x.strip() for x in data["names"])
