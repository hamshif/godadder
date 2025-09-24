from __future__ import annotations

import os
from typing import Iterable

import pytest
import requests
from fastapi.testclient import TestClient

import startupper.startup_namer as startup_namer


@pytest.fixture
def client():
    """Return a TestClient for the FastAPI app."""
    return TestClient(startup_namer.app)


def _server_available() -> bool:
    base = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
    try:
        r = requests.get(f"{base}/openapi.json", timeout=0.75)
        return r.status_code == 200
    except Exception:
        return False


def _ollama_available() -> bool:
    base = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
    try:
        r = requests.get(base, timeout=0.75)
        return 200 <= r.status_code < 500
    except Exception:
        return False


def _is_allowed(mark_name: str) -> tuple[bool, str | None]:
    # Global switch to enable all side-effect tests
    if os.getenv("RUN_SIDE_EFFECTS") == "1":
        return True, None

    # Resource-specific toggles: REQUIRE_<NAME>=1
    if mark_name.startswith("requires_"):
        key = mark_name.split("requires_", 1)[1].upper()
        if os.getenv(f"REQUIRE_{key}") == "1":
            return True, None
        return False, f"missing env REQUIRE_{key}=1 (or RUN_SIDE_EFFECTS=1)"

    if mark_name == "side_effect":
        if os.getenv("RUN_SIDE_EFFECTS") == "1":
            return True, None
        return False, "missing env RUN_SIDE_EFFECTS=1"

    return True, None


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        marks: Iterable[pytest.Mark] = getattr(item, "own_markers", []) or item.iter_markers()
        reasons: list[str] = []
        needs_server = False
        needs_ollama = False

        for m in marks:
            allow, reason = _is_allowed(m.name)
            if not allow and reason:
                reasons.append(f"{m.name}: {reason}")

            if m.name == "requires_live_server":
                needs_server = True
            elif m.name == "requires_ollama":
                needs_ollama = True

        if reasons:
            item.add_marker(pytest.mark.skip(reason="; ".join(reasons)))
            continue

        # Availability checks only after allow-passes
        if needs_server and not _server_available():
            item.add_marker(pytest.mark.skip(reason="requires_live_server: API not reachable at API_BASE_URL"))
            continue
        if needs_ollama and not _ollama_available():
            item.add_marker(pytest.mark.skip(reason="requires_ollama: Ollama not reachable at OLLAMA_URL"))
