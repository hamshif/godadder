from fastapi.testclient import TestClient
import pytest

import godadder.startup_namer as startup_namer


@pytest.fixture
def client():
    """Return a TestClient for the FastAPI app."""
    return TestClient(startup_namer.app)
