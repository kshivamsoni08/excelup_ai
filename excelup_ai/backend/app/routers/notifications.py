"""In-app notifications: list + mark read (bell polls every 10s)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.db.engine import get_session
from app.models.tables import Notification, User
from app.security import get_current_user

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
async def list_notifications(user: User = Depends(get_current_user),
                             session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(
        select(Notification).where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc()).limit(50)
    )).scalars().all()
    unread = (await session.execute(
        select(func.count()).select_from(Notification)
        .where(Notification.user_id == user.id, Notification.read == False)  # noqa: E712
    )).scalar()
    return {
        "unread": unread,
        "items": [
            {"id": n.id, "type": n.type, "payload": n.payload, "read": n.read,
             "created_at": n.created_at.isoformat()}
            for n in rows
        ],
    }


@router.post("/{notification_id}/read")
async def mark_read(notification_id: int, user: User = Depends(get_current_user),
                    session: AsyncSession = Depends(get_session)):
    n = (await session.execute(
        select(Notification).where(Notification.id == notification_id)
    )).scalar_one_or_none()
    if n is None or n.user_id != user.id:
        raise HTTPException(404, "Notification not found")
    n.read = True
    session.add(n)
    await session.commit()
    return {"ok": True}


@router.post("/read-all")
async def mark_all_read(user: User = Depends(get_current_user),
                        session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(
        select(Notification).where(Notification.user_id == user.id, Notification.read == False)  # noqa: E712
    )).scalars().all()
    for n in rows:
        n.read = True
        session.add(n)
    await session.commit()
    return {"ok": True, "marked": len(rows)}
