"""Skill decay engine.

Proficiencies are stored as (mu, sigma_sq, last_evidence_at). Effective state at t:

    mu_eff(t)    = 0.2 + (mu - 0.2) * 2^(-months_since_evidence / H)
    sigma_eff(t) = sqrt(sigma_sq + rho * months_since_evidence)

    H   : volatile=15, moderate=36, stable=60 months
    rho : 0.03 / 0.02 / 0.01 per month

    verified_floor    = mu_eff - sigma_eff   (shown to recruiters, used in matching)
    potential_ceiling = mu_eff + sigma_eff   (shown to students)

Pure functions only - no DB access.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

HALF_LIFE_MONTHS = {"volatile": 15.0, "moderate": 36.0, "stable": 60.0}
RHO_PER_MONTH = {"volatile": 0.03, "moderate": 0.02, "stable": 0.01}


def months_since(ts: datetime, now: Optional[datetime] = None) -> float:
    """Months elapsed since ts (30.44-day months)."""
    if now is None:
        now = datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    delta = (now - ts).total_seconds()
    return max(0.0, delta / (30.44 * 24 * 3600))


def mu_eff(mu: float, half_life_class: str, months: float) -> float:
    h = HALF_LIFE_MONTHS.get(half_life_class, 36.0)
    return 0.2 + (mu - 0.2) * (2.0 ** (-months / h))


def sigma_eff(sigma_sq: float, half_life_class: str, months: float) -> float:
    rho = RHO_PER_MONTH.get(half_life_class, 0.02)
    return math.sqrt(max(sigma_sq + rho * months, 0.0))


@dataclass
class EffectiveSkill:
    skill_id: int
    name: str
    domain: str
    half_life_class: str
    mu_stored: float
    sigma_sq_stored: float
    source: str
    last_evidence_at: datetime
    months_stale: float
    mu_effective: float
    sigma_effective: float
    verified_floor: float
    potential_ceiling: float
    faded: bool

    @property
    def is_verified(self) -> bool:
        return self.source in ("assessment", "gauntlet", "course")


def effective_skill(
    skill_id: int,
    name: str,
    domain: str,
    half_life_class: str,
    mu: float,
    sigma_sq: float,
    source: str,
    last_evidence_at: datetime,
    now: Optional[datetime] = None,
) -> EffectiveSkill:
    """Full effective state of one proficiency at time t."""
    m = months_since(last_evidence_at, now)
    me = mu_eff(mu, half_life_class, m)
    se = sigma_eff(sigma_sq, half_life_class, m)
    return EffectiveSkill(
        skill_id=skill_id,
        name=name,
        domain=domain,
        half_life_class=half_life_class,
        mu_stored=mu,
        sigma_sq_stored=sigma_sq,
        source=source,
        last_evidence_at=last_evidence_at,
        months_stale=m,
        mu_effective=me,
        sigma_effective=se,
        verified_floor=max(0.0, me - se),
        potential_ceiling=min(5.0, me + se),
        # visually fade once past half of its half-life class
        # (a 20-month-old 'moderate' skill is already visibly stale on the genome)
        faded=m > 0.5 * HALF_LIFE_MONTHS.get(half_life_class, 36.0),
    )


def freshness_factor(half_life_class: str, months: float) -> float:
    """2^(-months/H) - used by the Placement Readiness Index."""
    h = HALF_LIFE_MONTHS.get(half_life_class, 36.0)
    return 2.0 ** (-months / h)
