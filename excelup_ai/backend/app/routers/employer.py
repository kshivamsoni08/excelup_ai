"""Employer validation flow (§5.4): confirm/dispute reported wage episodes.

Employers see role + start month + a WAGE BAND (never exact wage - privacy).
Confirming sets validation_status='validated' and stamps validated_by/at.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.db.engine import get_session
from app.models.tables import Company, EmploymentEpisode, User
from app.security import require_roles
from app.services.events import record_event
from app.services.notifications import notify

router = APIRouter(prefix="/employer", tags=["employer"])


@router.get("/validations")
async def validation_queue(user: User = Depends(require_roles("employer", "admin")),
                           session: AsyncSession = Depends(get_session)):
    q = (select(EmploymentEpisode, User)
         .join(User, User.id == EmploymentEpisode.user_id)
         .where(EmploymentEpisode.employment_type == "wage",
                EmploymentEpisode.validation_status.in_(("unvalidated", "pending", "disputed"))))
    if user.company_id:
        q = q.where(EmploymentEpisode.company_id == user.company_id)
    rows = (await session.execute(q.order_by(EmploymentEpisode.start_date.desc()))).all()

    out = []
    for ep, trainee in rows:
        out.append({
            "episode_id": ep.id,
            "trainee_ref": f"TRN-{ep.user_id:05d}",
            "identity_revealed": ep.validation_status == "validated",
            "trainee_name": trainee.name if ep.validation_status == "validated" else None,
            "role_title": ep.role_title,
            "start_date": ep.start_date.isoformat(),
            "district_id": ep.district_id,
            "source": ep.source,
            "validation_status": ep.validation_status,
            "cohort_id": ep.cohort_id,
            "created_at": ep.created_at.isoformat(),
        })
    return out


class ValidationBody(BaseModel):
    decision: str  # confirm | dispute
    wage_band: int | None = None  # 0..4 -> <10k, 10-15k, 15-20k, 20-30k, 30k+
    role_title: str = ""


BAND_LABELS = ["<10k", "10-15k", "15-20k", "20-30k", "30k+"]


@router.post("/validations/{episode_id}")
async def validate_episode(episode_id: int, body: ValidationBody,
                           user: User = Depends(require_roles("employer", "admin")),
                           session: AsyncSession = Depends(get_session)):
    ep = (await session.execute(
        select(EmploymentEpisode).where(EmploymentEpisode.id == episode_id)
    )).scalar_one_or_none()
    if ep is None:
        raise HTTPException(404, "Episode not found")
    if user.company_id and ep.company_id != user.company_id:
        raise HTTPException(403, "Not your company's episode")
    if body.decision not in ("confirm", "dispute"):
        raise HTTPException(400, "decision must be confirm|dispute")

    if body.decision == "confirm":
        ep.validation_status = "validated"
        ep.validated_by = user.id
        ep.validated_at = datetime.now(timezone.utc)
        ep.source = "employer_validated" if ep.source != "platform_placement" else ep.source
        if body.role_title:
            ep.role_title = body.role_title
        if body.wage_band is not None:
            # wage BAND only - the episode stores the band midpoint as current wage
            mid = {0: 6000, 1: 12500, 2: 17500, 3: 25000, 4: 40000}.get(int(body.wage_band))
            if mid and ep.monthly_wage_start:
                ep.monthly_wage_current = max(ep.monthly_wage_start, mid)
            elif mid:
                ep.monthly_wage_current = mid
        session.add(ep)
        await session.flush()
        await record_event(session, "employment_episode", ep.id, "validated",
                           {"by": user.name, "band": BAND_LABELS[body.wage_band]
                            if body.wage_band is not None else None})
        await notify(session, ep.user_id, "episode_validated", {
            "episode_id": ep.id, "employer": user.name,
        })
        await session.commit()
        return {"episode_id": ep.id, "validation_status": "validated"}

    ep.validation_status = "disputed"
    session.add(ep)
    await session.flush()
    await record_event(session, "employment_episode", ep.id, "disputed",
                       {"by": user.name})
    await notify(session, ep.user_id, "episode_disputed", {
        "episode_id": ep.id, "employer": user.name,
    })
    await session.commit()
    return {"episode_id": ep.id, "validation_status": "disputed"}
