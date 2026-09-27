"""Provider routes (formerly institution): JRI cohort view, growth, verification queue.

Outcome analytics for the provider's own programmes now live in the new
/provider/dashboard (outcomes.py service). This module keeps the trainee-side
JRI (Job-Readiness Index, formerly PRI) with the published formula, skill
growth and artifact verification.
"""
from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.db.engine import get_session
from app.engines.decay import freshness_factor
from app.models.tables import (
    Application,
    Artifact,
    AssessSession,
    Cohort,
    CohortEnrollment,
    Opportunity,
    ProficiencyHistory,
    TraineeProfile,
    User,
)
from app.security import require_roles
from app.services.events import events_for, record_event
from app.services.matching import load_taxonomy, requirements_for
from app.services.notifications import notify
from app.services.proficiency import get_genome

router = APIRouter(prefix="/provider", tags=["provider"])


async def _my_trainees(session: AsyncSession, user: User) -> list[User]:
    """Trainees enrolled in this provider's cohorts (or all if platform admin view)."""
    if user.provider_id is None:
        return (await session.execute(
            select(User).where(User.role == "trainee")
        )).scalars().all()
    rows = (await session.execute(
        select(User)
        .join(CohortEnrollment, CohortEnrollment.user_id == User.id)
        .join(Cohort, CohortEnrollment.cohort_id == Cohort.id)
        .where(User.role == "trainee")
        .distinct()
    )).scalars().all()
    return [u for u in rows]


@router.get("/dashboard")
async def dashboard(user: User = Depends(require_roles("provider", "admin")),
                    session: AsyncSession = Depends(get_session)):
    trainees = await _my_trainees(session, user)
    tax = await load_taxonomy(session)
    skill_counter: Counter = Counter()
    gap_counter: Counter = Counter()
    participation = {"assessments": 0, "resumes_scanned": 0, "challenges_approved": 0}
    at_risk = []
    jri_values = []

    opps = (await session.execute(
        select(Opportunity).where(Opportunity.kind != "gauntlet")
    )).scalars().all()
    req_map = await requirements_for(session, [o.id for o in opps])
    role_reqs: dict[str, list] = {}
    for o in opps:
        role_reqs.setdefault(o.title, req_map.get(o.id, []))

    for stu in trainees:
        genome = await get_genome(session, stu.id)
        for e in genome:
            skill_counter[e.name] += 1
        tp = (await session.execute(
            select(TraineeProfile).where(TraineeProfile.user_id == stu.id)
        )).scalar_one_or_none()
        target = tp.target_role if tp else ""
        role_key = next((t for t in role_reqs if target and target.lower() in t.lower()), None)
        if role_key:
            held = {e.skill_id for e in genome}
            for r in role_reqs[role_key]:
                if r.skill_id not in held:
                    gap_counter[tax.skill_names.get(r.skill_id, "?")] += 1
        jri, components = await _jri_for_trainee(session, stu, tax, role_reqs, genome)
        jri_values.append((stu.id, stu.name, jri, target))
        if jri < 40:
            at_risk.append({"id": stu.id, "name": stu.name, "jri": round(jri, 1),
                            "target_role": target})

    counts = (await session.execute(
        select(AssessSession.user_id, func.count())
        .where(AssessSession.status == "completed",
               AssessSession.user_id.in_([s.id for s in trainees] or [0]))
        .group_by(AssessSession.user_id)
    )).all()
    participation["assessments"] = sum(c for _u, c in counts)
    participation["trainees_assessed"] = len(counts)

    verified_gauntlets = (await session.execute(
        select(Artifact).where(Artifact.kind == "gauntlet", Artifact.verification == "verified",
                               Artifact.user_id.in_([s.id for s in trainees] or [0]))
    )).scalars().all()
    participation["challenges_approved"] = len(verified_gauntlets)

    accepted = (await session.execute(
        select(Application).where(Application.status == "accepted",
                                  Application.user_id.in_([s.id for s in trainees] or [0]))
    )).scalars().all()
    placements = len(accepted)

    top_skills = [{"skill": n, "count": c} for n, c in skill_counter.most_common(10)]
    top_gaps = [{"skill": n, "count": c} for n, c in gap_counter.most_common(10)]
    jri_sorted = sorted(jri_values, key=lambda x: x[2], reverse=True)

    return {
        "trainees": len(trainees),
        "top_skills": top_skills,
        "top_gaps": top_gaps,
        "participation": participation,
        "placements": placements,
        "at_risk": at_risk[:20],
        "jri_mean": round(sum(p for _i, _n, p, _t in jri_values) / max(len(jri_values), 1), 1),
        "jri_histogram": _histogram([p for _i, _n, p, _t in jri_values]),
        "jri_formula": JRI_FORMULA,
        "top_trainees": [{"id": i, "name": n, "jri": round(p, 1), "target_role": t}
                         for i, n, p, t in jri_sorted[:10]],
    }


JRI_FORMULA = (
    "JRI = 0.35×essential_coverage + 0.25×portfolio_depth + 0.15×freshness "
    "+ 0.15×SJT + 0.10×interview_readiness"
)


def _histogram(values: list[float], bins=10) -> list[dict]:
    if not values:
        return [{"bin": f"{i * 10}-{(i + 1) * 10}", "count": 0} for i in range(bins)]
    counts = [0] * bins
    for v in values:
        idx = min(bins - 1, max(0, int(v // 10)))
        counts[idx] += 1
    return [{"bin": f"{i * 10}-{(i + 1) * 10}", "count": counts[i]} for i in range(bins)]


async def _jri_for_trainee(session, stu, tax, role_reqs, genome) -> tuple[float, dict]:
    from app.engines.matching import UserSkill

    tp = (await session.execute(
        select(TraineeProfile).where(TraineeProfile.user_id == stu.id)
    )).scalar_one_or_none()
    target = (tp.target_role if tp else "") or ""
    role_key = next((t for t in role_reqs if target and target.lower() in t.lower()), None)

    if role_key:
        skills = {e.skill_id: UserSkill(e.skill_id, e.verified_floor,
                                        e.potential_ceiling, e.source) for e in genome}
        from app.engines.matching import match_user_to_opportunity

        res = match_user_to_opportunity(skills, role_reqs[role_key], tax.prereq_index,
                                        tax.skill_names, tax.courses_by_skill)
        coverage = res.score
    else:
        coverage = 0.0

    arts = (await session.execute(
        select(Artifact).where(Artifact.user_id == stu.id, Artifact.verification == "verified")
    )).scalars().all()
    portfolio_depth = min(1.0, len(arts) / 5.0)

    top5 = sorted(genome, key=lambda e: -e.verified_floor)[:5]
    freshness = (sum(freshness_factor(e.half_life_class, e.months_stale) for e in top5)
                 / max(len(top5), 1))

    sjt = 0.5
    done = (await session.execute(
        select(AssessSession).where(AssessSession.user_id == stu.id,
                                    AssessSession.status == "completed")
    )).scalars().all()
    soft_names = {"Communication", "Teamwork", "Aptitude", "Workplace Communication"}
    soft_levels = []
    for s in done:
        if tax.skill_names.get(s.skill_id, "") in soft_names:
            from app.engines.irt import theta_to_level

            soft_levels.append(theta_to_level(s.theta) / 5.0)
    sjt = (sum(soft_levels) / len(soft_levels)) if soft_levels else 0.5

    apps = (await session.execute(
        select(Application).where(Application.user_id == stu.id)
    )).scalars().all()
    interview_count = 0
    for a in apps:
        evs = await events_for(session, "application", a.id)
        interview_count += sum(1 for e in evs if e.event_type == "interviewed")
    interview_readiness = min(1.0, 0.2 * interview_count)

    jri = (0.35 * coverage + 0.25 * portfolio_depth + 0.15 * freshness
           + 0.15 * sjt + 0.10 * interview_readiness) * 100.0
    return jri, {
        "coverage": round(coverage * 100, 1),
        "portfolio_depth": round(portfolio_depth * 100, 1),
        "freshness": round(freshness * 100, 1),
        "sjt": round(sjt * 100, 1),
        "interview_readiness": round(interview_readiness * 100, 1),
    }


@router.get("/jri")
async def jri(user: User = Depends(require_roles("provider", "admin")),
              session: AsyncSession = Depends(get_session)):
    trainees = await _my_trainees(session, user)
    tax = await load_taxonomy(session)
    opps = (await session.execute(
        select(Opportunity).where(Opportunity.kind != "gauntlet")
    )).scalars().all()
    req_map = await requirements_for(session, [o.id for o in opps])
    role_reqs = {}
    for o in opps:
        role_reqs.setdefault(o.title, req_map.get(o.id, []))

    out = []
    for stu in trainees:
        genome = await get_genome(session, stu.id)
        jri, components = await _jri_for_trainee(session, stu, tax, role_reqs, genome)
        tp = (await session.execute(
            select(TraineeProfile).where(TraineeProfile.user_id == stu.id)
        )).scalar_one_or_none()
        out.append({"id": stu.id, "name": stu.name, "jri": round(jri, 1),
                    "components": components,
                    "target_role": tp.target_role if tp else ""})
    out.sort(key=lambda x: -x["jri"])
    return {"trainees": out, "formula": JRI_FORMULA,
            "histogram": _histogram([t["jri"] for t in out])}


@router.get("/growth")
async def growth(user: User = Depends(require_roles("provider", "admin")),
                 session: AsyncSession = Depends(get_session)):
    """Skill trajectories from proficiency_history (cohort mean per month)."""
    trainees = await _my_trainees(session, user)
    ids = [s.id for s in trainees] or [0]
    rows = (await session.execute(
        select(ProficiencyHistory)
        .where(ProficiencyHistory.user_id.in_(ids))
        .order_by(ProficiencyHistory.ts)
    )).scalars().all()

    tax = await load_taxonomy(session)
    by_month_skill: dict[tuple[str, str], list[float]] = {}
    for h in rows:
        month = h.ts.strftime("%Y-%m")
        key = (month, tax.skill_names.get(h.skill_id, f"skill {h.skill_id}"))
        by_month_skill.setdefault(key, []).append(h.mu)
    series: dict[str, dict[str, float]] = {}
    for (month, skill), mus in by_month_skill.items():
        series.setdefault(skill, {})[month] = round(sum(mus) / len(mus), 2)
    return {"series": series, "formula": "Cohort mean μ per month from proficiency_history"}


@router.post("/artifacts/{artifact_id}/verify")
async def verify_artifact(artifact_id: int,
                          user: User = Depends(require_roles("provider", "admin")),
                          session: AsyncSession = Depends(get_session)):
    a = (await session.execute(select(Artifact).where(Artifact.id == artifact_id))).scalar_one_or_none()
    if a is None:
        raise HTTPException(404, "Artifact not found")
    a.verification = "verified"
    session.add(a)
    await session.flush()
    await record_event(session, "artifact", a.id, "verified", {"by": user.name})
    await notify(session, a.user_id, "artifact_verified", {"artifact": a.title})
    await session.commit()
    return {"id": a.id, "verification": a.verification}
