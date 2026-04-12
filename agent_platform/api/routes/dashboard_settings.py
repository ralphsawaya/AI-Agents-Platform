"""Dashboard-level settings: team visibility toggles.

Stores a single document in the ``dashboard_settings`` collection that tracks
which teams should be hidden from the Dashboard view.
"""

import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from agent_platform.db.client import get_database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["dashboard-settings"])

DOC_ID = "dashboard_visibility"


def _ok(data: Any = None) -> dict:
    return {"success": True, "data": data, "error": None}


class VisibilityUpdate(BaseModel):
    agent_id: str
    visible: bool


@router.get("/visibility")
async def get_visibility():
    """Return the set of hidden team IDs."""
    db = get_database()
    doc = await db["dashboard_settings"].find_one({"_id": DOC_ID})
    hidden: list[str] = (doc or {}).get("hidden_teams", [])
    return _ok({"hidden_teams": hidden})


@router.put("/visibility")
async def update_visibility(body: VisibilityUpdate):
    """Toggle a single team's dashboard visibility."""
    db = get_database()

    if body.visible:
        await db["dashboard_settings"].update_one(
            {"_id": DOC_ID},
            {"$pull": {"hidden_teams": body.agent_id}},
            upsert=True,
        )
    else:
        await db["dashboard_settings"].update_one(
            {"_id": DOC_ID},
            {"$addToSet": {"hidden_teams": body.agent_id}},
            upsert=True,
        )

    logger.info("Visibility updated: %s → %s", body.agent_id, body.visible)
    return _ok({"agent_id": body.agent_id, "visible": body.visible})
