"""Trainee outcome surfaces: Outcome Ledger timeline, one-tap follow-ups,
consent manager."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.db.engine import get_session
from app.models.tables import (
    Cohort,
    CohortEnrollment,
    Company,
    Consent,
    District,
    EmploymentEpisode,
    FollowupAttempt,
    FollowupWave,
    Programme,
    WageEvent,
)
from app.security import require_trainee
from app.services.followups import (
    BAND_MIDPOINTS,
    RESPONSE_TYPES,
    record_one_tap_response,
)

router = APIRouter(tags=["trainee-outcomes"])


@router.get("/me/outcomes")
async def my_outcomes(user=Depends(require_trainee),
                      session: AsyncSession = Depends(get_session)):
    """Outcome Ledger timeline: episodes + wage curve + next follow-up."""
    episodes = (await session.execute(
        select(EmploymentEpisode)
        .where(EmploymentEpisode.user_id == user.id)
        .order_by(EmploymentEpisode.start_date.desc())
    )).scalars().all()

    wages_by_ep: dict[int, list[dict]] = {}
    if episodes:
        we = (await session.execute(
            select(WageEvent).where(WageEvent.episode_id.in_([e.id for e in episodes]))
            .order_by(WageEvent.month_index)
        )).scalars().all()
        for w in we:
            wages_by_ep.setdefault(w.episode_id, []).append(
                {"month_index": w.month_index, "monthly_wage": w.monthly_wage})

    companies = {c.id: c.name for c in (await session.execute(select(Company))).scalars().all()}
    districts = {d.id: d.name for d in (await session.execute(select(District))).scalars().all()}

    ep_out = []
    for e in episodes:
        ep_out.append({
            "id": e.id,
            "employment_type": e.employment_type,
            "role_title": e.role_title,
            "company": companies.get(e.company_id),
            "district": districts.get(e.district_id),
            "start_date": e.start_date.isoformat(),
            "end_date": e.end_date.isoformat() if e.end_date else None,
            "status": e.status,
            "source": e.source,
            "validation_status": e.validation_status,
            "monthly_wage_start": e.monthly_wage_start,
            "monthly_wage_current": e.monthly_wage_current,
            "wage_series": wages_by_ep.get(e.id, []),
        })

    # programme/cohort context (trainee's completed cohorts)
    enroll_rows = (await session.execute(
        select(CohortEnrollment, Cohort, Programme)
        .join(Cohort, Cohort.id == CohortEnrollment.cohort_id)
        .join(Programme, Programme.id == Cohort.programme_id)
        .where(CohortEnrollment.user_id == user.id)
    )).all()
    programmes = [{"cohort_id": ce.cohort_id, "batch_code": c.batch_code,
                   "programme": p.title, "sector": p.sector,
                   "status": ce.status,
                   "completed_at": ce.completed_at.isoformat() if ce.completed_at else None}
                  for ce, c, p in enroll_rows]

    # next open follow-up (pending attempt on an active wave)
    next_followup = None
    attempt = (await session.execute(
        select(FollowupAttempt, FollowupWave)
        .join(FollowupWave, FollowupWave.id == FollowupAttempt.wave_id)
        .where(FollowupAttempt.user_id == user.id,
               FollowupAttempt.responded_at.is_(None),
               FollowupWave.status == "active")
        .order_by(FollowupAttempt.id.desc())
    )).first()
    if attempt:
        a, w = attempt
        next_followup = {"attempt_id": a.id, "wave_id": w.id,
                         "kind": w.kind,
                         "milestone_months": w.milestone_months}

    return {"episodes": ep_out, "programmes": programmes,
            "next_followup": next_followup}


class OneTapBody(BaseModel):
    response: str
    band_idx: int | None = None
    role_title: str = ""
    notes: str = ""


@router.post("/me/followups/{wave_id}/respond")
async def respond_to_wave(wave_id: int, body: OneTapBody,
                          user=Depends(require_trainee),
                          session: AsyncSession = Depends(get_session)):
    """One-tap follow-up response (~20 seconds)."""
    if body.response not in RESPONSE_TYPES:
        raise HTTPException(400, f"response must be one of {RESPONSE_TYPES}")
    wave = (await session.execute(
        select(FollowupWave).where(FollowupWave.id == wave_id,
                                   FollowupWave.status == "active")
    )).scalar_one_or_none()
    if wave is None:
        raise HTTPException(404, "Wave not found or not active")
    try:
        res = await record_one_tap_response(
            session, wave_id, user.id, body.response,
            band_idx=body.band_idx, role_title=body.role_title, notes=body.notes)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return res


@router.get("/me/consents")
async def get_consents(user=Depends(require_trainee),
                       session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(
        select(Consent).where(Consent.user_id == user.id)
        .order_by(Consent.granted_at)
    )).scalars().all()
    return [{
        "id": c.id, "grantee_type": c.grantee_type, "grantee_id": c.grantee_id,
        "scopes": c.scopes or [], "purpose": c.purpose,
        "granted_at": c.granted_at.isoformat(),
        "expires_at": c.expires_at.isoformat() if c.expires_at else None,
        "revoked": c.revoked,
        "revoked_at": c.revoked_at.isoformat() if c.revoked_at else None,
    } for c in rows]


class ConsentBody(BaseModel):
    grantee_type: str
    scopes: list[str]
    purpose: str = ""
    grantee_id: int | None = None


@router.post("/me/consents")
async def grant_consent(body: ConsentBody,
                        user=Depends(require_trainee),
                        session: AsyncSession = Depends(get_session)):
    from app.services.consents import SCOPES, GRANTEE_TYPES

    if body.grantee_type not in GRANTEE_TYPES:
        raise HTTPException(400, f"grantee_type must be one of {GRANTEE_TYPES}")
    bad = [s for s in body.scopes if s not in SCOPES]
    if bad:
        raise HTTPException(400, f"unknown scopes: {bad}")
    consent = Consent(
        user_id=user.id, grantee_type=body.grantee_type,
        grantee_id=body.grantee_id, scopes=body.scopes,
        purpose=body.purpose or "Trainee-granted from consent manager",
    )
    session.add(consent)
    await session.commit()
    await session.refresh(consent)
    return {"id": consent.id, "scopes": consent.scopes, "revoked": False}


@router.post("/me/consents/{consent_id}/revoke")
async def revoke_consent(consent_id: int,
                         user=Depends(require_trainee),
                         session: AsyncSession = Depends(get_session)):
    consent = (await session.execute(
        select(Consent).where(Consent.id == consent_id, Consent.user_id == user.id)
    )).scalar_one_or_none()
    if consent is None:
        raise HTTPException(404, "Consent not found")
    consent.revoked = True
    consent.revoked_at = datetime.now(timezone.utc)
    session.add(consent)
    await session.commit()
    return {"id": consent.id, "revoked": True,
            "revoked_at": consent.revoked_at.isoformat()}
