"""Append-only event audit trail helper (backs application timelines)."""
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import Event


async def record_event(session: AsyncSession, aggregate_type: str, aggregate_id: int,
                       event_type: str, payload: Optional[dict[str, Any]] = None):
    session.add(Event(aggregate_type=aggregate_type, aggregate_id=aggregate_id,
                      event_type=event_type, payload=payload or {}))
    await session.commit()


async def events_for(session: AsyncSession, aggregate_type: str, aggregate_id: int):
    res = await session.execute(
        select(Event)
        .where(Event.aggregate_type == aggregate_type, Event.aggregate_id == aggregate_id)
        .order_by(Event.ts)
    )
    return res.scalars().all()


from sqlmodel import select  # noqa: E402  (kept late to keep the helper header tidy)
