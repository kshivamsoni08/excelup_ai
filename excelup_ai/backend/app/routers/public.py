"""Public, no-auth routes: credential verification + shareable portfolio."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_session
from app.services.credentials import verify_credential

router = APIRouter(tags=["public"])


@router.get("/verify/{credential_id}")
async def verify(credential_id: int, session: AsyncSession = Depends(get_session)):
    """PUBLIC (no auth): payload, signature valid?, Merkle proof valid?, date."""
    return await verify_credential(session, credential_id)
