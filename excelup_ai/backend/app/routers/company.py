"""Company routes: Blind Shortlisting.

GET /company/candidates/{opp_id} - ANONYMIZED genomes only: no name, college or
gender. Just an anon ref + genome + match score + explanation.
POST /company/shortlist {application_ids} - shortlisting unlocks identities
(name, college, portfolio links) and advances the pipeline.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.db.engine import get_session
from app.models.tables import Application, Opportunity, Provider, User
from app.security import require_roles
from app.services.events import record_event
from app.services.matching import (
    load_taxonomy,
    requirements_for,
    user_skill_map,
)
from app.engines.matching import match_user_to_opportunity
from app.services.notifications import notify
from app.services.proficiency import genome_to_json, get_genome

router = APIRouter(prefix="/company", tags=["company"])


@router.get("/candidates/{opp_id}")
async def candidates(opp_id: int, user: User = Depends(require_roles("employer", "admin")),
                     session: AsyncSession = Depends(get_session)):
    opp = (await session.execute(select(Opportunity).where(Opportunity.id == opp_id))).scalar_one_or_none()
    if opp is None:
        raise HTTPException(404, "Opportunity not found")
    if user.company_id and opp.company_id != user.company_id:
        raise HTTPException(403, "Not your company's posting")

    tax = await load_taxonomy(session)
    reqs = (await requirements_for(session, [opp_id])).get(opp_id, [])

    apps = (await session.execute(
        select(Application).where(Application.opp_id == opp_id)
        .order_by(Application.score.desc())
    )).scalars().all()

    out = []
    for a in apps:
        genome = await get_genome(session, a.user_id)
        skills = await user_skill_map(session, a.user_id)
        res = match_user_to_opportunity(skills, reqs, tax.prereq_index,
                                        tax.skill_names, tax.courses_by_skill) if reqs else None
        revealed = a.status not in ("applied", "viewed")
        out.append({
            "application_id": a.id,
            "anon_ref": f"CAND-{a.id:04d}",
            "revealed": revealed,
            "genome": genome_to_json(genome[:10]),
            "score": round(res.score * 100, 1) if res else a.score,
            "explanation": res.explanation.to_json() if res else (a.explanation or {}),
            "pipeline_status": a.status,
            # identity only present after shortlist
            "identity": None,
        })
    return {"opportunity_id": opp_id, "title": opp.title, "candidates": out}


class ShortlistBody(BaseModel):
    application_ids: list[int]


@router.post("/shortlist")
async def shortlist(body: ShortlistBody,
                    user: User = Depends(require_roles("employer", "admin")),
                    session: AsyncSession = Depends(get_session)):
    """Shortlisting reveals identities and moves applications to 'shortlisted'."""
    revealed = []
    for app_id in body.application_ids:
        app = (await session.execute(select(Application).where(Application.id == app_id))).scalar_one_or_none()
        if app is None:
            continue
        opp = (await session.execute(select(Opportunity).where(Opportunity.id == app.opp_id))).scalar_one_or_none()
        if user.company_id and opp and opp.company_id != user.company_id:
            continue
        if app.status in ("applied", "viewed"):
            app.status = "shortlisted"
            app.updated_at = datetime.now(timezone.utc)
            session.add(app)
            await session.flush()
            await record_event(session, "application", app.id, "shortlisted",
                               {"by": user.name})
            await notify(session, app.user_id, "application_shortlisted",
                         {"application_id": app.id, "opp_id": app.opp_id})
        candidate = (await session.execute(select(User).where(User.id == app.user_id))).scalar_one_or_none()
        prov_name = None
        if candidate and candidate.provider_id:
            prov = (await session.execute(select(Provider).where(Provider.id == candidate.provider_id))).scalar_one_or_none()
            prov_name = prov.name if prov else None
        revealed.append({
            "application_id": app.id,
            "name": candidate.name if candidate else None,
            "institution": prov_name,
            "headline": candidate.headline if candidate else None,
            "status": app.status,
        })
    await session.commit()
    return {"revealed": revealed}
