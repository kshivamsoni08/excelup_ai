"""Adaptive assessment routes (§5.1): start, answer, status.

Live difficulty indicator: every served item carries its b-value and a label so
the UI can show "serving questions at your frontier" with a theta-vs-b bar.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.db.engine import get_session
from app.engines.irt import (
    Item as EngineItem,
    SessionState,
    difficulty_label,
    process_answer,
    select_item,
    theta_to_level,
)
from app.models.tables import AssessSession, Item, Response, Skill, User
from app.security import get_current_user
from app.services.matching import load_taxonomy
from app.services.proficiency import record_evidence_and_notify

router = APIRouter(prefix="/assess", tags=["assessment"])


async def _pool_for_skill(session: AsyncSession, skill_id: int) -> list[Item]:
    return (await session.execute(
        select(Item).where(Item.skill_id == skill_id)
    )).scalars().all()


def _engine_items(rows: list[Item]) -> dict[int, EngineItem]:
    return {r.id: EngineItem(id=r.id, a=r.a, b=r.b, skill_type=r.skill_type) for r in rows}


def _session_json(sess: AssessSession, skill: Skill | None, served: Item | None) -> dict:
    return {
        "session_id": sess.id,
        "skill_id": sess.skill_id,
        "skill": skill.name if skill else None,
        "theta": round(sess.theta, 3),
        "sem": round(sess.sem, 3),
        "answered_count": len(sess.answered or []),
        "status": sess.status,
        "level_estimate": round(theta_to_level(sess.theta), 2),
        "served": None if served is None else {
            "item_id": served.id,
            "stem": served.stem,
            "options": served.options,
            "difficulty_b": served.b,
            "difficulty_label": difficulty_label(served.b),
            "skill_type": served.skill_type,
        },
    }


@router.post("/start")
async def start(skill_id: int, user: User = Depends(get_current_user),
                session: AsyncSession = Depends(get_session)):
    skill = (await session.execute(select(Skill).where(Skill.id == skill_id))).scalar_one_or_none()
    if skill is None:
        raise HTTPException(404, "Skill not found")
    pool = await _pool_for_skill(session, skill_id)
    if not pool:
        raise HTTPException(400, f"No item bank for skill '{skill.name}' yet")

    # resume an active session if one exists
    active = (await session.execute(
        select(AssessSession).where(AssessSession.user_id == user.id,
                                    AssessSession.skill_id == skill_id,
                                    AssessSession.status == "active")
        .order_by(AssessSession.started_at.desc()).limit(1)
    )).scalar_one_or_none()

    if active:
        served = await _pick_next(session, active, pool)
        sess = active
    else:
        state = SessionState()
        engine_items = _engine_items(pool)
        first = select_item(state, engine_items.values())
        if first is None:
            raise HTTPException(400, "Item bank exhausted")
        sess = AssessSession(
            user_id=user.id, skill_id=skill_id, theta=state.theta, sem=state.sem,
            answered=[], status="active",
            started_at=datetime.now(timezone.utc),
        )
        sess.answered = {"served": [first.id], "answers": []}
        session.add(sess)
        await session.commit()
        await session.refresh(sess)
        served = (await session.execute(select(Item).where(Item.id == first.id))).scalar_one()

    return _session_json(sess, skill, served)


async def _pick_next(session: AsyncSession, sess: AssessSession, pool: list[Item]) -> Optional[Item]:
    """Next item for an active session, honoring served history."""
    data = sess.answered or {}
    served_ids = list(data.get("served", []))
    engine_items = _engine_items(pool)
    state = SessionState(theta=sess.theta, sem=sess.sem)
    state.served = served_ids
    nxt = select_item(state, engine_items.values())
    if nxt is None:
        return None
    if nxt.id not in served_ids:
        served_ids.append(nxt.id)
        sess.answered = {**data, "served": served_ids}
        session.add(sess)
        await session.commit()
    return (await session.execute(select(Item).where(Item.id == nxt.id))).scalar_one()


class AnswerBody(BaseModel):
    item_id: int
    choice: int


@router.post("/{sid}/answer")
async def answer(sid: int, body: AnswerBody, user: User = Depends(get_current_user),
                 session: AsyncSession = Depends(get_session)):
    sess = (await session.execute(
        select(AssessSession).where(AssessSession.id == sid, AssessSession.user_id == user.id)
    )).scalar_one_or_none()
    if sess is None:
        raise HTTPException(404, "Session not found")
    if sess.status != "active":
        raise HTTPException(400, "Session already completed")

    item = (await session.execute(select(Item).where(Item.id == body.item_id))).scalar_one()
    pool = await _pool_for_skill(session, sess.skill_id)
    engine_items = _engine_items(pool)

    data = sess.answered or {"served": [], "answers": []}
    state = SessionState(theta=sess.theta, sem=sess.sem)
    state.served = list(data.get("served", []))

    state = process_answer(state, engine_items[item.id], body.choice, item.correct_idx,
                           engine_items, engine_items.values())

    correct = body.choice == item.correct_idx
    session.add(Response(
        session_id=sess.id, item_id=item.id, chosen_idx=body.choice, correct=correct,
        theta_after=round(state.theta, 4), sem_after=round(state.sem, 4),
        ts=datetime.now(timezone.utc),
    ))

    answers = list(data.get("answers", []))
    answers.append({"item_id": item.id, "chosen_idx": body.choice, "correct": correct})
    sess.theta = state.theta
    sess.sem = state.sem
    sess.answered = {"served": state.served, "answers": answers}

    completed = state.status == "completed"
    if completed:
        sess.status = "completed"
        sess.completed_at = datetime.now(timezone.utc)
    session.add(sess)
    await session.commit()
    await session.refresh(sess)

    if completed:
        # §5.1: write proficiency mu=level, sigma_sq=0.10, source='assessment'
        await record_evidence_and_notify(
            session, user.id, sess.skill_id, "assessment",
            {"theta": round(state.theta, 3), "level": round(theta_to_level(state.theta), 2)},
        )

    skill = (await session.execute(select(Skill).where(Skill.id == sess.skill_id))).scalar_one()
    served = None
    if not completed:
        served = await _pick_next(session, sess, pool)
    return _session_json(sess, skill, served)


@router.get("/{sid}")
async def status(sid: int, user: User = Depends(get_current_user),
                 session: AsyncSession = Depends(get_session)):
    sess = (await session.execute(
        select(AssessSession).where(AssessSession.id == sid, AssessSession.user_id == user.id)
    )).scalar_one_or_none()
    if sess is None:
        raise HTTPException(404, "Session not found")
    skill = (await session.execute(select(Skill).where(Skill.id == sess.skill_id))).scalar_one_or_none()
    served = None
    if sess.status == "active":
        pool = await _pool_for_skill(session, sess.skill_id)
        served = await _pick_next(session, sess, pool)
    return _session_json(sess, skill, served)
