"""M6 T6.7: the cost dashboard's HTTP surface."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import httpx

from otherworld.api.deps import get_current_owner
from otherworld.api.main import app
from otherworld.db import get_session
from otherworld.models.owner import Owner, owner_to_orm
from otherworld.models.trace import DecisionTraceORM


async def test_cost_dashboard_reports_total_and_per_agent_day_costs(db_session):
    now = datetime.now(UTC)
    owner = Owner(
        id=uuid.uuid4(), handle="dash", email="dash@example.com", consent=None,
        created_at=now, last_active_at=now,
    )
    db_session.add(owner_to_orm(owner))
    agent_id = uuid.uuid4()
    db_session.add(
        DecisionTraceORM(
            id=uuid.uuid4(), agent_id=agent_id, tick=0, observation_summary="", retrieved_memory_ids=[],
            prompt_hash="h", tier_used=1, raw_completion="{}", parsed_action="idle",
            validator_result="accepted", latency_ms=5.0, input_tokens=100, output_tokens=16,
            estimated_cost_usd=0.025, created_at=now,
        )
    )
    await db_session.commit()

    async def _override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = _override_get_session
    app.dependency_overrides[get_current_owner] = lambda: owner
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    try:
        response = await client.get("/api/v1/dashboard/cost")
        assert response.status_code == 200
        body = response.json()
        assert body["total_cost_usd"] == 0.025
        assert body["cost_per_agent_day"][0]["agent_id"] == str(agent_id)
        assert body["tier_share"]["1"] == 1.0
    finally:
        app.dependency_overrides.clear()
        await client.aclose()
