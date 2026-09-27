"""Runtime matching service - glue between the pure matching engine and the DB.

Stage 1 (retrieval) uses stored skill embeddings (pgvector column, precomputed
at seed time) to build user/posting profile vectors and cosine-shortlist.
Stage 2 (directed coverage) runs the pure engine per (user, opportunity).

Also implements the What-if Career Simulator (§5.5) as a pure re-run of
stage 2 with an overridden floor.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.engines.decay import freshness_factor
from app.engines.matching import (
    Explanation,
    MatchResult,
    Requirement,
    UserSkill,
    build_prereq_index,
    cosine,
    match_user_to_opportunity,
    posting_profile_vector,
)
from app.models.tables import (
    Company,
    Course,
    Opportunity,
    OppRequirement,
    Proficiency,
    Skill,
    SkillEdge,
)
from app.services.proficiency import get_genome


@dataclass
class Taxonomy:
    skill_names: dict[int, str]
    domains: dict[int, str]
    half_life: dict[int, str]
    prereq_index: dict[int, set[int]]
    embeddings: dict[int, list[float]]
    courses_by_skill: dict[int, list[str]]
    synonyms: dict[int, list[str]]


async def load_taxonomy(session: AsyncSession) -> Taxonomy:
    skills = (await session.execute(select(Skill))).scalars().all()
    edges = (await session.execute(select(SkillEdge))).scalars().all()
    courses = (await session.execute(select(Course))).scalars().all()

    skill_names = {s.id: s.name for s in skills}
    domains = {s.id: s.domain for s in skills}
    half_life = {s.id: s.half_life_class for s in skills}
    prereq_index = build_prereq_index([(e.src_id, e.dst_id) for e in edges
                                       if e.type == "prerequisite"])

    embeddings: dict[int, list[float]] = {}
    for s in skills:
        if s.embedding is not None:
            embeddings[s.id] = [float(x) for x in list(s.embedding)]

    courses_by_skill: dict[int, list[str]] = {}
    name_to_id = {v: k for k, v in skill_names.items()}
    for c in courses:
        for sk in (c.skills or []):
            sid = name_to_id.get(sk)
            if sid is not None:
                courses_by_skill.setdefault(sid, []).append(c.title)

    synonyms = {s.id: list(s.synonyms or []) for s in skills}
    return Taxonomy(skill_names, domains, half_life, prereq_index,
                    embeddings, courses_by_skill, synonyms)


async def user_skill_map(session: AsyncSession, user_id: int) -> dict[int, UserSkill]:
    genome = await get_genome(session, user_id)
    return {
        e.skill_id: UserSkill(
            skill_id=e.skill_id,
            verified_floor=e.verified_floor,
            potential_ceiling=e.potential_ceiling,
            source=e.source,
        )
        for e in genome
    }


async def build_prereq_index_from_db(session: AsyncSession) -> dict[int, set[int]]:
    """Prerequisite index straight from the DB (used by skill-gap diagnostics)."""
    edges = (await session.execute(select(SkillEdge))).scalars().all()
    return build_prereq_index([(e.src_id, e.dst_id) for e in edges if e.type == "prerequisite"])


async def courses_by_skill_map(session: AsyncSession) -> dict[int, list[str]]:
    """skill_id -> course titles that teach it (bridge suggestions)."""
    skills = (await session.execute(select(Skill.id, Skill.name))).all()
    name_to_id = {name: sid for sid, name in skills}
    courses = (await session.execute(select(Course))).scalars().all()
    out: dict[int, list[str]] = {}
    for c in courses:
        for sk in (c.skills or []):
            sid = name_to_id.get(sk)
            if sid is not None:
                out.setdefault(sid, []).append(c.title)
    return out


async def requirements_for(session: AsyncSession, opp_ids: list[int]) -> dict[int, list[Requirement]]:
    if not opp_ids:
        return {}
    reqs = (await session.execute(
        select(OppRequirement).where(OppRequirement.opp_id.in_(opp_ids))
    )).scalars().all()
    out: dict[int, list[Requirement]] = {}
    for r in reqs:
        out.setdefault(r.opp_id, []).append(
            Requirement(skill_id=r.skill_id, min_level=r.min_level,
                        weight=r.weight, essential=r.essential)
        )
    return out


async def score_opportunity(
    session: AsyncSession,
    user_skills: dict[int, UserSkill],
    opp: Opportunity,
    opp_reqs: list[Requirement],
    tax: Taxonomy,
    override_floor: Optional[dict[int, float]] = None,
) -> MatchResult:
    """Stage 2 for one (user, opportunity). override_floor supports the simulator."""
    if override_floor:
        patched = dict(user_skills)
        for sid, floor in override_floor.items():
            base = patched.get(sid)
            patched[sid] = UserSkill(
                skill_id=sid,
                verified_floor=floor,
                potential_ceiling=max(floor, base.potential_ceiling if base else floor),
                source=base.source if base else "assessment",
            )
        user_skills = patched
    return match_user_to_opportunity(
        user_skills, opp_reqs, tax.prereq_index, tax.skill_names,
        courses_by_skill=tax.courses_by_skill,
    )


@dataclass
class FeedEntry:
    opportunity: Opportunity
    company_name: str
    result: MatchResult


def _stipend_int(stipend: str) -> int:
    """Parse "₹15,000/month" style strings into a comparable integer."""
    digits = "".join(ch for ch in (stipend or "") if ch.isdigit())
    return int(digits) if digits else 0


async def feed_for_user(session: AsyncSession, user_id: int,
                        kinds: Optional[list[str]] = None,
                        location: Optional[str] = None,
                        min_stipend: Optional[int] = None,
                        skill_id: Optional[int] = None,
                        limit: int = 60) -> list[FeedEntry]:
    """Ranked opportunities with scores + explanations (student home feed)."""
    tax = await load_taxonomy(session)
    user_skills = await user_skill_map(session, user_id)

    q = select(Opportunity, Company).join(Company, Company.id == Opportunity.company_id).where(
        Opportunity.status == "open", Opportunity.kind != "gauntlet"
    )
    if kinds:
        q = q.where(Opportunity.kind.in_(kinds))
    if location:
        q = q.where(Opportunity.location.ilike(f"%{location}%"))
    opps = (await session.execute(q.order_by(Opportunity.posted_at.desc()))).all()

    req_map = await requirements_for(session, [o.id for o, _c in opps])

    entries: list[FeedEntry] = []
    for opp, company in opps:
        reqs = req_map.get(opp.id, [])
        if skill_id is not None and not any(r.skill_id == skill_id for r in reqs):
            continue
        if min_stipend is not None and _stipend_int(opp.stipend) < min_stipend:
            continue
        result = (
            match_user_to_opportunity(
                user_skills, reqs, tax.prereq_index, tax.skill_names,
                courses_by_skill=tax.courses_by_skill)
            if reqs else MatchResult(0.0, True, Explanation())
        )
        entries.append(FeedEntry(opp, company.name, result))

    entries.sort(key=lambda e: (-e.result.score, -e.result.eligible))
    return entries[:limit]


async def stage1_candidates(
    session: AsyncSession,
    opp_reqs: list[Requirement],
    candidates: dict[int, dict[int, float]],  # user_id -> {skill_id: floor}
    tax: Taxonomy,
    top: int = 500,
) -> list[int]:
    """Retrieval stage: rank candidate users by cosine(user_v, posting_v)."""
    profile = posting_profile_vector(opp_reqs, tax.embeddings)
    if profile is None:
        return list(candidates.keys())[:top]
    scored: list[tuple[float, int]] = []
    for uid, floors in candidates.items():
        acc = [0.0] * len(profile)
        for r in opp_reqs:
            floor = floors.get(r.skill_id)
            emb = tax.embeddings.get(r.skill_id)
            if floor is None or emb is None:
                continue
            for i, v in enumerate(emb):
                acc[i] += floor * r.weight * v
        n = sum(x * x for x in acc) ** 0.5
        if n == 0:
            continue
        u = [x / n for x in acc]
        scored.append((cosine(u, profile), uid))
    scored.sort(reverse=True)
    return [uid for _s, uid in scored[:top]]


async def what_if_simulator(
    session: AsyncSession,
    user_id: int,
    skill_id: int,
    hypothetical_level: float,
) -> dict:
    """§5.5: re-run matching for the user's top 10 postings with the override."""
    tax = await load_taxonomy(session)
    user_skills = await user_skill_map(session, user_id)

    opps = (await session.execute(
        select(Opportunity, Company)
        .join(Company, Company.id == Opportunity.company_id)
        .where(Opportunity.status == "open", Opportunity.kind != "gauntlet")
    )).all()
    req_map = await requirements_for(session, [o.id for o, _c in opps])

    base_entries: list[tuple[float, bool, Opportunity, str]] = []
    skill_req_postings: list[tuple[float, bool, Opportunity, str]] = []
    for opp, company in opps:
        reqs = req_map.get(opp.id, [])
        if not reqs:
            continue
        res = match_user_to_opportunity(user_skills, reqs, tax.prereq_index,
                                        tax.skill_names, tax.courses_by_skill)
        entry = (res.score, res.eligible, opp, company.name)
        base_entries.append(entry)
        if any(r.skill_id == skill_id for r in reqs):
            skill_req_postings.append(entry)
    base_entries.sort(key=lambda t: (t[0], t[1]), reverse=True)
    # top-10 base + every posting requiring this skill (bounded) so newly
    # unlocked roles are always visible to the student
    seen_ids = set()
    top10 = []
    for e in base_entries[:10] + skill_req_postings[:15]:
        if e[2].id not in seen_ids:
            seen_ids.add(e[2].id)
            top10.append(e)

    override = {skill_id: hypothetical_level}
    skill_name = tax.skill_names.get(skill_id, f"skill {skill_id}")

    override_floor = max(
        hypothetical_level,
        user_skills[skill_id].verified_floor if skill_id in user_skills else 0.0,
    )
    patched_skills = {
        **user_skills,
        skill_id: UserSkill(skill_id=skill_id, verified_floor=override_floor,
                            potential_ceiling=5.0),
    }

    results = []
    newly_eligible = []
    for score0, elig0, opp, company in top10:
        res1 = match_user_to_opportunity(
            patched_skills, req_map[opp.id], tax.prereq_index,
            tax.skill_names, tax.courses_by_skill)
        delta = res1.score - score0
        results.append({
            "opp_id": opp.id,
            "title": opp.title,
            "company": company,
            "kind": opp.kind,
            "score_before": round(score0 * 100, 1),
            "score_after": round(res1.score * 100, 1),
            "delta": round(delta * 100, 1),
            "eligible_before": elig0,
            "eligible_after": res1.eligible,
        })
        if res1.eligible and not elig0:
            newly_eligible.append(opp.title)

    return {
        "skill": skill_name,
        "hypothetical_level": hypothetical_level,
        "results": results,
        "newly_eligible": newly_eligible,
        "avg_delta": round(sum(r["delta"] for r in results) / max(len(results), 1), 1),
    }
