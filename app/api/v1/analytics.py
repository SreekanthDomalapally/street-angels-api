"""Analytics aggregation endpoints (Phase 6)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, require_admin
from app.db.session import get_db
from app.models import Alert, AlertResponse, User

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview")
async def analytics_overview(
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
) -> dict[str, object]:
    since = datetime.now(UTC) - timedelta(days=30)
    total_alerts = await db.scalar(
        select(func.count()).select_from(Alert).where(Alert.created_at >= since)
    )
    active_users = await db.scalar(
        select(func.count()).select_from(User).where(User.last_active_at >= since)
    )
    responses = await db.scalar(
        select(func.count()).select_from(AlertResponse).where(AlertResponse.created_at >= since)
    )
    avg_response = await db.scalar(
        select(func.avg(AlertResponse.eta_minutes)).where(AlertResponse.created_at >= since)
    )
    return {
        "period_days": 30,
        "alerts_last_30d": int(total_alerts or 0),
        "active_users_last_30d": int(active_users or 0),
        "responses_last_30d": int(responses or 0),
        "avg_eta_minutes": round(float(avg_response), 1) if avg_response else None,
    }
