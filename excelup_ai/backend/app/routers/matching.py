"""Matching + opportunities + simulator routes.

- GET /feed: ranked opportunities with scores + explanations ("Why You Matched")
- GET /opportunities: filters (kind, location, stipend, skill)
- GET /opportunities/{id}, /opportunities/{id}/why-match
- POST /simulator/what-if (§5.5)
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.db.engine import get_session
from app.models.tables import Company, Opportunity, OppRequirement, Skill, User
from app.security import get_current_user
from app.services.matching import (
    load_taxonomy,
    requirements_for,
    user_skill_map,
    what_if_simulator,
)
from app.services.proficiency import get_genome

router = APIRouter(tags=["matching"])


def _opp_json(opp: Opportunity, company: str | None = None, reqs=None, tax=None):
    return {
        "id": opp.id, "kind": opp.kind, "title": opp.title,
        "description": opp.description, "location": opp.location,
        "stipend": opp.stipend, "duration": opp.duration,
        "rubric": opp.rubric, "status": opp.status, "posted_at": opp.posted_at.isoformat(),
        "company": company,
        "requirements": ([
            {"skill": tax.skill_names.get(r.skill_id, f"skill {r.skill_id}"),
             "skill_id": r.skill_id, "min_level": r.min_level, "weight": r.weight,
             "essential": r.essential}
            for r in (reqs or [])
        ] if reqs is not None and tax is not None else None),
    }


@router.get("/feed")
async def feed(user: User = Depends(get_current_user),
               session: AsyncSession = Depends(get_session)):
    from app.services.matching import feed_for_user

    entries = await feed_for_user(session, user.id)
    tax = await load_taxonomy(session)
    req_map = await requirements_for(session, [e.opportunity.id for e in entries])
    out = []
    for e in entries:
        item = _opp_json(e.opportunity, e.company_name,
                         req_map.get(e.opportunity.id, []), tax)
        item["match"] = {
            "score": round(e.result.score * 100, 1),
            "eligible": e.result.eligible,
            "explanation": e.result.explanation.to_json(),
        }
        out.append(item)
    return out


@router.get("/opportunities")
async def list_opportunities(session: AsyncSession = Depends(get_session),
                             kind: Optional[str] = Query(None),
                             location: Optional[str] = Query(None),
                             min_stipend: Optional[int] = Query(None),
                             skill: Optional[str] = Query(None)):
    q = select(Opportunity, Company).join(Company, Company.id == Opportunity.company_id).where(
        Opportunity.status == "open")
    if kind:
        q = q.where(Opportunity.kind == kind)
    if location:
        q = q.where(Opportunity.location.ilike(f"%{location}%"))
    rows = (await session.execute(q.order_by(Opportunity.posted_at.desc()))).all()

    tax = await load_taxonomy(session)
    req_map = await requirements_for(session, [o.id for o, _c in rows])
    out = []
    for opp, company in rows:
        reqs = req_map.get(opp.id, [])
        if skill:
            s = skill.lower()
            if not any(tax.skill_names.get(r.skill_id, "").lower() == s
                       or s in tax.skill_names.get(r.skill_id, "").lower()
                       for r in reqs):
                continue
        if min_stipend is not None:
            digits = "".join(ch for ch in (opp.stipend or "") if ch.isdigit())
            if digits and int(digits) < min_stipend:
                continue
        out.append(_opp_json(opp, company.name, reqs, tax))
    return out


@router.get("/opportunities/{opp_id}")
async def opportunity_detail(opp_id: int, session: AsyncSession = Depends(get_session)):
    row = (await session.execute(
        select(Opportunity, Company)
        .join(Company, Company.id == Opportunity.company_id)
        .where(Opportunity.id == opp_id)
    )).first()
    if row is None:
        raise HTTPException(404, "Opportunity not found")
    opp, company = row
    tax = await load_taxonomy(session)
    reqs = (await requirements_for(session, [opp_id])).get(opp_id, [])
    return _opp_json(opp, company.name, reqs, tax)


@router.get("/opportunities/{opp_id}/why-match")
async def why_match(opp_id: int, user: User = Depends(get_current_user),
                    session: AsyncSession = Depends(get_session)):
    from app.engines.matching import match_user_to_opportunity

    opp = (await session.execute(select(Opportunity).where(Opportunity.id == opp_id))).scalar_one_or_none()
    if opp is None:
        raise HTTPException(404, "Opportunity not found")
    tax = await load_taxonomy(session)
    reqs = (await requirements_for(session, [opp_id])).get(opp_id, [])
    user_skills = await user_skill_map(session, user.id)
    res = match_user_to_opportunity(user_skills, reqs, tax.prereq_index,
                                    tax.skill_names, tax.courses_by_skill)
    return {
        "opportunity_id": opp_id,
        "title": opp.title,
        "score": round(res.score * 100, 1),
        **res.explanation.to_json(),
    }


class WhatIfBody(BaseModel):
    skill_id: int
    hypothetical_level: float


@router.post("/simulator/what-if")
async def simulator(body: WhatIfBody, user: User = Depends(get_current_user),
                    session: AsyncSession = Depends(get_session)):
    if not (0 <= body.hypothetical_level <= 5):
        raise HTTPException(400, "hypothetical_level must be 0..5")
    return await what_if_simulator(session, user.id, body.skill_id,
                                   body.hypothetical_level)
