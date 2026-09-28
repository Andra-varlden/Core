"""The cost dashboard. See About/plan.md M6 T6.7: "Reports cost per
agent-day and tier shares live." Deliberately a minimal text/JSON endpoint
(plan.md's own "minimal text dashboard" framing), not a charting UI — the
`web` frontend's dashboard page just renders this as a table.

Platform-operational data (aggregate spend and tier mix), not personal data
about any one owner, so any signed-in owner can read it — it's gated behind
authentication only to keep it off the public internet, not because it's
owner-specific.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from otherworld.api.deps import get_current_owner
from otherworld.db import get_session
from otherworld.models.owner import Owner
from otherworld.output.cost import cost_per_agent_day, tier_share

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("/cost")
async def get_cost_dashboard(
    _owner: Owner = Depends(get_current_owner), session: AsyncSession = Depends(get_session)
) -> dict[str, object]:
    per_agent_day = await cost_per_agent_day(session)
    shares = await tier_share(session)
    return {
        "cost_per_agent_day": [
            {"agent_id": str(agent_id), "day": day.isoformat(), "cost_usd": cost}
            for (agent_id, day), cost in sorted(per_agent_day.items(), key=lambda kv: kv[0][1])
        ],
        "total_cost_usd": sum(per_agent_day.values()),
        "tier_share": {str(tier): share for tier, share in shares.items()},
    }
