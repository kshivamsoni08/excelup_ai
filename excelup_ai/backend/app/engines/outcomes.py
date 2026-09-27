"""Outcome Analytics engine (pure math, no DB) - the heart of Impact Intelligence.

EXACT RULES (spec 5.1):

- Denominators are ALWAYS completers, never enrolled.
- placement_0  = share of completers with an episode of type wage / self_employed /
  apprenticeship starting within 30 days of their completion date.
- placement_m  = share of completers with an ACTIVE (positive-type) episode at
  completion + m months.
- retention_m  = of episodes started at least m months ago: fraction with
  end_date NULL or end_date >= start_date + m months.
- wage_growth_12 = (median monthly wage at month 12 / median starting wage) - 1,
  computed ONLY over trainees with wage consent. Every stat exposes n.
- Follow-up response rate F = responded attempts / issued attempts.
- Validation rate V = validated wage episodes / reported wage episodes.
- OQI = 100 x (0.30*placement_12 + 0.25*retention_12 + 0.25*W + 0.10*V + 0.10*F)
  where W = clamp(wage_growth_12 / 0.30, 0, 1)   [30% growth = full marks]
- Flags: vanity_metric, oversupplied, obsolete.
- k-anonymity: demographic cells with n < k render "suppressed (n<5)".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from statistics import median
from typing import Optional

POSITIVE_TYPES = ("wage", "self_employed", "apprenticeship")
INCOME_TYPES = ("wage", "self_employed")  # income progression covers self-employment too
MONTHS_AFTER = 0.30  # wage growth that maps to full OQI marks
OQI_WEIGHTS = {"placement_12": 0.30, "retention_12": 0.25, "wage": 0.25,
               "validation": 0.10, "followup": 0.10}
K_ANON = 5


@dataclass
class Episode:
    """Minimal episode record the pure functions operate on."""

    user_id: int
    employment_type: str
    start: date
    end: Optional[date] = None
    wage_start: Optional[float] = None
    wages: dict[int, float] = field(default_factory=dict)  # month_index -> wage
    validation_status: str = "unvalidated"
    company_id: Optional[int] = None


# --------------------------------------------------------------- placements
def _positive(episodes: list[Episode]) -> list[Episode]:
    return [e for e in episodes if e.employment_type in POSITIVE_TYPES]


def placement_day_rate(completions: dict[int, date], episodes: list[Episode],
                       within_days: int = 30) -> float:
    """placement_0: share of completers placed within `within_days` of completion."""
    if not completions:
        return 0.0
    by_user: dict[int, list[Episode]] = {}
    for e in _positive(episodes):
        by_user.setdefault(e.user_id, []).append(e)
    placed = sum(
        1 for uid, cdate in completions.items()
        if any(0 <= (e.start - cdate).days <= within_days for e in by_user.get(uid, []))
    )
    return placed / len(completions)


def placement_at_month(completions: dict[int, date], episodes: list[Episode],
                       months: int, grace_days: int = 30) -> float:
    """placement_m: share of completers with an active positive episode at
    completion + m months. At m=0 this is the 30-day placement-day rate (an
    episode may start slightly after the completion date), keeping the decay
    curve anchored to placement_0."""
    if not completions:
        return 0.0
    by_user: dict[int, list[Episode]] = {}
    for e in _positive(episodes):
        by_user.setdefault(e.user_id, []).append(e)

    def _active_at(e: Episode, d: date) -> bool:
        return e.start <= d and (e.end is None or e.end >= d)

    placed = 0
    for uid, cdate in completions.items():
        if months == 0:
            if any(0 <= (e.start - cdate).days <= grace_days
                   for e in by_user.get(uid, [])):
                placed += 1
            continue
        target = _add_months(cdate, months)
        if any(_active_at(e, target) for e in by_user.get(uid, [])):
            placed += 1
    return placed / len(completions)


def placement_decay_curve(completions: dict[int, date], episodes: list[Episode],
                          months_list: list[int]) -> list[dict]:
    return [{"months": m,
             "rate": round(placement_at_month(completions, episodes, m), 4)}
            for m in months_list]


# --------------------------------------------------------------- retention
def retention_at(episodes: list[Episode], months: int, as_of: date) -> float:
    """Of episodes that started >= m months before as_of: fraction still alive
    at start + m months (end_date NULL counts as retained)."""
    started = [e for e in _positive(episodes)
               if e.start <= _add_months(as_of, -months)]
    if not started:
        return 0.0
    retained = sum(
        1 for e in started
        if e.end is None or e.end >= _add_months(e.start, months)
    )
    return retained / len(started)


# ------------------------------------------------------------------- wages
def wage_growth_12(episodes: list[Episode], consented_user_ids: set[int]) -> dict:
    """(median wage at month 12 / median start wage) - 1, wage-consented only.
    Self-employment income episodes count toward wage progression."""
    elig = [e for e in episodes
            if e.employment_type in INCOME_TYPES and e.user_id in consented_user_ids
            and e.wage_start]
    n = len(elig)
    if n == 0:
        return {"growth": None, "n": 0, "coverage": 0.0}
    at12 = []
    for e in elig:
        w = e.wages.get(12)
        if w is None:
            # fall back to the latest known wage if month 12 not yet reached
            later = [m for m in e.wages if m <= 12]
            w = e.wages[max(later)] if later else None
        at12.append(w if w is not None else e.wage_start)
    growth = (median(at12) / median(e.wage_start for e in elig)) - 1.0
    return {"growth": round(growth, 4), "n": n, "coverage": None}


def wage_curve(episodes: list[Episode], consented_user_ids: set[int],
               max_month: int = 24) -> list[dict]:
    """Median monthly income by month index across consented wage + self-employed
    episodes."""
    elig = [e for e in episodes
            if e.employment_type in INCOME_TYPES and e.user_id in consented_user_ids]
    out = []
    for m in range(0, max_month + 1):
        vals = [e.wages[m] for e in elig if m in e.wages]
        out.append({"month": m,
                    "median_wage": round(median(vals)) if vals else None,
                    "n": len(vals)})
    return out


# ---------------------------------------------------------- rates and OQI
def followup_response_rate(attempts: list[dict]) -> float:
    """F = responded / issued. attempts: [{responded: bool}]."""
    issued = len(attempts)
    if issued == 0:
        return 0.0
    responded = sum(1 for a in attempts
                    if a.get("responded") and a.get("response") != "no_response")
    return responded / issued


def validation_rate(episodes: list[Episode]) -> float:
    """V = validated wage episodes / reported wage episodes."""
    wage_eps = [e for e in episodes if e.employment_type == "wage"]
    if not wage_eps:
        return 0.0
    validated = sum(1 for e in wage_eps if e.validation_status == "validated")
    return validated / len(wage_eps)


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def oqi(placement_12: float, retention_12: float, wage_growth: Optional[float],
        validation_rate_v: float, followup_rate_f: float) -> dict:
    """Outcome-adjusted Quality Index, 0-100. Formula is displayed on screen."""
    w = 0.0 if wage_growth is None else _clamp01(wage_growth / MONTHS_AFTER)
    score = 100.0 * (
        OQI_WEIGHTS["placement_12"] * _clamp01(placement_12)
        + OQI_WEIGHTS["retention_12"] * _clamp01(retention_12)
        + OQI_WEIGHTS["wage"] * w
        + OQI_WEIGHTS["validation"] * _clamp01(validation_rate_v)
        + OQI_WEIGHTS["followup"] * _clamp01(followup_rate_f)
    )
    return {
        "score": round(score, 1),
        "components": {
            "placement_12": round(_clamp01(placement_12), 4),
            "retention_12": round(_clamp01(retention_12), 4),
            "wage_component": round(w, 4),
            "validation": round(_clamp01(validation_rate_v), 4),
            "followup": round(_clamp01(followup_rate_f), 4),
        },
        "wage_growth_used": wage_growth,
    }


OQI_FORMULA = ("OQI = 100 x (0.30 x placement_12 + 0.25 x retention_12 "
               "+ 0.25 x wage_growth_component + 0.10 x validation_rate "
               "+ 0.10 x followup_response_rate),  wage component = clamp(growth/30%, 0, 1)")


# ------------------------------------------------------------------ flags
def programme_flags(placement_0: float, placement_12: float,
                    completions: int, sector_median_completions: float,
                    sector_postings_yoy: Optional[float]) -> list[str]:
    """Auto flags:
    - vanity_metric: placement_0 - placement_12 > 0.25
    - oversupplied: completions > 2x sector median AND placement_12 < 0.5
      AND postings in sector declining YoY
    - obsolete: sector postings down > 25% YoY
    """
    flags: list[str] = []
    if placement_0 - placement_12 > 0.25:
        flags.append("vanity_metric")
    if (sector_median_completions > 0
            and completions > 2 * sector_median_completions
            and placement_12 < 0.5
            and sector_postings_yoy is not None and sector_postings_yoy < 0):
        flags.append("oversupplied")
    if sector_postings_yoy is not None and sector_postings_yoy <= -0.25:
        flags.append("obsolete")
    return flags


# ------------------------------------------------------------- k-anonymity
def suppressed(n: int, k: int = K_ANON) -> bool:
    return n < k


def cell(value: Optional[float], n: int, k: int = K_ANON) -> dict:
    """Render an aggregate cell with k-anonymity + n always attached."""
    if suppressed(n, k):
        return {"suppressed": True, "n": n, "value": None,
                "label": f"suppressed (n<{k})"}
    return {"suppressed": False, "n": n, "value": value, "label": None}


# ----------------------------------------------------------------- helpers
def _add_months(d: date, months: int) -> date:
    month_index = (d.month - 1) + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    # clamp day to end of month
    day = d.day
    while day > 28:
        try:
            return date(year, month, day)
        except ValueError:
            day -= 1
    return date(year, month, day)


def median_wage_at(episodes: list[Episode], month: int) -> Optional[float]:
    vals = [e.wages[month] for e in episodes if month in e.wages]
    return median(vals) if vals else None
