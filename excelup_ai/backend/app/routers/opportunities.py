"""Opportunity creation (Posting Builder) - company + faculty-facing.

Payload: kind, title, description, location, stipend, duration, rubric,
requirements: [{skill_id, min_level, weight, essential}].
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.db.engine import get_session
from app.models.tables import Company, Opportunity, OppRequirement, Skill, User
from app.security import get_current_user, require_roles
from app.services.events import record_event

router = APIRouter(tags=["opportunities"])

ALLOWED_KINDS = (
    "job", "internship", "apprenticeship", "live_project", "gauntlet",
    "faculty_internship", "industrial_training", "fdp", "consultancy",
    "training_program",
)
FACULTY_KINDS = ("faculty_internship", "industrial_training", "fdp",
                 "consultancy", "training_program")


class RequirementBody(BaseModel):
    skill_id: int
    min_level: float = 3.0
    weight: float = 1.0
    essential: bool = False


class PostingBody(BaseModel):
    kind: str
    title: str
    description: str = ""
    location: str = ""
    stipend: str = ""
    duration: str = ""
    rubric: Optional[dict] = None
    requirements: list[RequirementBody] = []


@router.post("/opportunities")
async def create_opportunity(body: PostingBody,
                             user: User = Depends(require_roles("employer", "admin")),
                             session: AsyncSession = Depends(get_session)):
    if body.kind not in ALLOWED_KINDS:
        raise HTTPException(400, f"kind must be one of {ALLOWED_KINDS}")
    if not body.title.strip():
        raise HTTPException(400, "title is required")
    if user.company_id is None and user.role != "admin":
        raise HTTPException(400, "Your account is not linked to a company")
    company_id = user.company_id
    if company_id is None:
        comp = (await session.execute(select(Company).limit(1))).scalar_one()
        company_id = comp.id

    # validate skills exist
    ids = [r.skill_id for r in body.requirements]
    if ids:
        found = (await session.execute(select(Skill).where(Skill.id.in_(ids)))).scalars().all()
        if len(found) != len(set(ids)):
            raise HTTPException(400, "One or more skill_ids do not exist")

    opp = Opportunity(
        company_id=company_id, kind=body.kind, title=body.title.strip(),
        description=body.description, location=body.location, stipend=body.stipend,
        duration=body.duration, rubric=body.rubric, status="open",
    )
    session.add(opp)
    await session.flush()
    for r in body.requirements:
        session.add(OppRequirement(opp_id=opp.id, skill_id=r.skill_id,
                                   min_level=r.min_level, weight=r.weight,
                                   essential=r.essential))
    await session.commit()
    await session.refresh(opp)
    await record_event(session, "opportunity", opp.id, "posted",
                       {"title": opp.title, "kind": opp.kind})
    return {"id": opp.id, "title": opp.title, "kind": opp.kind,
            "requirements": len(body.requirements)}
