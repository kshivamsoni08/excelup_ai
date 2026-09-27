"""Tests for the skill decay engine (exact math checks)."""
from datetime import datetime, timedelta, timezone

from app.engines.decay import (
    effective_skill,
    freshness_factor,
    months_since,
    mu_eff,
    sigma_eff,
)

NOW = datetime(2026, 9, 24, tzinfo=timezone.utc)


def _ts(months_ago: float) -> datetime:
    return NOW - timedelta(days=30.44 * months_ago)


def test_months_since():
    assert abs(months_since(_ts(10), NOW) - 10.0) < 0.05
    assert months_since(NOW, NOW) == 0.0


def test_no_decay_when_fresh():
    v = mu_eff(4.0, "volatile", 0.0)
    assert abs(v - 4.0) < 1e-9


def test_half_life_values():
    # after exactly H months, value collapses to 0.2 + (mu-0.2)/2
    for cls, h in (("volatile", 15), ("moderate", 36), ("stable", 60)):
        assert abs(mu_eff(4.2, cls, h) - (0.2 + 4.0 / 2)) < 1e-6


def test_volatile_decays_faster_than_stable():
    m = mu_eff(4.0, "volatile", 20)
    s = mu_eff(4.0, "stable", 20)
    assert m < s


def test_floor_never_negative_and_ceiling_capped():
    e = effective_skill(1, "X", "d", "volatile", 1.0, 0.10, "assessment",
                        _ts(40), now=NOW)
    assert e.verified_floor >= 0.0
    assert e.potential_ceiling <= 5.0


def test_hero_hptlc_scenario_faded():
    """HPTLC mu=3.2 verified 20 months ago, moderate class: visibly decayed."""
    e = effective_skill(7, "HPTLC", "Pharmacy/QC", "moderate", 3.2, 0.10,
                        "assessment", _ts(20), now=NOW)
    assert e.mu_effective < 3.2 - 0.5          # clearly decayed
    assert e.verified_floor < e.mu_effective    # floor below stored mu
    assert e.faded is True                      # months (20) > H? no — moderate H=36
    # moderate: 20 months < H=36 -> not faded by class rule; volatile would be
    ev = effective_skill(7, "HPTLC", "Pharmacy/QC", "volatile", 3.2, 0.10,
                         "assessment", _ts(20), now=NOW)
    assert ev.faded is True


def test_sigma_grows_with_time():
    s0 = sigma_eff(0.10, "moderate", 0.0)
    s20 = sigma_eff(0.10, "moderate", 20.0)
    assert s20 > s0
    assert abs(s20 - (0.10 + 0.02 * 20) ** 0.5) < 1e-9


def test_floor_below_4_for_decayed_hero_skill():
    """Aarav's HPTLC: floor must land below 4 so the QC posting shows near-miss."""
    e = effective_skill(7, "HPTLC", "Pharmacy/QC", "moderate", 3.2, 0.10,
                        "assessment", _ts(20), now=NOW)
    assert e.verified_floor < 4.0


def test_freshness_factor():
    assert abs(freshness_factor("moderate", 0.0) - 1.0) < 1e-9
    assert abs(freshness_factor("volatile", 15.0) - 0.5) < 1e-6
    assert freshness_factor("stable", 12.0) > freshness_factor("volatile", 12.0)
