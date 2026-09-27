"""Proficiency service - evidence → recompute (§5.4) + genome reads (§5.2).

    score_s = 0.50*A_s + 0.35*E_s + 0.15*V_s

    A_s = latest assessment level (0 if none)
    E_s = best artifact evidence strength:
          gauntlet-approved=1.0, verified cert=0.8, completed course=0.7, else 0
    V_s = 0.6 if ≥1 peer/mentor vouch exists, else 0

Recomputed on every evidence event; every change appends to proficiency_history.
All genome reads pass through the decay engine to get floor/ceiling.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.engines.decay import EffectiveSkill, effective_skill
from app.models.tables import (
    AssessSession,
    Artifact,
    Enrollment,
    Proficiency,
    ProficiencyHistory,
    Skill,
)
from app.services.notifications import notify

WEIGHTS = {"assessment": 0.50, "evidence": 0.35, "vouch": 0.15}
SIGMA_SQ_ON_EVIDENCE = 0.10


async def latest_assessment_level(session: AsyncSession, user_id: int, skill_id: int) -> float:
    from app.engines.irt import theta_to_level

    res = await session.execute(
        select(AssessSession)
        .where(AssessSession.user_id == user_id,
               AssessSession.skill_id == skill_id,
               AssessSession.status == "completed")
        .order_by(AssessSession.completed_at.desc())
        .limit(1)
    )
    s = res.scalar_one_or_none()
    return round(theta_to_level(s.theta), 3) if s else 0.0


async def best_evidence_strength(session: AsyncSession, user_id: int, skill_id: int, skill_name: str) -> tuple[float, str]:
    """Returns (strength 0..1, kind) from artifacts + completed courses."""
    best, kind = 0.0, ""
    arts = (await session.execute(
        select(Artifact).where(Artifact.user_id == user_id)
    )).scalars().all()
    for a in arts:
        payload = a.payload or {}
        skills = payload.get("skills") or ([payload.get("skill")] if payload.get("skill") else [])
        if skill_name not in skills:
            continue
        if a.kind == "gauntlet" and a.verification == "verified":
            if best < 1.0:
                best, kind = 1.0, "gauntlet"
        elif a.kind == "certificate" and a.verification == "verified":
            if best < 0.8:
                best, kind = 0.8, "certificate"
        elif a.verification == "verified":
            if best < 0.5:
                best, kind = 0.5, "artifact"
    # completed courses covering this skill
    enrolls = (await session.execute(
        select(Enrollment).where(Enrollment.user_id == user_id,
                                 Enrollment.status == "completed")
    )).scalars().all()
    if enrolls:
        from app.models.tables import Course

        course_ids = [e.course_id for e in enrolls]
        courses = (await session.execute(
            select(Course).where(Course.id.in_(course_ids))
        )).scalars().all()
        for c in courses:
            if skill_name in (c.skills or []):
                if best < 0.7:
                    best, kind = 0.7, "course"
    return best, kind


async def has_vouch(session: AsyncSession, user_id: int, skill_id: int) -> bool:
    res = await session.execute(
        select(Proficiency).where(Proficiency.user_id == user_id,
                                  Proficiency.skill_id == skill_id,
                                  Proficiency.source == "vouch")
    )
    return res.scalar_one_or_none() is not None


def _pick_source(a_level: float, e_strength: float, e_kind: str, had_vouch: bool,
                 current: Optional[Proficiency]) -> str:
    if e_kind == "gauntlet":
        return "gauntlet"
    if a_level > 0:
        return "assessment"
    if e_kind == "course":
        return "course"
    if e_kind == "certificate":
        return "assessment"  # verified certification acts like assessed proof
    if had_vouch:
        return "vouch"
    return current.source if current else "declared"


async def recompute_proficiency(session: AsyncSession, user_id: int, skill_id: int) -> Optional[Proficiency]:
    """Recompute (mu, sigma_sq) from all evidence and persist + append history."""
    skill = (await session.execute(select(Skill).where(Skill.id == skill_id))).scalar_one_or_none()
    if skill is None:
        return None

    a_level = await latest_assessment_level(session, user_id, skill_id)
    e_strength, e_kind = await best_evidence_strength(session, user_id, skill_id, skill.name)
    had_vouch = await has_vouch(session, user_id, skill_id)
    v_score = 0.6 if had_vouch else 0.0

    # Composite (§5.4) blended with channel level-equivalents so strong proof
    # is never downgraded and a company-approved gauntlet visibly jumps the
    # genome: assessment alone -> mu = A (§5.1); gauntlet approval attests
    # ~4.5; verified certificate ~4.0; completed course ~3.5. Capped at 5.
    channel_level = {1.0: 4.5, 0.8: 4.0, 0.7: 3.5}.get(e_strength, 0.0)
    composite = (WEIGHTS["assessment"] * a_level + WEIGHTS["evidence"] * e_strength
                 + WEIGHTS["vouch"] * v_score)
    mu_new = max(composite, a_level, channel_level)

    current = (await session.execute(
        select(Proficiency).where(Proficiency.user_id == user_id, Proficiency.skill_id == skill_id)
    )).scalar_one_or_none()

    source = _pick_source(a_level, e_strength, e_kind, had_vouch, current)

    if current is None:
        prof = Proficiency(
            user_id=user_id, skill_id=skill_id, mu=round(mu_new, 3),
            sigma_sq=SIGMA_SQ_ON_EVIDENCE, source=source,
            last_evidence_at=datetime.now(timezone.utc),
        )
        session.add(prof)
        current = prof
    else:
        current.mu = round(mu_new, 3)
        current.sigma_sq = SIGMA_SQ_ON_EVIDENCE
        current.source = source
        current.last_evidence_at = datetime.now(timezone.utc)
        session.add(current)

    session.add(ProficiencyHistory(user_id=user_id, skill_id=skill_id,
                                   mu=current.mu, sigma_sq=current.sigma_sq))
    await session.commit()
    await session.refresh(current)
    return current


async def get_genome(session: AsyncSession, user_id: int) -> list[EffectiveSkill]:
    """Effective (decayed) view of every proficiency the user holds."""
    res = await session.execute(
        select(Proficiency, Skill)
        .join(Skill, Skill.id == Proficiency.skill_id)
        .where(Proficiency.user_id == user_id)
    )
    out: list[EffectiveSkill] = []
    for prof, skill in res.all():
        out.append(effective_skill(
            skill_id=skill.id, name=skill.name, domain=skill.domain,
            half_life_class=skill.half_life_class, mu=prof.mu,
            sigma_sq=prof.sigma_sq, source=prof.source,
            last_evidence_at=prof.last_evidence_at,
        ))
    out.sort(key=lambda e: -e.verified_floor)
    return out


async def record_evidence_and_notify(session: AsyncSession, user_id: int, skill_id: int,
                                     kind: str, detail: dict | None = None):
    """Single entry point for evidence events: recompute + notify."""
    prof = await recompute_proficiency(session, user_id, skill_id)
    skill = (await session.execute(select(Skill).where(Skill.id == skill_id))).scalar_one_or_none()
    await notify(session, user_id, f"evidence_{kind}", {
        "skill": skill.name if skill else f"skill {skill_id}",
        "mu": prof.mu if prof else None,
        **(detail or {}),
    })
    return prof


def genome_to_json(genome: list[EffectiveSkill]) -> list[dict]:
    return [
        {
            "skill_id": e.skill_id,
            "name": e.name,
            "domain": e.domain,
            "half_life_class": e.half_life_class,
            "mu_stored": round(e.mu_stored, 2),
            "mu_effective": round(e.mu_effective, 2),
            "verified_floor": round(e.verified_floor, 2),
            "potential_ceiling": round(e.potential_ceiling, 2),
            "sigma": round(e.sigma_effective, 2),
            "source": e.source,
            "is_verified": e.is_verified,
            "last_evidence_at": e.last_evidence_at.isoformat(),
            "months_stale": round(e.months_stale, 1),
            "faded": e.faded,
        }
        for e in genome
    ]
