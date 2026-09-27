"""Small helper for creating in-app notifications."""
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import Notification


async def notify(session: AsyncSession, user_id: int, type: str,
                 payload: Optional[dict[str, Any]] = None) -> Notification:
    n = Notification(user_id=user_id, type=type, payload=payload or {})
    session.add(n)
    await session.commit()
    return n
