"""Officer portal (Department of Skills) - the hero Impact Intelligence surface.

All endpoints serve aggregates only (never PII), with consent coverage and
k-anonymity baked in. Individual trainee views log PII_VIEWED events.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.db.engine import get_session
from app.models.tables import Cohort, FollowupAttempt, FollowupWave, Programme, Provider, User
from app.security import require_roles
from app.services import outcomes as outcome_svc
from app.services.consents import log_pii_view, pii_access_log
from app.services.followups import create_adhoc_wave, non_responders, record_one_tap_response

router = APIRouter(prefix="/officer", tags=["officer"])


@router.get("/dashboard")
async def dashboard(user: User = Depends(require_roles("officer", "admin")),
                    session: AsyncSession = Depends(get_session)):
    return await outcome_svc.officer_dashboard(session)


@router.get("/programmes")
async def programmes(view: str = "day0",
                     user: User = Depends(require_roles("officer", "admin")),
                     session: AsyncSession = Depends(get_session)):
    if view not in ("day0", "outcomes"):
        raise HTTPException(400, "view must be day0|outcomes")
    return await outcome_svc.programmes_table(session, view)


@router.get("/programmes/{programme_id}")
async def programme_detail(programme_id: int,
                           user: User = Depends(require_roles("officer", "admin")),
                           session: AsyncSession = Depends(get_session)):
    detail = await outcome_svc.programme_detail(session, programme_id)
    if not detail:
        raise HTTPException(404, "Programme not found")
    return detail


@router.get("/districts")
async def districts(user: User = Depends(require_roles("officer", "admin")),
                    session: AsyncSession = Depends(get_session)):
    return await outcome_svc.district_heatmap(session)


@router.get("/demographics")
async def demographics(user: User = Depends(require_roles("officer", "admin")),
                       session: AsyncSession = Depends(get_session)):
    return await outcome_svc.demographic_overview(session)


@router.get("/followups")
async def followups(user: User = Depends(require_roles("officer", "admin")),
                    session: AsyncSession = Depends(get_session)):
    """Assisted workbench: due waves + non-responder queue (PII banner on open)."""
    waves = (await session.execute(
        select(FollowupWave, Cohort)
        .join(Cohort, Cohort.id == FollowupWave.cohort_id)
        .order_by(FollowupWave.due_on.desc())
        .limit(50)
    )).all()
    out_waves = []
    for w, c in waves:
        from app.services.followups import wave_stats

        stats = await wave_stats(session, w.id)
        out_waves.append({
            "id": w.id, "cohort_id": w.cohort_id, "batch_code": c.batch_code,
            "milestone_months": w.milestone_months, "kind": w.kind,
            "status": w.status, "due_on": w.due_on.isoformat(), **stats,
        })
    return {"waves": out_waves, "non_responders": await non_responders(session, days=14),
            "cohorts": [
                {"id": c.id, "batch_code": c.batch_code,
                 "programme": p.title, "provider": prov.name,
                 "status": ("completed" if c.end_date and c.end_date <= date.today()
                            else "running")}
                for c, p, prov in (await session.execute(
                    select(Cohort, Programme, Provider)
                    .join(Programme, Programme.id == Cohort.programme_id)
                    .join(Provider, Provider.id == Programme.provider_id)
                    .order_by(Cohort.end_date.desc())
                    .limit(60)
                )).all()
            ]}


class WaveBody(BaseModel):
    cohort_id: int


@router.post("/waves")
async def trigger_wave(body: WaveBody,
                       user: User = Depends(require_roles("officer", "admin")),
                       session: AsyncSession = Depends(get_session)):
    cohort = (await session.execute(
        select(Cohort).where(Cohort.id == body.cohort_id))).scalar_one_or_none()
    if cohort is None:
        raise HTTPException(404, "Cohort not found")
    wave = await create_adhoc_wave(session, body.cohort_id, officer_id=user.id)
    return {"wave_id": wave.id, "status": wave.status,
            "notified": "all completers notified in-app"}


class AssistedBody(BaseModel):
    response: str  # wage|self_employed|apprenticeship|higher_study|unemployed|no_response
    band_idx: int | None = None
    role_title: str = ""
    notes: str = ""


@router.post("/followup-attempts/{attempt_id}")
async def assisted_attempt(attempt_id: int, body: AssistedBody,
                           user: User = Depends(require_roles("officer", "admin")),
                           session: AsyncSession = Depends(get_session)):
    """Officer records an outcome for a non-responder. Opens PII (audited)."""
    from app.models.tables import FollowupAttempt

    attempt = (await session.execute(
        select(FollowupAttempt).where(FollowupAttempt.id == attempt_id)
    )).scalar_one_or_none()
    if attempt is None:
        raise HTTPException(404, "Attempt not found")

    # PII access is audited BEFORE anything is shown/recorded
    await log_pii_view(session, officer_id=user.id, trainee_id=attempt.user_id,
                       context=f"assisted follow-up attempt {attempt_id}")

    if body.response == "no_response":
        attempt.response = "no_response"
        attempt.responded_at = None
        attempt.officer_id = user.id
        attempt.notes = body.notes or "no contact"
        session.add(attempt)
        await session.commit()
        return {"attempt_id": attempt.id, "response": "no_response"}

    if body.response not in ("wage", "self_employed", "apprenticeship",
                             "higher_study", "unemployed"):
        raise HTTPException(400, "invalid response type")
    res = await record_one_tap_response(
        session, attempt.wave_id, attempt.user_id, body.response,
        band_idx=body.band_idx, role_title=body.role_title, notes=body.notes)
    # mark it assisted + officer
    attempt2 = (await session.execute(
        select(FollowupAttempt).where(FollowupAttempt.id == res["attempt_id"])
    )).scalar_one()
    attempt2.method = "assisted"
    attempt2.officer_id = user.id
    session.add(attempt2)
    await session.commit()
    return {"attempt_id": res["attempt_id"], "response": res["response"],
            "episode_id": res["episode_id"]}


@router.get("/audit")
async def audit(user: User = Depends(require_roles("officer", "admin")),
                session: AsyncSession = Depends(get_session)):
    entries = await pii_access_log(session)
    officers = {u.id: u.name for u in (await session.execute(
        select(User).where(User.role.in_(("officer", "admin"))))).scalars().all()}
    for e in entries:
        e["officer_name"] = officers.get(e["officer_id"], f"user {e['officer_id']}")
    return {"entries": entries}
