"""Tests for the IRT adaptive assessment engine (exact math checks)."""
import math

from app.engines.irt import (
    GRID,
    Item,
    SessionState,
    difficulty_label,
    eap_estimate,
    fisher_information,
    p_correct,
    process_answer,
    select_item,
    should_stop,
    theta_to_level,
)


def test_grid_is_61_points():
    assert len(GRID) == 61
    assert GRID[0] == -3.0 and GRID[-1] == 3.0
    assert abs(GRID[1] - GRID[0] - 0.1) < 1e-9


def test_p_correct_2pl():
    # theta == b -> P = 0.5 regardless of a
    assert abs(p_correct(1.0, 1.2, 1.0) - 0.5) < 1e-9
    # P increases with theta above b, decreases below b
    assert p_correct(2.0, 1.0, 0.0) > 0.5
    assert p_correct(-2.0, 1.0, 0.0) < 0.5
    # known value: theta=1, a=1, b=0 -> 1/(1+e^-1) ~ 0.731
    assert abs(p_correct(1.0, 1.0, 0.0) - 1 / (1 + math.exp(-1))) < 1e-9


def test_fisher_information_peaks_at_b():
    a, b = 1.5, 0.4
    info_at_b = fisher_information(b, a, b)
    info_off = fisher_information(b + 1.0, a, b)
    assert info_at_b > info_off
    # I = a^2 * P * (1-P) = a^2/4 at theta == b
    assert abs(info_at_b - a * a / 4) < 1e-9


def test_eap_recovers_theta_for_strong_ability():
    items = [Item(id=i, a=1.4, b=-1.5 + i * 0.5) for i in range(1, 9)]  # b: -1.5..2.0
    by_id = {it.id: it for it in items}
    # strong ability: answers all items with b <= 1.0 correctly
    answers = [(it.id, it.b <= 1.0) for it in items]
    theta, sem = eap_estimate(answers, by_id)
    assert theta > 0.9
    assert sem < 0.6  # more certain than the N(0,1) prior


def test_eap_prior_when_no_answers():
    theta, sem = eap_estimate([], {})
    assert abs(theta) < 0.2  # centered at prior mean 0
    # discrete prior over the truncated grid [-3, 3] is slightly narrower
    # than the continuous N(0,1)
    assert 0.95 < sem < 1.0


def test_item_selection_maximizes_information_and_excludes_served():
    pool = [
        Item(id=1, a=1.0, b=-1.0),
        Item(id=2, a=1.5, b=0.5),
        Item(id=3, a=1.2, b=1.5),
    ]
    state = SessionState(theta=0.5)
    # at theta=0.5 the most informative item is the one with b closest to 0.5
    it = select_item(state, pool)
    assert it.id == 2
    # after serving it, it must not be served again
    state.served.append(2)
    it2 = select_item(state, pool)
    assert it2.id in (1, 3)


def test_stopping_rules():
    state = SessionState(theta=0.0, sem=0.9, answered=[{"item_id": 1, "correct": True}])
    assert not should_stop(state)
    state.sem = 0.29
    assert should_stop(state)  # SEM < 0.30
    state.sem = 0.5
    state.answered = [{"item_id": i, "correct": True} for i in range(10)]
    assert should_stop(state)  # 10 items answered


def test_process_answer_adapts_downward_after_wrong():
    pool = [Item(id=i, a=1.4, b=-1.0 + (i - 1) * 0.4) for i in range(1, 9)]
    by_id = {it.id: it for it in pool}
    state = SessionState(theta=1.0, sem=0.6)
    first = select_item(state, pool)
    state = process_answer(state, first, chosen_idx=99, correct_idx=0,
                           items_by_id=by_id, pool=pool)
    # after a wrong answer the next served item should be easier (lower b)
    nxt = select_item(state, pool)
    assert nxt.b < first.b


def test_level_mapping():
    assert abs(theta_to_level(0.0) - 2.5) < 1e-9
    assert abs(theta_to_level(3.0) - 5.0) < 1e-9
    assert abs(theta_to_level(-3.0)) < 1e-9


def test_difficulty_labels():
    assert difficulty_label(-1.5) == "easy"
    assert difficulty_label(0.0) == "moderate"
    assert difficulty_label(1.0) == "hard"
    assert difficulty_label(1.8) == "very hard"
