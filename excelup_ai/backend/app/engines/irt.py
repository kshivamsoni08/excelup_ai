"""IRT adaptive assessment engine (2-parameter logistic model).

EXACT MATH
----------
P(correct) = 1 / (1 + exp(-a * (theta - b)))

- theta scale: -3..+3, prior theta ~ N(0,1).
- Estimation: EAP over a 61-point quadrature grid [-3, +3], step 0.1.
- Item selection: maximize Fisher information I(theta) = a^2 * P * (1-P),
  excluding already-served items.
- Stopping: posterior SEM < 0.30 OR 10 items answered.
- 0-5 level mapping: level = (theta + 3) / 1.2.

Pure functions only - no DB access - so this module is fully pytest-able
before any database wiring exists.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

# ----------------------------------------------------------------- constants
THETA_MIN = -3.0
THETA_MAX = 3.0
QUADRATURE_STEP = 0.1
SEM_STOP = 0.30
MAX_ITEMS = 10
PRIOR_MEAN = 0.0
PRIOR_SD = 1.0

# 61-point grid [-3, +3], step 0.1
GRID = [round(THETA_MIN + i * QUADRATURE_STEP, 2) for i in range(61)]


def p_correct(theta: float, a: float, b: float) -> float:
    """2PL probability of a correct response."""
    z = a * (theta - b)
    # numerically stable logistic
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def fisher_information(theta: float, a: float, b: float) -> float:
    """I(theta) = a^2 * P * (1-P)."""
    p = p_correct(theta, a, b)
    return a * a * p * (1.0 - p)


@dataclass
class Item:
    id: int
    a: float
    b: float
    skill_type: str = "technical"


@dataclass
class SessionState:
    """Mutable running state of one adaptive session."""

    theta: float = PRIOR_MEAN
    sem: float = PRIOR_SD
    served: list[int] = field(default_factory=list)          # item ids served
    answered: list[dict] = field(default_factory=list)        # {item_id, correct}
    status: str = "active"                                    # active|completed


def eap_estimate(
    answers: Sequence[tuple[int, bool]],
    items_by_id: dict[int, Item],
) -> tuple[float, float]:
    """Expected A Posteriori theta estimate over the 61-point grid.

    Returns (theta, sem) where sem is the posterior standard deviation.
    """
    # grid densities, starting from the prior
    log_post: list[float] = []
    for t in GRID:
        lp = -0.5 * ((t - PRIOR_MEAN) / PRIOR_SD) ** 2
        for item_id, correct in answers:
            it = items_by_id.get(item_id)
            if it is None:
                continue
            p = min(max(p_correct(t, it.a, it.b), 1e-9), 1 - 1e-9)
            lp += math.log(p if correct else 1.0 - p)
        log_post.append(lp)

    m = max(log_post)
    weights = [math.exp(lp - m) for lp in log_post]
    total = sum(weights)
    mean = sum(t * w for t, w in zip(GRID, weights)) / total
    var = sum((t - mean) ** 2 * w for t, w in zip(GRID, weights)) / total
    return mean, math.sqrt(max(var, 0.0))


def select_item(
    state: SessionState,
    pool: Iterable[Item],
    theta: Optional[float] = None,
) -> Optional[Item]:
    """Pick the unserved item maximizing Fisher information at current theta."""
    t = state.theta if theta is None else theta
    best: Optional[Item] = None
    best_info = -1.0
    for it in pool:
        if it.id in state.served:
            continue
        info = fisher_information(t, it.a, it.b)
        if info > best_info:
            best_info = info
            best = it
    return best


def should_stop(state: SessionState) -> bool:
    """SEM < 0.30 OR 10 items answered."""
    if len(state.answered) >= MAX_ITEMS:
        return True
    return state.sem < SEM_STOP and len(state.answered) > 0


def process_answer(
    state: SessionState,
    item: Item,
    chosen_idx: int,
    correct_idx: int,
    items_by_id: dict[int, Item],
    pool: Iterable[Item],
) -> SessionState:
    """Record one response, re-estimate theta via EAP, serve next item / stop.

    Mutates and returns `state` (kept in assess_sessions.answered / theta / sem).
    """
    correct = chosen_idx == correct_idx
    if item.id not in state.served:
        state.served.append(item.id)
    state.answered.append({"item_id": item.id, "chosen_idx": chosen_idx, "correct": correct})

    answers = [(a["item_id"], a["correct"]) for a in state.answered]
    state.theta, state.sem = eap_estimate(answers, items_by_id)

    if should_stop(state):
        state.status = "completed"
    else:
        nxt = select_item(state, pool)
        if nxt is None:
            state.status = "completed"  # pool exhausted
    return state


def theta_to_level(theta: float) -> float:
    """Map theta (-3..+3) to a 0-5 skill level."""
    return (theta + 3.0) / 1.2


def level_to_theta(level: float) -> float:
    return level * 1.2 - 3.0


def difficulty_label(b: float) -> str:
    """Human-facing difficulty tag for the live 'frontier' indicator."""
    if b < -1.0:
        return "easy"
    if b < 0.5:
        return "moderate"
    if b < 1.5:
        return "hard"
    return "very hard"
