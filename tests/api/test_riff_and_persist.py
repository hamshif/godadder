from __future__ import annotations

from fastapi.testclient import TestClient

import startupper.startup_namer as sn
from startupper.persistence.sqlite_store import SQLiteDomainStore
from tests.fakes import FakeAgent, FakeDomainChecker


def test_riff_and_check_persists_results(tmp_path):
    # Arrange fakes
    db_path = tmp_path / "domains.db"
    store = SQLiteDomainStore(str(db_path))
    store.setup()

    app = sn.app
    app.dependency_overrides[sn.get_riff_agent] = lambda: FakeAgent(["Alpha", "Beta"])  # clean labels
    app.dependency_overrides[sn.get_domain_checker] = lambda: FakeDomainChecker()
    app.dependency_overrides[sn.provide_domain_store] = lambda: store

    client = TestClient(app)

    # Act: riff-and-check with default persist=True
    payload = {"base": "Acme", "count": 2, "persist": True}
    r = client.post("/riff-and-check", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, dict)
    assert isinstance(data.get("names"), list)
    assert len(data["names"]) == 2
    # Alpha, Beta -> Alpha.com, Alpha.ai, Beta.com, Beta.ai
    assert isinstance(data.get("items"), list)
    assert len(data["items"]) == 4

    # Assert persisted rows
    r2 = client.get("/domains")
    assert r2.status_code == 200
    rows = r2.json()
    if not (isinstance(rows, list) and len(rows) >= 4):
        # Fallback check via store API to aid diagnosis
        # First, directly upsert to validate the store plumbing
        store.upsert_domain("alpha.com", {"available": True, "price": 12.3, "currency": "USD"})
        df = store.select_domains()
        assert len(df.index) >= 1, "store upsert/select not working"
        # If store works but route didn't persist, fail explicitly
        assert False, "persistence did not create expected rows"
    domains = {row.get("domain") or row.get("name") for row in rows}
    assert {"alpha.com", "alpha.ai", "beta.com", "beta.ai"}.issubset(domains)
