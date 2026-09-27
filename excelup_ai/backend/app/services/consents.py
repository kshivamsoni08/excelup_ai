"""Consent engine (§5.5): consent-scoped analytics + PII access audit.

Consents are rows in `consents` with scopes drawn from
["outcomes", "wage", "demographics", "skills"]. Revoking takes effect on the
next query - every analytics helper re-reads consent rows live.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.tables import Consent, Event

SCOPES = ("outcomes", "wage", "demographics", "skills")
GRANTEE_TYPES = ("department", "provider", "employer")


async def consented_user_ids(session: AsyncSession, scope: str,
                             grantee_type: str = "department",
                             grantee_id: Optional[int] = None) -> set[int]:
    """User ids holding an ACTIVE (non-revoked, non-expired) consent of the
    given scope for the grantee. Used to filter every analytics query."""
    rows = (await session.execute(select(Consent).where(
        Consent.grantee_type == grantee_type,
        Consent.revoked == False,  # noqa: E712
    ))).scalars().all()
    now = datetime.now(timezone.utc)
    out: set[int] = set()
    for c in rows:
        if grantee_id is not None and c.grantee_id is not None and c.grantee_id != grantee_id:
            continue
        if c.expires_at is not None and c.expires_at < now:
            continue
        if scope in (c.scopes or []):
            out.add(c.user_id)
    return out


async def user_consents(session: AsyncSession, user_id: int) -> list[Consent]:
    return (await session.execute(
        select(Consent).where(Consent.user_id == user_id)
        .order_by(Consent.granted_at)
    )).scalars().all()


async def log_pii_view(session: AsyncSession, officer_id: int, trainee_id: int,
                       context: str) -> Event:
    """Every officer view of individual-level PII writes a PII_VIEWED event."""
    ev = Event(
        aggregate_type="trainee", aggregate_id=trainee_id,
        event_type="PII_VIEWED",
        payload={"officer_id": officer_id, "context": context,
                 "at": datetime.now(timezone.utc).isoformat()},
    )
    session.add(ev)
    await session.commit()
    return ev


async def pii_access_log(session: AsyncSession, limit: int = 200) -> list[dict]:
    rows = (await session.execute(
        select(Event).where(Event.event_type == "PII_VIEWED")
        .order_by(Event.ts.desc()).limit(limit)
    )).scalars().all()
    return [{
        "id": e.id, "trainee_id": e.aggregate_id,
        "officer_id": (e.payload or {}).get("officer_id"),
        "context": (e.payload or {}).get("context"),
        "ts": e.ts.isoformat(),
    } for e in rows]
