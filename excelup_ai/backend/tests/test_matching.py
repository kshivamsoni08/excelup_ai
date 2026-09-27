"""Tests for the two-stage matching engine (exact math checks)."""
from app.engines.matching import (
    Explanation,
    Requirement,
    UserSkill,
    build_prereq_index,
    cosine,
    cover,
    match_user_to_opportunity,
    posting_profile_vector,
    prerequisite_distance,
)


def _skills(*pairs):
    return {sid: UserSkill(skill_id=sid, verified_floor=f, potential_ceiling=f + 0.3)
            for sid, f in pairs}


def test_cover_full_when_floor_ge_level():
    u = _skills((1, 4.2))
    assert cover(1, 4.0, u, {}) == 1.0


def test_cover_partial_half_credit():
    # no prereqs: max(0, m/l) * 0.5
    u = _skills((1, 2.0))
    assert abs(cover(1, 4.0, u, {}) - (0.5 * 0.5)) < 1e-9
    assert cover(1, 4.0, {}, {}) == 0.0


def test_cover_via_prerequisite_path():
    # user has TLC (skill 2) at floor 4.0; HPTLC (skill 1) requires level 4.0
    # edge TLC -> HPTLC (2 is prereq of 1), d=1 -> 0.8 * (4.0/4.0) = 0.8
    u = _skills((2, 4.0))
    idx = build_prereq_index([(2, 1)])
    assert abs(cover(1, 4.0, u, idx) - 0.8) < 1e-9


def test_prerequisite_distance_bfs():
    idx = build_prereq_index([(3, 2), (2, 1)])  # 3 -> 2 -> 1
    assert prerequisite_distance(1, {3}, idx) == 2
    assert prerequisite_distance(1, {2}, idx) == 1
    assert prerequisite_distance(1, {1}, idx) == 0
    assert prerequisite_distance(1, {9}, idx) is None


def test_eligibility_gate_on_essential():
    reqs = [Requirement(1, 4.0, 1.0, essential=True)]
    skills = _skills((1, 3.2))  # floor 3.2 < 4.0 - 0.5
    res = match_user_to_opportunity(skills, reqs, {}, {1: "HPTLC"})
    assert res.eligible is False
    # borderline: exactly min-0.5 passes
    skills2 = _skills((1, 3.5))
    res2 = match_user_to_opportunity(skills2, reqs, {}, {1: "HPTLC"})
    assert res2.eligible is True


def test_score_is_weighted_mean():
    reqs = [
        Requirement(1, 4.0, 3.0, essential=False),
        Requirement(2, 2.0, 1.0, essential=False),
    ]
    skills = _skills((1, 4.0), (2, 1.0))  # cover1=1.0, cover2=0.25
    res = match_user_to_opportunity(skills, reqs, {}, {1: "A", 2: "B"})
    expected = (3.0 * 1.0 + 1.0 * 0.25) / 4.0
    assert abs(res.score - expected) < 1e-6


def test_explanation_always_present_with_bridge():
    reqs = [Requirement(1, 4.0, 1.0, essential=False)]
    skills = _skills((1, 2.5))
    courses = {1: ["HPTLC Method Development"]}
    res = match_user_to_opportunity(skills, reqs, {}, {1: "HPTLC"},
                                    courses_by_skill=courses)
    js = res.explanation.to_json()
    assert set(js) == {"matched", "near_miss", "eligible", "score"}
    assert len(js["near_miss"]) == 1
    assert "HPTLC Method Development" in js["near_miss"][0]["bridge"]


def test_retrieval_vector_normalized_and_weighted():
    reqs = [Requirement(1, 3.0, 2.0, False), Requirement(2, 3.0, 1.0, False)]
    emb = {1: [1.0, 0.0], 2: [0.0, 1.0]}
    floors = {1: 3.0, 2: 1.0}
    v = posting_profile_vector(reqs, emb)
    u = __import__("app.engines.matching", fromlist=["user_retrieval_vector"]) \
        .user_retrieval_vector(reqs, floors, emb)
    assert v is not None and u is not None
    # cosine of e1-heavy vs mixed should be high but < 1
    c = cosine(v, u)
    assert 0.6 < c < 1.0


def test_cosine_identical_vectors():
    assert abs(cosine([1, 2, 3], [2, 4, 6]) - 1.0) < 1e-9
    assert abs(cosine([1, 0], [0, 1])) < 1e-9
