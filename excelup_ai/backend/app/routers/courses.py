"""Courses catalog + enrollments + roadmaps."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.db.engine import get_session
from app.models.tables import Course, Enrollment, Roadmap, Skill, User
from app.security import get_current_user
from app.services.events import record_event
from app.services.matching import load_taxonomy
from app.services.notifications import notify
from app.services.proficiency import record_evidence_and_notify

router = APIRouter(tags=["courses"])


@router.get("/courses")
async def list_courses(skill: str | None = None,
                       session: AsyncSession = Depends(get_session)):
    courses = (await session.execute(select(Course).order_by(Course.title))).scalars().all()
    out = []
    for c in courses:
        if skill and skill.lower() not in [s.lower() for s in (c.skills or [])]:
            continue
        out.append({
            "id": c.id, "title": c.title, "provider": c.provider, "url": c.url,
            "skills": c.skills or [], "duration_hours": c.duration_hours,
            "level": c.level,
        })
    return out


@router.post("/courses/{course_id}/enroll")
async def enroll(course_id: int, user: User = Depends(get_current_user),
                 session: AsyncSession = Depends(get_session)):
    course = (await session.execute(select(Course).where(Course.id == course_id))).scalar_one_or_none()
    if course is None:
        raise HTTPException(404, "Course not found")
    existing = (await session.execute(
        select(Enrollment).where(Enrollment.course_id == course_id, Enrollment.user_id == user.id)
    )).scalar_one_or_none()
    if existing:
        return {"id": existing.id, "status": existing.status, "already": True}
    e = Enrollment(user_id=user.id, course_id=course_id, progress=0.0, status="active")
    session.add(e)
    await session.commit()
    await session.refresh(e)
    return {"id": e.id, "status": e.status}


class ProgressBody(BaseModel):
    progress: float  # 0..100


@router.post("/enrollments/{enrollment_id}/progress")
async def set_progress(enrollment_id: int, body: ProgressBody,
                       user: User = Depends(get_current_user),
                       session: AsyncSession = Depends(get_session)):
    e = (await session.execute(select(Enrollment).where(Enrollment.id == enrollment_id))).scalar_one_or_none()
    if e is None or e.user_id != user.id:
        raise HTTPException(404, "Enrollment not found")
    if not (0 <= body.progress <= 100):
        raise HTTPException(400, "progress must be 0..100")
    e.progress = body.progress
    e.status = "completed" if body.progress >= 100 else "active"
    session.add(e)

    completed_now = False
    if e.status == "completed" and e.completed_at is None:
        e.completed_at = datetime.now(timezone.utc)
        completed_now = True
    session.add(e)
    await session.commit()

    if completed_now:
        # course completion is an evidence event → genome recompute (real, live)
        course = (await session.execute(select(Course).where(Course.id == e.course_id))).scalar_one()
        tax = await load_taxonomy(session)
        name_to_id = {v: k for k, v in tax.skill_names.items()}
        for skill_name in (course.skills or []):
            sid = name_to_id.get(skill_name)
            if sid:
                await record_evidence_and_notify(
                    session, user.id, sid, "course",
                    {"course": course.title, "progress": 100})
        await record_event(session, "enrollment", e.id, "completed",
                           {"course": course.title})
    return {"id": e.id, "progress": e.progress, "status": e.status,
            "completed_now": completed_now}


@router.get("/me/enrollments")
async def my_enrollments(user: User = Depends(get_current_user),
                         session: AsyncSession = Depends(get_session)):
    rows = (await session.execute(
        select(Enrollment, Course)
        .join(Course, Course.id == Enrollment.course_id)
        .where(Enrollment.user_id == user.id)
        .order_by(Enrollment.id.desc())
    )).all()
    return [
        {"id": e.id, "course_id": c.id, "title": c.title, "provider": c.provider,
         "url": c.url, "skills": c.skills or [], "progress": e.progress,
         "status": e.status,
         "completed_at": e.completed_at.isoformat() if e.completed_at else None}
        for e, c in rows
    ]


@router.get("/roadmaps")
async def list_roadmaps(session: AsyncSession = Depends(get_session)):
    roads = (await session.execute(select(Roadmap))).scalars().all()
    return [{"id": r.id, "title": r.title, "from_role": r.from_role,
             "to_role": r.to_role, "steps": r.steps or []} for r in roads]
