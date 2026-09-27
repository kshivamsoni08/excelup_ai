"""Applications: one-click apply, trainee timeline, status transitions.

State machine: applied → viewed → shortlisted → interviewed → offered → accepted
(rejected possible from any stage, with feedback auto-filled from the match
explanation: which skill decided it).

ExcelUp AI addition: when an application is 'accepted', auto-create an
employment episode (source='platform_placement') and an employer validation
request - linking training → placement → employment in one event.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.db.engine import get_session
from app.models.tables import (
    Application, CohortEnrollment, Company, EmploymentEpisode, Opportunity, User,
)
from app.security import get_current_user, require_roles
from app.services.events import events_for, record_event
from app.services.matching import (
    load_taxonomy,
    requirements_for,
    user_skill_map,
)
from app.services.notifications import notify
from app.engines.matching import match_user_to_opportunity

router = APIRouter(tags=["applications"])

STATUS_FLOW = ["applied", "viewed", "shortlisted", "interviewed", "offered", "accepted"]


class StatusBody(BaseModel):
    status: str
    feedback: dict | None = None


@router.post("/opportunities/{opp_id}/apply")
async def apply(opp_id: int, user: User = Depends(require_roles("trainee")),
                session: AsyncSession = Depends(get_session)):
    opp = (await session.execute(select(Opportunity).where(Opportunity.id == opp_id))).scalar_one_or_none()
    if opp is None:
        raise HTTPException(404, "Opportunity not found")
    if opp.kind == "gauntlet":
        raise HTTPException(400, "Use the gauntlet submission flow for challenges")

    existing = (await session.execute(
        select(Application).where(Application.opp_id == opp_id, Application.user_id == user.id)
    )).scalar_one_or_none()
    if existing:
        return {"id": existing.id, "status": existing.status, "already_applied": True}

    tax = await load_taxonomy(session)
    reqs = (await requirements_for(session, [opp_id])).get(opp_id, [])
    skills = await user_skill_map(session, user.id)
    res = match_user_to_opportunity(skills, reqs, tax.prereq_index,
                                    tax.skill_names, tax.courses_by_skill) if reqs else None

    app = Application(
        opp_id=opp_id, user_id=user.id,
        score=round(res.score * 100, 1) if res else 0.0,
        explanation=res.explanation.to_json() if res else {},
        status="applied",
    )
    session.add(app)
    await session.flush()
    await record_event(session, "application", app.id, "applied",
                       {"opp_id": opp_id, "score": app.score})
    await session.commit()
    await session.refresh(app)
    return {"id": app.id, "status": app.status, "score": app.score}


def _with_events(a: Application, evs) -> dict:
    return {
        "id": a.id, "opp_id": a.opp_id, "status": a.status, "score": a.score,
        "explanation": a.explanation, "feedback": a.feedback,
        "created_at": a.created_at.isoformat(), "updated_at": a.updated_at.isoformat(),
        "events": [{"type": e.event_type, "ts": e.ts.isoformat(), **(e.payload or {})} for e in evs],
    }


@router.get("/me/applications")
async def my_applications(user: User = Depends(get_current_user),
                          session: AsyncSession = Depends(get_session)):
    apps = (await session.execute(
        select(Application).where(Application.user_id == user.id)
        .order_by(Application.created_at.desc())
    )).scalars().all()
    out = []
    for a in apps:
        opp = (await session.execute(select(Opportunity, Company)
                                     .join(Company, Company.id == Opportunity.company_id)
                                     .where(Opportunity.id == a.opp_id))).first()
        evs = await events_for(session, "application", a.id)
        entry = _with_events(a, evs)
        entry["opportunity"] = {
            "id": opp[0].id, "title": opp[0].title, "kind": opp[0].kind,
            "company": opp[1].name, "location": opp[0].location,
        } if opp else None
        out.append(entry)
    return out


@router.get("/company/applications")
async def company_applications(opp_id: int | None = None,
                               user: User = Depends(require_roles("employer", "admin")),
                               session: AsyncSession = Depends(get_session)):
    q = select(Application, Opportunity, User).join(
        Opportunity, Opportunity.id == Application.opp_id).join(
        User, User.id == Application.user_id)
    if opp_id:
        q = q.where(Application.opp_id == opp_id)
    if user.company_id:
        q = q.where(Opportunity.company_id == user.company_id)
    rows = (await session.execute(q.order_by(Application.score.desc()))).all()
    out = []
    for a, opp, candidate in rows:
        evs = await events_for(session, "application", a.id)
        out.append({
            "id": a.id, "opp_id": a.opp_id, "opp_title": opp.title,
            "candidate_id": candidate.id, "candidate_name": candidate.name,
            "status": a.status, "score": a.score, "explanation": a.explanation,
            "feedback": a.feedback,
            "timeline": [{"type": e.event_type, "ts": e.ts.isoformat()} for e in evs],
        })
    return out


async def _auto_feedback(app: Application, session: AsyncSession) -> dict:
    """Rejection feedback auto-filled from the match explanation."""
    exp = app.explanation or {}
    near = exp.get("near_miss") or []
    deciding = near[0] if near else None
    bridges = []
    if deciding:
        skill_name = deciding.get("skill")
        tax = await load_taxonomy(session)
        sid = next((k for k, v in tax.skill_names.items() if v == skill_name), None)
        if sid:
            bridges = tax.courses_by_skill.get(sid, [])
    return {
        "headline": f"Deciding skill: {deciding['skill']} at {deciding['user_level']} vs required {deciding['required']}" if deciding else "Overall match below the bar for this cohort",
        "deciding_skill": deciding,
        "bridges": bridges or ["Explore My Learning Path for bridge courses"],
    }


async def _auto_placement_episode(app: Application, user: User,
                                  session: AsyncSession) -> None:
    """On acceptance, link training → placement → employment: create an active
    platform_placement episode + a pending employer validation request."""
    opp = (await session.execute(select(Opportunity).where(Opportunity.id == app.opp_id))).scalar_one_or_none()
    if opp is None or opp.kind == "gauntlet":
        return
    cohort_id = (await session.execute(
        select(CohortEnrollment.cohort_id)
        .where(CohortEnrollment.user_id == user.id, CohortEnrollment.status == "completed")
        .order_by(CohortEnrollment.completed_at.desc())
    )).scalars().first()
    start = date.today()
    episode = EmploymentEpisode(
        user_id=user.id, cohort_id=cohort_id, company_id=opp.company_id,
        employment_type="wage", role_title=opp.title, start_date=start,
        monthly_wage_start=None, monthly_wage_current=None,
        status="active", source="platform_placement", validation_status="pending",
    )
    session.add(episode)
    await session.flush()
    await record_event(session, "employment_episode", episode.id, "created",
                       {"source": "platform_placement", "application_id": app.id,
                        "company_id": opp.company_id})
    await notify(session, user.id, "placement_recorded", {
        "episode_id": episode.id, "company_id": opp.company_id, "role": opp.title,
    })


@router.post("/company/applications/{app_id}/status")
async def set_status(app_id: int, body: StatusBody,
                     user: User = Depends(require_roles("employer", "admin")),
                     session: AsyncSession = Depends(get_session)):
    app = (await session.execute(select(Application).where(Application.id == app_id))).scalar_one_or_none()
    if app is None:
        raise HTTPException(404, "Application not found")
    if body.status not in STATUS_FLOW + ["rejected"]:
        raise HTTPException(400, f"status must be in {STATUS_FLOW + ['rejected']}")
    if body.status == "accepted" and app.status != "offered":
        raise HTTPException(400, "Can only accept after an offer")

    app.status = body.status
    app.updated_at = datetime.now(timezone.utc)
    if body.status == "rejected":
        auto = await _auto_feedback(app, session)
        app.feedback = {**auto, **(body.feedback or {})}
    session.add(app)
    await session.flush()
    await record_event(session, "application", app.id, body.status,
                       {"by": user.name})
    await notify(session, app.user_id, f"application_{body.status}", {
        "application_id": app.id, "opp_id": app.opp_id,
        "feedback": app.feedback if body.status == "rejected" else None,
    })
    if body.status == "accepted":
        candidate = (await session.execute(select(User).where(User.id == app.user_id))).scalar_one_or_none()
        await _auto_placement_episode(app, candidate, session)
    await session.commit()
    return {"id": app.id, "status": app.status, "feedback": app.feedback}
