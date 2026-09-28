"""M6 scope: the API service must be deployable and health-checkable.
See About/plan.md T6.1/T6.7 — a host needs a real signal the service (and
its DB connection) is actually up, not just that the process started.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from otherworld.api.main import app


def test_health_reports_ok_when_db_is_reachable():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
