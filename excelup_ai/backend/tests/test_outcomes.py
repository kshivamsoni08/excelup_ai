"""Tests for the Outcome Analytics engine (pure math - no DB)."""
from datetime import date

from app.engines.outcomes import (
    Episode,
    cell,
    followup_response_rate,
    oqi,
    placement_at_month,
    placement_day_rate,
    placement_decay_curve,
    programme_flags,
    retention_at,
    suppressed,
    validation_rate,
    wage_curve,
    wage_growth_12,
    _add_months,
)

D = date


def _completions(n: int, day: D = D(2025, 6, 1)) -> dict[int, D]:
    return {i: day for i in range(1, n + 1)}


# ------------------------------------------------------------- placement
def test_placement_day_rate_30_day_window():
    completions = _completions(10)
    eps = [Episode(user_id=i, employment_type="wage", start=D(2025, 6, 15))
           for i in range(1, 8)]  # 7 placed within 30 days
    eps.append(Episode(user_id=8, employment_type="wage", start=D(2025, 7, 15)))  # too late
    eps.append(Episode(user_id=9, employment_type="unemployed", start=D(2025, 6, 5)))  # not positive
    assert placement_day_rate(completions, eps) == 0.7


def test_placement_at_month_requires_active_episode():
    completions = _completions(2, D(2025, 1, 1))
    # user 1: ended after 2 months - not active at month 3; user 2: still active
    eps = [
        Episode(user_id=1, employment_type="wage", start=D(2025, 1, 10), end=D(2025, 3, 5)),
        Episode(user_id=2, employment_type="self_employed", start=D(2025, 1, 20)),
    ]
    assert placement_at_month(completions, eps, 3) == 0.5
    assert placement_at_month(completions, eps, 1) == 1.0


def test_placement_decay_curve_monotonic():
    completions = _completions(4, D(2025, 1, 1))
    eps = [
        Episode(user_id=1, employment_type="wage", start=D(2025, 1, 5)),
        Episode(user_id=2, employment_type="wage", start=D(2025, 1, 6), end=D(2025, 4, 1)),
        Episode(user_id=3, employment_type="wage", start=D(2025, 1, 7), end=D(2025, 2, 1)),
        # user 4 never placed
    ]
    curve = placement_decay_curve(completions, eps, [0, 3, 6, 12])
    assert curve[0]["rate"] == 0.75
    assert curve[1]["rate"] == 0.5
    assert curve[2]["rate"] == 0.25
    assert curve[3]["rate"] == 0.25


# ------------------------------------------------------------- retention
def test_retention_counts_null_end_as_retained():
    eps = [
        Episode(user_id=1, employment_type="wage", start=D(2025, 1, 1)),                      # active
        Episode(user_id=2, employment_type="wage", start=D(2025, 1, 1), end=D(2025, 7, 1)),   # >= 6mo
        Episode(user_id=3, employment_type="wage", start=D(2025, 1, 1), end=D(2025, 4, 1)),   # < 6mo
    ]
    assert retention_at(eps, 6, D(2025, 12, 1)) == 2 / 3


def test_retention_excludes_recent_episodes():
    eps = [Episode(user_id=1, employment_type="wage", start=D(2025, 11, 1))]
    assert retention_at(eps, 6, D(2025, 12, 1)) == 0.0  # started < 6 months ago


# ----------------------------------------------------------------- wages
def test_wage_growth_12_consent_scoped():
    eps = [
        Episode(user_id=1, employment_type="wage", start=D(2025, 1, 1),
                wage_start=14000, wages={0: 14000, 6: 16000, 12: 19000}),
        Episode(user_id=2, employment_type="wage", start=D(2025, 1, 1),
                wage_start=10000, wages={0: 10000, 12: 10000}),
        Episode(user_id=3, employment_type="wage", start=D(2025, 1, 1),
                wage_start=12000, wages={12: 20000}),  # NO consent - excluded
    ]
    res = wage_growth_12(eps, consented_user_ids={1, 2})
    assert res["n"] == 2
    assert abs(res["growth"] - 0.2040) < 0.01  # (median 14.5k / median 12k) - 1


def test_wage_growth_none_without_consent():
    eps = [Episode(user_id=1, employment_type="wage", start=D(2025, 1, 1), wage_start=10000)]
    assert wage_growth_12(eps, set())["growth"] is None


def test_wage_curve_medians():
    eps = [
        Episode(user_id=1, employment_type="wage", start=D(2025, 1, 1), wage_start=10000,
                wages={0: 10000, 12: 15000}),
        Episode(user_id=2, employment_type="wage", start=D(2025, 1, 1), wage_start=14000,
                wages={0: 14000, 12: 19000}),
    ]
    curve = wage_curve(eps, {1, 2}, max_month=12)
    assert curve[0]["median_wage"] == 12000 and curve[0]["n"] == 2
    assert curve[12]["median_wage"] == 17000 and curve[12]["n"] == 2
    assert curve[6]["n"] == 0 and curve[6]["median_wage"] is None


# ------------------------------------------------------------------ rates
def test_followup_response_rate():
    attempts = [{"responded": True, "response": "wage"},
                {"responded": True, "response": "no_response"},
                {"responded": False, "response": None},
                {"responded": True, "response": "self_employed"}]
    # F = real outcome responses / issued; 'no_response' and silence don't count
    assert followup_response_rate(attempts) == 0.5
    assert followup_response_rate(attempts[:1]) == 1.0


def test_validation_rate_wage_only():
    class FakeEp:
        def __init__(self, t, v):
            self.employment_type, self.validation_status = t, v

    eps = [FakeEp("wage", "validated"), FakeEp("wage", "pending"),
           FakeEp("wage", "validated"), FakeEp("self_employed", "unvalidated")]
    assert validation_rate(eps) == 2 / 3


# ------------------------------------------------------------------- OQI
def test_oqi_pune_solar_scripted_reveal():
    """Seed target: Solar PV @ ITI Pune -> OQI ~= 87."""
    res = oqi(placement_12=0.80, retention_12=0.82, wage_growth=0.31,
              validation_rate_v=0.85, followup_rate_f=0.82)
    assert 84 <= res["score"] <= 90  # ~87


def test_oqi_nashik_ev_scripted_reveal():
    """Seed target: EV Assembly @ ITI Nashik -> OQI ~= 52 (vanity metrics)."""
    res = oqi(placement_12=0.78, retention_12=0.48, wage_growth=0.04,
              validation_rate_v=0.60, followup_rate_f=0.75)
    assert 48 <= res["score"] <= 56  # ~52


def test_oqi_full_and_zero_marks():
    full = oqi(1.0, 1.0, 0.30, 1.0, 1.0)
    assert full["score"] == 100.0
    zero = oqi(0.0, 0.0, None, 0.0, 0.0)
    assert zero["score"] == 0.0
    assert zero["components"]["wage_component"] == 0.0


def test_oqi_wage_growth_clamped():
    # 60% growth -> clamped to full marks
    over = oqi(0, 0, 0.60, 0, 0)
    assert over["components"]["wage_component"] == 1.0


# ----------------------------------------------------------------- flags
def test_vanity_metric_flag():
    flags = programme_flags(placement_0=0.92, placement_12=0.60,
                            completions=50, sector_median_completions=50,
                            sector_postings_yoy=0.1)
    assert "vanity_metric" in flags


def test_oversupplied_and_obsolete_flags():
    # textile: 3x sector median completions, placement_12=0.40, postings -25% YoY
    flags = programme_flags(placement_0=0.55, placement_12=0.40,
                            completions=300, sector_median_completions=100,
                            sector_postings_yoy=-0.25)
    assert "oversupplied" in flags
    assert "obsolete" in flags


def test_no_flags_for_healthy_programme():
    flags = programme_flags(placement_0=0.85, placement_12=0.80,
                            completions=60, sector_median_completions=100,
                            sector_postings_yoy=0.05)
    assert flags == []


# ------------------------------------------------------------ k-anonymity
def test_k_anonymity_suppression():
    assert suppressed(4)
    assert not suppressed(5)
    c = cell(0.75, 3)
    assert c["suppressed"] and c["value"] is None and "n<5" in c["label"]
    ok = cell(0.75, 12)
    assert not ok["suppressed"] and ok["value"] == 0.75 and ok["n"] == 12


# --------------------------------------------------------------- helpers
def test_add_months_handles_year_rollover_and_clamping():
    assert _add_months(D(2025, 1, 31), 1) == D(2025, 2, 28)
    assert _add_months(D(2025, 11, 15), 3) == D(2026, 2, 15)
    assert _add_months(D(2025, 6, 1), 12) == D(2026, 6, 1)
