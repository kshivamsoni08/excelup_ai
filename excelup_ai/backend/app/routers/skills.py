"""Skills + Skill Genome routes: taxonomy search, genome with decayed state,
declared skills, skill gap report vs role genomes."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.db.engine import get_session
from app.models.tables import Opportunity, OppRequirement, Proficiency, Skill
from app.security import get_current_user, hash_password  # hash_password unused here
from app.models.tables import User
from app.services.matching import load_taxonomy, requirements_for, user_skill_map
from app.services.proficiency import genome_to_json, get_genome

router = APIRouter(tags=["skills"])


@router.get("/skills")
async def list_skills(session: AsyncSession = Depends(get_session),
                      search: Optional[str] = Query(None),
                      domain: Optional[str] = Query(None),
                      limit: int = 100):
    q = select(Skill)
    if search:
        like = f"%{search.lower()}%"
        q = q.where(Skill.name.ilike(like))
    if domain:
        q = q.where(Skill.domain == domain)
    skills = (await session.execute(q.order_by(Skill.name).limit(limit))).scalars().all()
    return [
        {"id": s.id, "name": s.name, "domain": s.domain, "nsqf_level": s.nsqf_level,
         "half_life_class": s.half_life_class, "synonyms": s.synonyms or []}
        for s in skills
    ]


@router.get("/skills/domains")
async def domains(session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(select(Skill.domain).distinct())).all()
    return sorted({r[0] for r in rows})


@router.get("/me/genome")
async def my_genome(user: User = Depends(get_current_user),
                    session: AsyncSession = Depends(get_session)):
    genome = await get_genome(session, user.id)
    return {"skills": genome_to_json(genome)}


class DeclaredSkillsBody(BaseModel):
    skill_ids: list[int]


@router.post("/me/declared-skills")
async def declare_skills(body: DeclaredSkillsBody,
                         user: User = Depends(get_current_user),
                         session: AsyncSession = Depends(get_session)):
    """Add unverified (dashed-border) skills: mu=3.0, sigma_sq=0.30, source='declared'."""
    from datetime import datetime, timezone

    tax = await load_taxonomy(session)
    created, skipped = [], []
    for sid in body.skill_ids:
        if sid not in tax.skill_names:
            skipped.append(sid)
            continue
        existing = (await session.execute(
            select(Proficiency).where(Proficiency.user_id == user.id, Proficiency.skill_id == sid)
        )).scalar_one_or_none()
        if existing:
            skipped.append(sid)
            continue
        session.add(Proficiency(
            user_id=user.id, skill_id=sid, mu=3.0, sigma_sq=0.30,
            source="declared", last_evidence_at=datetime.now(timezone.utc),
        ))
        created.append({"skill_id": sid, "name": tax.skill_names[sid]})
    await session.commit()
    return {"created": created, "skipped": skipped}


@router.get("/me/skill-gap/{role}")
async def skill_gap(role: str, user: User = Depends(get_current_user),
                    session: AsyncSession = Depends(get_session)):
    """Side-by-side gap report for a role genome (student flow)."""
    role_opp = (await session.execute(
        select(Opportunity)
        .where(Opportunity.title.ilike(f"%{role}%"), Opportunity.kind != "gauntlet")
        .order_by(Opportunity.posted_at.desc()).limit(1)
    )).scalar_one_or_none()
    if role_opp is None:
        role_opp = (await session.execute(
            select(Opportunity).where(Opportunity.kind != "gauntlet")
            .order_by(Opportunity.posted_at.desc()).limit(1)
        )).scalar_one_or_none()
    if role_opp is None:
        return {"role": role, "requirements": [], "gaps": []}

    tax = await load_taxonomy(session)
    reqs = (await requirements_for(session, [role_opp.id])).get(role_opp.id, [])
    user_skills = await user_skill_map(session, user.id)

    from app.engines.matching import UserSkill

    gaps = []
    for r in reqs:
        us = user_skills.get(r.skill_id)
        floor = us.verified_floor if us else 0.0
        ceiling = us.potential_ceiling if us else 0.0
        courses = tax.courses_by_skill.get(r.skill_id, [])
        gaps.append({
            "skill": tax.skill_names.get(r.skill_id, f"skill {r.skill_id}"),
            "required": r.min_level,
            "user_level": round(floor, 2),
            "user_ceiling": round(ceiling, 2),
            "essential": r.essential,
            "gap": round(max(0.0, r.min_level - floor), 2),
            "verified": bool(us and us.source in ("assessment", "gauntlet", "course")),
            "bridge_courses": courses,
        })
    gaps.sort(key=lambda g: -g["gap"])
    return {"role": role_opp.title, "opportunity_id": role_opp.id,
            "requirements": gaps}
