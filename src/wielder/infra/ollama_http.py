import requests
from typing import Optional


def is_reachable(base_url: str, timeout: float = 1.5) -> bool:
    try:
        r = requests.get(base_url, timeout=timeout)
        return 200 <= r.status_code < 500
    except Exception:
        return False


def model_present(base_url: str, model: str, timeout: float = 2.0) -> Optional[bool]:
    try:
        resp = requests.get(f"{base_url}/api/tags", timeout=timeout)
        if not resp.ok:
            return None
        data = resp.json()
        models = [m.get("name") for m in data.get("models", [])]
        return model in models if model else None
    except Exception:
        return None


def warm_model(base_url: str, model: str, timeout: float = 15.0, keep_alive: str = "30m") -> None:
    """Best-effort warmup call; non-raising and non-blocking semantics by design."""
    # Quick probe to avoid long timeouts if server is down
    if not is_reachable(base_url, timeout=1.5):
        return
    try:
        resp = requests.post(
            f"{base_url}/api/generate",
            json={"model": model, "prompt": "Ready?", "stream": False, "keep_alive": keep_alive},
            timeout=timeout,
        )
        _ = resp.status_code  # ignore errors; this is a hint
    except Exception:
        pass
