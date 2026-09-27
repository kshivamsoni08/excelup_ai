"""Matching engine - two stages.

STAGE 1 (retrieval): user vector v_u = normalize(Σ (mu_eff - sigma_eff) * weight * skill_embedding)
over a posting's requirements; cosine similarity via pgvector shortlists candidates.

STAGE 2 (directed coverage scoring) for user u vs opportunity o:
  - Eligibility gate: every essential requirement s must satisfy
    verified_floor(u,s) >= min_level(s) - 0.5, else the match is flagged not_eligible.
  - cover(u, s, l):
        m = verified_floor(u,s)
        if m >= l:                       1.0
        elif prerequisite path exists (skill_edges BFS, distance d) from a skill p
             the user has with verified_floor(p) >= l:
                                          0.8^d * (verified_floor(p) / l)
        else:                            max(0, m/l) * 0.5
  - score = Σ(weight_k * cover_k) / Σ(weight_k)  → percentage.
  - ALWAYS produces an explanation jsonb:
        { matched, near_miss (with bridge suggestion), eligible, score }

Pure functions only - no DB access.
"""
from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Optional


# --------------------------------------------------------------------- inputs
@dataclass
class Requirement:
    skill_id: int
    min_level: float
    weight: float
    essential: bool


@dataclass
class UserSkill:
    """Effective (decayed) state of one skill the user holds."""

    skill_id: int
    verified_floor: float
    potential_ceiling: float
    source: str = "assessment"


@dataclass
class Explanation:
    matched: list[dict] = field(default_factory=list)
    near_miss: list[dict] = field(default_factory=list)
    eligible: bool = True
    score: float = 0.0
    not_eligible_skills: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        return {
            "matched": self.matched,
            "near_miss": self.near_miss,
            "eligible": self.eligible,
            "score": self.score,
        }


@dataclass
class MatchResult:
    score: float                 # 0..1
    eligible: bool
    explanation: Explanation


# ------------------------------------------------------- stage 1: retrieval
def posting_profile_vector(
    requirements: list[Requirement],
    embeddings: dict[int, list[float]],
) -> Optional[list[float]]:
    """Normalized Σ weight * skill_embedding - precomputed at seed time too."""
    dim = len(next(iter(embeddings.values()))) if embeddings else 0
    if dim == 0:
        return None
    acc = [0.0] * dim
    for r in requirements:
        emb = embeddings.get(r.skill_id)
        if emb is None:
            continue
        for i, v in enumerate(emb):
            acc[i] += r.weight * v
    return _normalize(acc)


def user_retrieval_vector(
    requirements: list[Requirement],
    user_floors: dict[int, float],
    embeddings: dict[int, list[float]],
) -> Optional[list[float]]:
    """v_u = normalize(Σ (mu_eff - sigma_eff) * weight * skill_embedding)."""
    dim = len(next(iter(embeddings.values()))) if embeddings else 0
    if dim == 0:
        return None
    acc = [0.0] * dim
    for r in requirements:
        floor = user_floors.get(r.skill_id)
        emb = embeddings.get(r.skill_id)
        if floor is None or emb is None:
            continue
        for i, v in enumerate(emb):
            acc[i] += floor * r.weight * v
    return _normalize(acc)


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _normalize(v: list[float]) -> Optional[list[float]]:
    n = math.sqrt(sum(x * x for x in v))
    if n == 0:
        return None
    return [x / n for x in v]


# ------------------------------------------- stage 2: directed coverage score
def build_prereq_index(edges: list[tuple[int, int]]) -> dict[int, set[int]]:
    """Index: target skill -> set of direct prerequisite skills.

    An edge (src, dst) means src is a prerequisite of dst (e.g. TLC → HPTLC).
    """
    idx: dict[int, set[int]] = defaultdict(set)
    for src, dst in edges:
        idx[dst].add(src)
    return idx


def prerequisite_distance(
    target_skill: int,
    user_skill_ids: set[int],
    prereq_index: dict[int, set[int]],
    max_depth: int = 4,
) -> Optional[int]:
    """BFS distance d from some user-held skill p to the target via prerequisite
    edges. Returns smallest d, or None if no path within max_depth."""
    if target_skill in user_skill_ids:
        return 0
    visited = {target_skill}
    frontier = deque([(target_skill, 0)])
    while frontier:
        node, d = frontier.popleft()
        if d >= max_depth:
            continue
        for prereq in prereq_index.get(node, ()):  # move backwards: prerequisites
            if prereq in user_skill_ids:
                return d + 1
            if prereq not in visited:
                visited.add(prereq)
                frontier.append((prereq, d + 1))
    return None


def cover(
    skill_id: int,
    min_level: float,
    user_skills: dict[int, UserSkill],
    prereq_index: dict[int, set[int]],
) -> float:
    """Directed coverage of one requirement, exactly as specified."""
    us = user_skills.get(skill_id)
    m = us.verified_floor if us else 0.0
    if m >= min_level:
        return 1.0
    # prerequisite path: any user skill p with floor >= min_level reaching s
    user_ids = {sid for sid, s in user_skills.items() if s.verified_floor >= min_level}
    d = prerequisite_distance(skill_id, user_ids, prereq_index)
    if d is not None and d > 0:
        best_p = max(
            (user_skills[p].verified_floor for p in user_ids),
            default=0.0,
        )
        return min(1.0, (0.8 ** d) * (best_p / min_level))
    return max(0.0, m / min_level) * 0.5


def match_user_to_opportunity(
    user_skills: dict[int, UserSkill],           # skill_id -> effective state
    requirements: list[Requirement],
    prereq_index: dict[int, set[int]],
    skill_names: dict[int, str],
    courses_by_skill: Optional[dict[int, list[str]]] = None,
) -> MatchResult:
    """Score one user against one opportunity and build the explanation."""
    courses_by_skill = courses_by_skill or {}

    total_weight = sum(r.weight for r in requirements) or 1.0
    weighted = 0.0
    eligible = True
    exp = Explanation()

    for r in requirements:
        name = skill_names.get(r.skill_id, f"skill#{r.skill_id}")
        us = user_skills.get(r.skill_id)
        user_level = round(us.verified_floor, 2) if us else 0.0

        c = cover(r.skill_id, r.min_level, user_skills, prereq_index)
        weighted += r.weight * c

        # eligibility gate on essential requirements
        if r.essential and (user_level < r.min_level - 0.5):
            eligible = False
            exp.not_eligible_skills.append(name)

        entry_base = {
            "skill": name,
            "user_level": user_level,
            "required": r.min_level,
            "weight": r.weight,
            "essential": r.essential,
        }
        if c >= 0.999:
            exp.matched.append({**entry_base, "credit": round(c, 3)})
        else:
            bridge = _bridge_text(r.skill_id, courses_by_skill)
            exp.near_miss.append(
                {**entry_base, "credit": round(c, 3), "bridge": bridge}
            )

    score = weighted / total_weight
    exp.eligible = eligible
    exp.score = round(score, 4)
    return MatchResult(score=score, eligible=eligible, explanation=exp)


def _bridge_text(skill_id: int, courses_by_skill: dict[int, list[str]]) -> str:
    courses = courses_by_skill.get(skill_id) or []
    if courses:
        return f"Bridge this gap: take '{courses[0]}' (see My Learning Path)."
    return (
        "Bridge this gap: pick a course from My Learning Path or prove it in an "
        "Industry Skill Challenge."
    )


def score_percentage(result: MatchResult) -> float:
    return round(result.score * 100.0, 1)
