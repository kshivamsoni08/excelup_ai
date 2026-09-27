"""Outcomes aggregation service: DB rows -> pure outcomes engine.

All analytics are consent-scoped: wage statistics include only trainees with
an active department 'wage' consent; every statistic exposes n + coverage %.
Denominators are always completers. No PII ever leaves this module - only
aggregates (k-anonymity applied for demographic slices).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from statistics import median
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.engines.matching import match_user_to_opportunity
from app.engines.outcomes import (
    Episode,
    K_ANON,
    OQI_FORMULA,
    cell,
    followup_response_rate,
    oqi,
    placement_at_month,
    placement_day_rate,
    placement_decay_curve,
    programme_flags,
    retention_at,
    validation_rate,
    wage_curve,
    wage_growth_12,
)
from app.models.tables import (
    Cohort,
    CohortEnrollment,
    Company,
    Consent,
    EmploymentEpisode,
    FollowupAttempt,
    FollowupWave,
    Opportunity,
    OppRequirement,
    Programme,
    Provider,
    ReasonCode,
    Skill,
    TraineeProfile,
    User,
)
from app.services.consents import consented_user_ids
from app.services.proficiency import get_genome


async def _wage_consented(session: AsyncSession) -> set[int]:
    return await consented_user_ids(session, "wage", "department")


async def _any_consented(session: AsyncSession) -> set[int]:
    return await consented_user_ids(session, "outcomes", "department")


def _engine_episode(e: EmploymentEpisode, wages: dict[int, float]) -> Episode:
    return Episode(
        user_id=e.user_id,
        employment_type=e.employment_type,
        start=e.start_date,
        end=e.end_date,
        wage_start=e.monthly_wage_start,
        wages=wages,
        validation_status=e.validation_status,
        company_id=e.company_id,
    )


async def _programme_cohorts(session: AsyncSession, programme_id: int) -> list[Cohort]:
    return (await session.execute(
        select(Cohort).where(Cohort.programme_id == programme_id)
    )).scalars().all()


async def _completions_of_cohorts(session: AsyncSession,
                                  cohort_ids: list[int]) -> dict[int, date]:
    if not cohort_ids:
        return {}
    rows = (await session.execute(
        select(CohortEnrollment)
        .where(CohortEnrollment.cohort_id.in_(cohort_ids),
               CohortEnrollment.status == "completed",
               CohortEnrollment.completed_at.is_not(None))
    )).scalars().all()
    out: dict[int, date] = {}
    for ce in rows:
        c = ce.completed_at if isinstance(ce.completed_at, date) else None
        if c is None:
            continue
        if ce.user_id not in out or c < out[ce.user_id]:
            out[ce.user_id] = c
    return out


async def _episodes_of_users(session: AsyncSession,
                             user_ids: list[int]) -> list[Episode]:
    if not user_ids:
        return []
    eps = (await session.execute(
        select(EmploymentEpisode).where(EmploymentEpisode.user_id.in_(user_ids))
    )).scalars().all()
    wages_by_ep: dict[int, dict[int, float]] = defaultdict(dict)
    if eps:
        from app.models.tables import WageEvent

        we = (await session.execute(
            select(WageEvent).where(WageEvent.episode_id.in_([e.id for e in eps]))
        )).scalars().all()
        for w in we:
            wages_by_ep[w.episode_id][w.month_index] = w.monthly_wage
    return [_engine_episode(e, wages_by_ep.get(e.id, {})) for e in eps]


async def _attempts_of_cohorts(session: AsyncSession,
                               cohort_ids: list[int]) -> list[FollowupAttempt]:
    if not cohort_ids:
        return []
    waves = (await session.execute(
        select(FollowupWave).where(FollowupWave.cohort_id.in_(cohort_ids))
    )).scalars().all()
    if not waves:
        return []
    return (await session.execute(
        select(FollowupAttempt).where(FollowupAttempt.wave_id.in_([w.id for w in waves]))
    )).scalars().all()


def _sector_postings_yoy_from(sector: str, stats: dict) -> Optional[float]:
    return stats.get("sector_postings_yoy", {}).get(sector)


async def sector_stats(session: AsyncSession) -> dict[str, dict]:
    """Per sector: programme completions (for medians) + postings YoY."""
    programmes = (await session.execute(select(Programme))).scalars().all()
    prog_completions: dict[int, int] = {}
    for p in programmes:
        cohorts = await _programme_cohorts(session, p.id)
        comps = await _completions_of_cohorts(session, [c.id for c in cohorts])
        prog_completions[p.id] = len(comps)

    by_sector: dict[str, list[int]] = defaultdict(list)
    prog_sector: dict[int, str] = {}
    for p in programmes:
        by_sector[p.sector].append(prog_completions.get(p.id, 0))
        prog_sector[p.id] = p.sector

    sector_median_completions = {
        s: median(vals) if vals else 0.0 for s, vals in by_sector.items()}

    # postings YoY: last 12 months vs previous 12
    now = datetime.now(timezone.utc)
    cutoff = date(now.year, now.month, 1)
    opps = (await session.execute(
        select(Opportunity, Company).join(Company, Company.id == Opportunity.company_id)
    )).all()
    last12: Counter = Counter()
    prev12: Counter = Counter()
    for opp, comp in opps:
        d = opp.posted_at.date()
        months_ago = (cutoff.year - d.year) * 12 + (cutoff.month - d.month)
        sector = comp.sector or "other"
        if 0 <= months_ago < 12:
            last12[sector] += 1
        elif 12 <= months_ago < 24:
            prev12[sector] += 1
    yoy: dict[str, Optional[float]] = {}
    for s in set(last12) | set(prev12):
        prev = prev12.get(s, 0)
        yoy[s] = (last12.get(s, 0) - prev) / prev if prev else None

    return {"sector_median_completions": sector_median_completions,
            "sector_postings_yoy": yoy}


async def programme_row(session: AsyncSession, programme: Programme,
                        provider_name: str, stats: dict) -> dict:
    cohorts = await _programme_cohorts(session, programme.id)
    cohort_ids = [c.id for c in cohorts]
    completions = await _completions_of_cohorts(session, cohort_ids)
    episodes = await _episodes_of_users(session, list(completions))
    attempts = await _attempts_of_cohorts(session, cohort_ids)

    wage_ids = await _wage_consented(session)
    any_ids = await _any_consented(session)

    p0 = placement_day_rate(completions, episodes)
    p12 = placement_at_month(completions, episodes, 12)
    r12 = retention_at(episodes, 12, date.today())
    wage = wage_growth_12(episodes, wage_ids)
    v = validation_rate([e for e in episodes if e.employment_type == "wage"])  # wage episodes only
    f = followup_response_rate([{"responded": a.responded_at is not None,
                                 "response": a.response} for a in attempts])
    q = oqi(p12, r12, wage["growth"], v, f)
    flags = programme_flags(
        p0, p12, len(completions),
        stats["sector_median_completions"].get(programme.sector, 0.0),
        stats["sector_postings_yoy"].get(programme.sector),
    )
    covered = len([u for u in completions if u in any_ids])
    return {
        "programme_id": programme.id,
        "title": programme.title,
        "provider": provider_name,
        "sector": programme.sector,
        "nsqf_level": programme.nsqf_level,
        "completions": len(completions),
        "placement_0": round(p0, 4),
        "placement_12": round(p12, 4),
        "retention_12": round(r12, 4),
        "wage_growth_12": wage["growth"],
        "wage_n": wage["n"],
        "validation_rate": round(v, 4),
        "followup_rate": round(f, 4),
        "oqi": q["score"],
        "oqi_components": q["components"],
        "flags": flags,
        "consent": {"completers": len(completions),
                    "consented": covered,
                    "coverage_pct": round(100 * covered / max(len(completions), 1), 1)},
    }


async def programmes_table(session: AsyncSession,
                           view: str = "day0") -> dict:
    programmes = (await session.execute(
        select(Programme, Provider).join(Provider, Provider.id == Programme.provider_id)
    )).all()
    stats = await sector_stats(session)
    rows = [await programme_row(session, p, prov.name, stats) for p, prov in programmes]
    if view == "outcomes":
        rows.sort(key=lambda r: -r["oqi"])
    else:  # day0: the vanity ranking
        rows.sort(key=lambda r: (-r["placement_0"], -r["oqi"]))
    return {"view": view, "rows": rows, "oqi_formula": OQI_FORMULA,
            "flags_legend": {
                "vanity_metric": "placement-day rate far above 12-month outcomes",
                "oversupplied": "completions exceed sector demand and outcomes are weak",
                "obsolete": "sector postings declining > 25% YoY",
            }}


async def programme_detail(session: AsyncSession, programme_id: int) -> dict:
    programme = (await session.execute(
        select(Programme, Provider).join(Provider, Provider.id == Programme.provider_id)
        .where(Programme.id == programme_id)
    )).first()
    if programme is None:
        return {}
    p, prov = programme
    cohorts = await _programme_cohorts(session, p.id)
    cohort_ids = [c.id for c in cohorts]
    completions = await _completions_of_cohorts(session, cohort_ids)
    episodes = await _episodes_of_users(session, list(completions))
    attempts = await _attempts_of_cohorts(session, cohort_ids)
    wage_ids = await _wage_consented(session)
    any_ids = await _any_consented(session)

    p0 = placement_day_rate(completions, episodes)
    p12 = placement_at_month(completions, episodes, 12)
    r12 = retention_at(episodes, 12, date.today())
    wage = wage_growth_12(episodes, wage_ids)
    wage_eps = [e for e in episodes if e.employment_type == "wage"]
    v = validation_rate(wage_eps)
    f = followup_response_rate([{"responded": a.responded_at is not None,
                                 "response": a.response} for a in attempts])
    q = oqi(p12, r12, wage["growth"], v, f)
    stats = await sector_stats(session)
    flags = programme_flags(
        p0, p12, len(completions),
        stats["sector_median_completions"].get(p.sector, 0.0),
        stats["sector_postings_yoy"].get(p.sector))

    curve = placement_decay_curve(completions, episodes, [0, 3, 6, 12, 24])
    wages = wage_curve(episodes, wage_ids, max_month=24)
    wages = [w for w in wages if w["n"] > 0][:13]

    # attrition / non-placement reason Pareto
    codes_counter: Counter = Counter()
    for a in attempts:
        for code in (a.reason_codes or []):
            codes_counter[code] += 1
    reason_rows = (await session.execute(select(ReasonCode))).scalars().all()
    labels = {r.code: r.label for r in reason_rows}
    total_codes = sum(codes_counter.values())
    pareto = [{"code": c, "label": labels.get(c, c), "count": n,
               "share": round(n / total_codes, 4)}
              for c, n in codes_counter.most_common()]

    # demographic equity (k-anonymised)
    profiles = (await session.execute(
        select(TraineeProfile).where(TraineeProfile.user_id.in_(list(completions) or [0]))
    )).scalars().all()
    prof_by_user = {tp.user_id: tp for tp in profiles}
    demo = _demographic_slices(completions, episodes, prof_by_user, any_ids)

    # consent coverage banner
    covered = len([u for u in completions if u in any_ids])
    wage_covered = len([u for u in completions if u in wage_ids])

    gaps = await skill_gaps_for_cohorts(session, cohort_ids)

    return {
        "programme": {"id": p.id, "title": p.title, "sector": p.sector,
                      "provider": prov.name, "nsqf_level": p.nsqf_level,
                      "duration_months": p.duration_months},
        "cohorts": [{"id": c.id, "batch_code": c.batch_code,
                     "end_date": c.end_date.isoformat() if c.end_date else None}
                    for c in cohorts],
        "completions": len(completions),
        "placement_0": round(p0, 4), "placement_12": round(p12, 4),
        "retention_12": round(r12, 4),
        "wage_growth_12": wage["growth"], "wage_n": wage["n"],
        "validation_rate": round(v, 4), "followup_rate": round(f, 4),
        "oqi": q["score"], "oqi_components": q["components"],
        "oqi_formula": OQI_FORMULA, "flags": flags,
        "decay_curve": curve,
        "wage_curve": wages,
        "attrition_pareto": pareto,
        "demographics": demo,
        "skill_gaps": gaps,
        "consent": {"completers": len(completions), "consented": covered,
                    "wage_consented": wage_covered,
                    "coverage_pct": round(100 * covered / max(len(completions), 1), 1),
                    "wage_coverage_pct": round(100 * wage_covered / max(len(completions), 1), 1)},
    }


def _demographic_slices(completions: dict[int, date], episodes: list[Episode],
                        profiles: dict[int, TraineeProfile],
                        consented: set[int]) -> dict:
    """placement_12 by gender / social category, k-anonymised."""
    out = {"by_gender": [], "by_category": []}
    by_user: dict[int, list[Episode]] = defaultdict(list)
    for e in episodes:
        by_user[e.user_id].append(e)

    def placed12(uid: int, cdate: date) -> int:
        target = _add_months(cdate, 12)
        return int(any(e.employment_type in ("wage", "self_employed", "apprenticeship")
                       and e.start <= target and (e.end is None or e.end >= target)
                       for e in by_user.get(uid, [])))

    for field, key in (("gender", "by_gender"), ("social_category", "by_category")):
        buckets: dict[str, list[int]] = defaultdict(list)
        for uid, cdate in completions.items():
            tp = profiles.get(uid)
            val = getattr(tp, field, None) if tp else None
            if val:
                buckets[str(val)].append(placed12(uid, cdate) if uid in consented else 0)
        for val, vals in sorted(buckets.items()):
            rate = sum(vals) / len(vals) if vals else 0.0
            c = cell(round(rate, 4), len(vals), K_ANON)
            out[key].append({"value": str(val), "n": c["n"],
                             "suppressed": c["suppressed"],
                             "rate": None if c["suppressed"] else round(rate, 4)})
    return out


async def skill_gaps_for_cohorts(session: AsyncSession,
                                 cohort_ids: list[int]) -> dict:
    """§5.2 - for non-placed completers: run the existing coverage matcher
    against postings in their districts; aggregate near-miss skills."""
    completions = await _completions_of_cohorts(session, cohort_ids)
    if not completions:
        return {"non_placed": 0, "top_missing": [], "curriculum_updates": []}
    episodes = await _episodes_of_users(session, list(completions))
    by_user: dict[int, list[Episode]] = defaultdict(list)
    for e in episodes:
        by_user[e.user_id].append(e)
    non_placed = [uid for uid in completions
                  if not any(e.employment_type in ("wage", "self_employed", "apprenticeship")
                             for e in by_user.get(uid, []))]
    if not non_placed:
        return {"non_placed": 0, "top_missing": [], "curriculum_updates": []}

    # district of the cohorts' provider trainees (home district fallback)
    from app.models.tables import District, Provider

    cohort_rows = (await session.execute(
        select(Cohort, Programme, Provider)
        .join(Programme, Programme.id == Cohort.programme_id)
        .join(Provider, Provider.id == Programme.provider_id)
        .where(Cohort.id.in_(cohort_ids))
    )).all()
    district_ids = list({prov.district_id for _c, _p, prov in cohort_rows
                         if prov.district_id})
    # The programme's own sector: gaps must be diagnostic for THIS curriculum,
    # not noise from unrelated sectors sharing the district.
    sectors = list({p.sector for _c, p, _prov in cohort_rows})

    # postings in those districts AND the programme's sector
    opp_rows = (await session.execute(
        select(Opportunity).join(Company, Company.id == Opportunity.company_id)
        .where(Company.district_id.in_(district_ids or [0]),
               Company.sector.in_(sectors or ["_"]),
               Opportunity.status == "open", Opportunity.kind != "gauntlet")
    )).scalars().all()
    reqs = (await session.execute(
        select(OppRequirement).where(OppRequirement.opp_id.in_([o.id for o in opp_rows] or [0]))
    )).scalars().all()
    req_map: dict[int, list] = defaultdict(list)
    for r in reqs:
        req_map[r.opp_id].append(r)

    skills = {s.id: s for s in (await session.execute(select(Skill))).scalars().all()}
    from app.services.matching import build_prereq_index_from_db, courses_by_skill_map

    prereq_index = await build_prereq_index_from_db(session)
    courses_map = await courses_by_skill_map(session)

    missing: Counter = Counter()
    for uid in non_placed:
        genome = await get_genome(session, uid)
        user_skills = {e.skill_id: type("US", (), {"skill_id": e.skill_id,
                                                   "verified_floor": e.verified_floor,
                                                   "potential_ceiling": e.potential_ceiling,
                                                   "source": e.source})()
                       for e in genome}
        best: dict[str, float] = {}
        for opp in opp_rows:
            req_list = req_map.get(opp.id, [])
            if not req_list:
                continue
            res = match_user_to_opportunity(user_skills, req_list, prereq_index,
                                            {sid: s.name for sid, s in skills.items()},
                                            courses_by_skill=courses_map)
            for nm in res.explanation.near_miss:
                gap = nm["required"] - nm["user_level"]
                # hiring impact: essential + heavily weighted requirements block
                # placement; that is what a curriculum update must address first
                impact = (2.0 if nm.get("essential") else 1.0) * \
                    max(nm.get("weight", 1.0), 0.5) * gap
                prev = best.get(nm["skill"], 0.0)
                best[nm["skill"]] = max(prev, impact)
        for skill_name, impact in best.items():
            entry = missing.setdefault(skill_name, [0, 0.0])
            entry[0] += 1
            entry[1] += impact

    # Rank by hiring impact (sum over non-placed trainees), not raw count -
    # the most damaging missing skills surface first.
    ranked = sorted(missing.items(), key=lambda kv: (round(kv[1][1], 1), kv[1][0]),
                    reverse=True)
    top_missing = [{"skill": name, "trainees_missing": n, "impact": round(g, 1)}
                   for name, (n, g) in ranked[:8]]
    curriculum = [{"skill": t["skill"], "suggestion":
                   f"Add a hands-on module / bridge course for {t['skill']} "
                   f"({t['trainees_missing']} non-placed trainees need it)"}
                  for t in top_missing[:5]]
    return {"non_placed": len(non_placed),
            "completers": len(completions),
            "top_missing": top_missing,
            "curriculum_updates": curriculum}


def _add_months(d: date, months: int) -> date:
    mi = (d.month - 1) + months
    year, month = d.year + mi // 12, mi % 12 + 1
    day = d.day
    while day > 28:
        try:
            return date(year, month, day)
        except ValueError:
            day -= 1
    return date(year, month, day)


async def officer_dashboard(session: AsyncSession) -> dict:
    """Headline KPIs across the whole system."""
    programmes = (await session.execute(
        select(Programme, Provider).join(Provider, Provider.id == Programme.provider_id)
    )).all()
    stats = await sector_stats(session)
    rows = []
    for p, prov in programmes:
        cohorts = await _programme_cohorts(session, p.id)
        cohort_ids = [c.id for c in cohorts]
        completions = await _completions_of_cohorts(session, cohort_ids)
        if not completions:
            continue
        episodes = await _episodes_of_users(session, list(completions))
        attempts = await _attempts_of_cohorts(session, cohort_ids)
        wage_ids = await _wage_consented(session)
        p0 = placement_day_rate(completions, episodes)
        p12 = placement_at_month(completions, episodes, 12)
        r12 = retention_at(episodes, 12, date.today())
        wage = wage_growth_12(episodes, wage_ids)
        v = validation_rate([e for e in episodes if e.employment_type == "wage"])
        f = followup_response_rate([{"responded": a.responded_at is not None,
                                     "response": a.response} for a in attempts])
        q = oqi(p12, r12, wage["growth"], v, f)
        flags = programme_flags(
            p0, p12, len(completions),
            stats["sector_median_completions"].get(p.sector, 0.0),
            stats["sector_postings_yoy"].get(p.sector))
        rows.append({
            "programme_id": p.id, "title": p.title, "provider": prov.name,
            "sector": p.sector, "completions": len(completions),
            "placement_0": round(p0, 4), "placement_12": round(p12, 4),
            "retention_12": round(r12, 4), "wage_growth_12": wage["growth"],
            "wage_n": wage["n"], "validation_rate": round(v, 4),
            "followup_rate": round(f, 4), "oqi": q["score"], "flags": flags,
        })

    total_completers = sum(r["completions"] for r in rows)
    w_total = sum(r["completions"] for r in rows) or 1
    overall = {
        "completers": total_completers,
        "placement_0": round(sum(r["placement_0"] * r["completions"] for r in rows) / w_total, 4),
        "placement_12": round(sum(r["placement_12"] * r["completions"] for r in rows) / w_total, 4),
        "retention_12": round(sum(r["retention_12"] * r["completions"] for r in rows) / w_total, 4),
        "validation_rate": round(sum(r["validation_rate"] * r["completions"] for r in rows) / w_total, 4),
        "followup_rate": round(sum(r["followup_rate"] * r["completions"] for r in rows) / w_total, 4),
    }
    # follow-up + consent stats
    all_waves = (await session.execute(select(FollowupWave))).scalars().all()
    all_attempts = (await session.execute(select(FollowupAttempt))).scalars().all()
    consent_ids = await _any_consented(session)
    trainee_count = (await session.execute(
        select(User).where(User.role == "trainee"))).scalars().all()
    flagged = [r for r in rows if r["flags"]]
    return {
        "overall": overall,
        "wage_curve_overall": None,  # rendered from programme drill-downs
        "followups": {"waves": len(all_waves), "attempts": len(all_attempts),
                      "responded": sum(1 for a in all_attempts if a.responded_at is not None)},
        "consent_coverage": {"trainees": len(trainee_count),
                             "consented": len(consent_ids & {u.id for u in trainee_count})},
        "flagged_programmes": [{"programme_id": r["programme_id"], "title": r["title"],
                                "flags": r["flags"]} for r in flagged],
        "oqi_formula": OQI_FORMULA,
    }


async def district_heatmap(session: AsyncSession) -> dict:
    """District x sector -> OQI cell (episode counts attached)."""
    rows = (await session.execute(
        select(EmploymentEpisode, Company, District)
        .join(Company, Company.id == EmploymentEpisode.company_id)
        .join(District, District.id == Company.district_id)
    )).all()
    cells: dict[tuple[str, str], dict] = {}
    for ep, comp, district in rows:
        key = (district.name, comp.sector or "other")
        c = cells.setdefault(key, {"district": district.name, "sector": key[1],
                                   "episodes": 0, "active": 0})
        c["episodes"] += 1
        if ep.status == "active" and ep.employment_type in ("wage", "self_employed", "apprenticeship"):
            c["active"] += 1
    return {"cells": list(cells.values()),
            "note": "Positive-episode share by district x sector (employer-linked episodes)"}


async def demographic_overview(session: AsyncSession) -> dict:
    """Department-wide gender / category slices of placement_12, k-anonymised."""
    completions_all = (await session.execute(
        select(CohortEnrollment)
        .where(CohortEnrollment.status == "completed",
               CohortEnrollment.completed_at.is_not(None))
    )).scalars().all()
    completions: dict[int, date] = {}
    for ce in completions_all:
        c = ce.completed_at
        if ce.user_id not in completions or c < completions[ce.user_id]:
            completions[ce.user_id] = c
    episodes = await _episodes_of_users(session, list(completions))
    profiles = (await session.execute(select(TraineeProfile))).scalars().all()
    prof_by_user = {tp.user_id: tp for tp in profiles}
    any_ids = await _any_consented(session)
    demo = _demographic_slices(completions, episodes, prof_by_user, any_ids)
    consented_n = len([u for u in completions if u in any_ids])
    return {"total_completers": len(completions),
            "consented": consented_n,
            "coverage_pct": round(100 * consented_n / max(len(completions), 1), 1),
            **demo}
