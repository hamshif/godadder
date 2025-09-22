from fastapi.testclient import TestClient
import pytest

import godadder.gpoc as gpoc


@pytest.fixture
def client():
    """Return a TestClient for the FastAPI app."""
    return TestClient(gpoc.app)

