"""Portfolio: artifacts CRUD, shareable read-only portfolio via signed tokens."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.db.engine import get_session
from app.models.tables import Artifact, Credential, ShareToken, User
from app.security import get_current_user
from app.services.proficiency import genome_to_json, get_genome

router = APIRouter(tags=["portfolio"])


class ArtifactBody(BaseModel):
    kind: str = "project"
    title: str
    payload: dict = {}
    verification: str = "pending"


@router.get("/me/artifacts")
async def my_artifacts(user: User = Depends(get_current_user),
                       session: AsyncSession = Depends(get_session)):
    arts = (await session.execute(
        select(Artifact).where(Artifact.user_id == user.id)
        .order_by(Artifact.created_at.desc())
    )).scalars().all()
    creds = (await session.execute(
        select(Credential).where(Credential.user_id == user.id)
    )).scalars().all()
    cred_by_artifact = {c.artifact_id: c for c in creds}
    return [
        {
            "id": a.id, "kind": a.kind, "title": a.title, "payload": a.payload,
            "verification": a.verification, "created_at": a.created_at.isoformat(),
            "credential_id": cred_by_artifact[a.id].id if a.id in cred_by_artifact else None,
        }
        for a in arts
    ]


@router.post("/artifacts")
async def create_artifact(body: ArtifactBody,
                          user: User = Depends(get_current_user),
                          session: AsyncSession = Depends(get_session)):
    if body.kind not in ("project", "certificate", "internship", "achievement", "gauntlet"):
        raise HTTPException(400, "invalid kind")
    if not body.title.strip():
        raise HTTPException(400, "title required")
    a = Artifact(user_id=user.id, kind=body.kind, title=body.title.strip(),
                 payload=body.payload, verification=body.verification)
    session.add(a)
    await session.commit()
    await session.refresh(a)
    return {"id": a.id, "title": a.title, "verification": a.verification}


@router.delete("/artifacts/{artifact_id}")
async def delete_artifact(artifact_id: int, user: User = Depends(get_current_user),
                          session: AsyncSession = Depends(get_session)):
    a = (await session.execute(select(Artifact).where(Artifact.id == artifact_id))).scalar_one_or_none()
    if a is None or a.user_id != user.id:
        raise HTTPException(404, "Artifact not found")
    await session.delete(a)
    await session.commit()
    return {"ok": True}


class ShareTokenBody(BaseModel):
    days: int = 30
    scopes: list[str] = ["genome", "artifacts", "credentials"]


@router.post("/share-tokens")
async def create_share_token(body: ShareTokenBody,
                             user: User = Depends(get_current_user),
                             session: AsyncSession = Depends(get_session)):
    token = secrets.token_urlsafe(24)
    st = ShareToken(
        token=token, user_id=user.id, scopes=body.scopes,
        expires_at=datetime.now(timezone.utc) + timedelta(days=body.days),
    )
    session.add(st)
    await session.commit()
    return {"token": token, "url": f"/public/portfolio/{token}",
            "expires_at": st.expires_at.isoformat()}


@router.get("/me/share-tokens")
async def my_tokens(user: User = Depends(get_current_user),
                    session: AsyncSession = Depends(get_session)):
    toks = (await session.execute(
        select(ShareToken).where(ShareToken.user_id == user.id, ShareToken.revoked == False)  # noqa: E712
    )).scalars().all()
    return [{"token": t.token, "expires_at": t.expires_at.isoformat() if t.expires_at else None}
            for t in toks]


@router.delete("/share-tokens/{token}")
async def revoke_token(token: str, user: User = Depends(get_current_user),
                       session: AsyncSession = Depends(get_session)):
    st = (await session.execute(select(ShareToken).where(ShareToken.token == token))).scalar_one_or_none()
    if st is None or st.user_id != user.id:
        raise HTTPException(404, "Token not found")
    st.revoked = True
    session.add(st)
    await session.commit()
    return {"ok": True}


@router.get("/public/portfolio/{token}")
async def public_portfolio(token: str, session: AsyncSession = Depends(get_session)):
    """No-auth read-only portfolio view."""
    st = (await session.execute(select(ShareToken).where(ShareToken.token == token))).scalar_one_or_none()
    if st is None or st.revoked:
        raise HTTPException(404, "Portfolio link invalid")
    if st.expires_at and st.expires_at < datetime.now(timezone.utc):
        raise HTTPException(410, "Portfolio link expired")

    user = (await session.execute(select(User).where(User.id == st.user_id))).scalar_one_or_none()
    if user is None:
        raise HTTPException(404, "Owner not found")

    out: dict = {"owner": user.name, "headline": user.headline, "scopes": st.scopes or []}
    if "genome" in (st.scopes or []):
        genome = await get_genome(session, user.id)
        out["genome"] = genome_to_json(genome)
    if "artifacts" in (st.scopes or []):
        arts = (await session.execute(select(Artifact).where(Artifact.user_id == user.id))).scalars().all()
        out["artifacts"] = [{"kind": a.kind, "title": a.title,
                             "verification": a.verification} for a in arts]
    if "credentials" in (st.scopes or []):
        creds = (await session.execute(select(Credential).where(Credential.user_id == user.id))).scalars().all()
        out["credentials"] = [{"id": c.id, "payload": c.payload,
                               "verify_url": f"/verify/{c.id}"} for c in creds]
    return out
