"""Trainer routes (dormant portal): residency/FDP/consultancy marketplace + enrollment."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.db.engine import get_session
from app.models.tables import Company, Opportunity, User
from app.security import require_roles
from app.services.matching import load_taxonomy, requirements_for
from app.services.events import record_event
from app.services.notifications import notify

router = APIRouter(prefix="/faculty", tags=["faculty"])

FACULTY_KINDS = ("faculty_internship", "industrial_training", "fdp",
                 "consultancy", "training_program")


@router.get("/opportunities")
async def list_faculty_opportunities(kind: str | None = None,
                                     user: User = Depends(require_roles("trainer", "admin")),
                                     session: AsyncSession = Depends(get_session)):
    q = (select(Opportunity, Company)
         .join(Company, Company.id == Opportunity.company_id)
         .where(Opportunity.kind.in_(list(FACULTY_KINDS)), Opportunity.status == "open"))
    if kind:
        q = q.where(Opportunity.kind == kind)
    rows = (await session.execute(q.order_by(Opportunity.posted_at.desc()))).all()
    tax = await load_taxonomy(session)
    req_map = await requirements_for(session, [o.id for o, _c in rows])
    return [
        {
            "id": o.id, "kind": o.kind, "title": o.title,
            "description": o.description, "company": c.name,
            "location": o.location, "stipend": o.stipend, "duration": o.duration,
            "skills": [tax.skill_names.get(r.skill_id, "?")
                       for r in req_map.get(o.id, [])],
        }
        for o, c in rows
    ]


class EnrollBody(BaseModel):
    note: str = ""


# Reuse applications table for faculty enrollment (kind-scoped)
from app.models.tables import Application  # noqa: E402


@router.post("/opportunities/{opp_id}/enroll")
async def enroll(opp_id: int, body: EnrollBody,
                 user: User = Depends(require_roles("trainer", "admin")),
                 session: AsyncSession = Depends(get_session)):
    opp = (await session.execute(select(Opportunity).where(Opportunity.id == opp_id))).scalar_one_or_none()
    if opp is None or opp.kind not in FACULTY_KINDS:
        raise HTTPException(404, "Faculty opportunity not found")
    existing = (await session.execute(
        select(Application).where(Application.opp_id == opp_id, Application.user_id == user.id)
    )).scalar_one_or_none()
    if existing:
        return {"id": existing.id, "status": existing.status, "already": True}
    app = Application(opp_id=opp_id, user_id=user.id, score=0.0, explanation={},
                      status="applied")
    session.add(app)
    await session.flush()
    await record_event(session, "application", app.id, "applied", {"faculty": True})
    staff = (await session.execute(
        select(User).where(User.company_id == opp.company_id, User.role == "employer")
    )).scalars().all()
    for s in staff:
        await notify(session, s.id, "faculty_enrollment",
                     {"opp": opp.title, "faculty": user.name})
    await session.commit()
    return {"id": app.id, "status": app.status}
