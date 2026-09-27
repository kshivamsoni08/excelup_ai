"""ExcelUp AI FastAPI application.

- CORS from FRONTEND_ORIGINS
- Neon warm-up SELECT 1 on startup (autosuspend cold-start)
- APScheduler: nightly skill-decay job + 4-minute keep-warm heartbeat
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlmodel import SQLModel

from app.config import settings
from app.db.engine import get_engine, get_sessionmaker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("skillsetu")


async def _warm_up():
    """Warm-up SELECT 1 - also materializes the schema on first boot."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(SQLModel.metadata.create_all)
    async with get_sessionmaker()() as session:
        await session.execute(text("SELECT 1"))
    logger.info("DB warm-up complete (pgvector ready, schema current)")


async def _nightly_decay_job():
    """Re-materialize decayed proficiencies; emit decay_alert notifications.

    For every proficiency whose verified_floor decayed since its last
    re-materialization, refresh last_evidence bookkeeping is intentionally NOT
    touched (decay is computed on read); instead we alert: when the floor of a
    skill drops below the min_level of any of the user's top-match postings,
    a decay_alert notification is created (deduped per day).
    """
    from sqlmodel import select

    from app.engines.decay import effective_skill
    from app.models.tables import (
        Notification, Opportunity, OppRequirement, Proficiency, Skill, User,
    )
    from app.services.matching import load_taxonomy

    maker = get_sessionmaker()
    async with maker() as session:
        skills = {s.id: s for s in (await session.execute(select(Skill))).scalars().all()}
        reqs = (await session.execute(
            select(OppRequirement, Opportunity)
            .join(Opportunity, Opportunity.id == OppRequirement.opp_id)
            .where(Opportunity.status == "open")
        )).all()
        req_by_skill: dict[int, list[dict]] = {}
        for r, opp in reqs:
            req_by_skill.setdefault(r.skill_id, []).append(
                {"opp_id": opp.id, "title": opp.title, "min_level": r.min_level})

        profs = (await session.execute(select(Proficiency))).scalars().all()
        now = datetime.now(timezone.utc)
        alerts = 0
        for p in profs:
            s = skills.get(p.skill_id)
            if s is None:
                continue
            eff = effective_skill(p.skill_id, s.name, s.domain, s.half_life_class,
                                  p.mu, p.sigma_sq, p.source, p.last_evidence_at, now=now)
            if eff.verified_floor >= eff.mu_stored - 0.3:
                continue  # not meaningfully decayed
            for req in req_by_skill.get(p.skill_id, []):
                if eff.verified_floor < req["min_level"] - 0.5:
                    # dedupe: one alert per (user, skill) per day
                    today = now.date().isoformat()
                    dup = (await session.execute(
                        select(Notification).where(
                            Notification.user_id == p.user_id,
                            Notification.type == "decay_alert",
                            Notification.created_at >= now.replace(hour=0, minute=0,
                                                                   second=0, microsecond=0))
                    )).scalars().all()
                    if any((n.payload or {}).get("skill") == s.name for n in dup):
                        continue
                    session.add(Notification(
                        user_id=p.user_id, type="decay_alert",
                        payload={"skill": s.name,
                                 "floor": round(eff.verified_floor, 2),
                                 "required_by": req["title"],
                                 "min_level": req["min_level"],
                                 "date": today}))
                    alerts += 1
                    break
        await session.commit()
        logger.info("Nightly decay job: %d decay_alert notifications", alerts)


async def _keep_warm():
    """SELECT 1 every 4 minutes so Neon never sleeps during a demo."""
    try:
        async with get_sessionmaker()() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:
        logger.warning("Keep-warm heartbeat failed: %s", exc)


async def _daily_followup_job():
    """Auto-generate scheduled follow-up waves at completion + 3/6/12/24 months."""
    try:
        from app.services.followups import ensure_scheduled_waves

        maker = get_sessionmaker()
        async with maker() as session:
            created = await ensure_scheduled_waves(session)
            logger.info("Daily follow-up job: %d scheduled waves created", created)
    except Exception as exc:
        logger.warning("Daily follow-up job failed: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    if not settings.database_url:
        raise RuntimeError(
            "BLOCKED: DATABASE_URL missing. Create .env with your Neon pooled string."
        )
    try:
        await _warm_up()
    except Exception as exc:
        logger.error("DB warm-up failed: %s - the API will still boot; check .env/DATABASE_URL", exc)

    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    scheduler = AsyncIOScheduler()
    scheduler.add_job(_keep_warm, "interval", minutes=4, id="keep_warm")
    scheduler.add_job(_nightly_decay_job, "cron", hour=2, minute=30, id="nightly_decay")
    scheduler.add_job(_daily_followup_job, "cron", hour=1, minute=0, id="daily_followups")
    # also run the maintenance passes once at boot so demo data is fresh immediately
    scheduler.add_job(_nightly_decay_job, "date",
                      run_date=datetime.now(timezone.utc), id="boot_decay")
    scheduler.add_job(_daily_followup_job, "date",
                      run_date=datetime.now(timezone.utc), id="boot_followups")
    scheduler.start()
    logger.info("APScheduler started (keep-warm 4min, nightly decay, daily follow-up waves)")
    yield
    # shutdown
    scheduler.shutdown(wait=False)


app = FastAPI(
    title="ExcelUp AI API",
    description="Skilling outcomes, measured honestly. - Longitudinal skilling-outcomes "
                "and impact-measurement platform (SIH PS 26135, Government of Maharashtra, "
                "Dept of Skills, Employment, Entrepreneurship and Innovation)",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------- routers
from app.routers.admin import router as admin_router  # noqa: E402
from app.routers.applications import router as applications_router  # noqa: E402
from app.routers.assessment import router as assessment_router  # noqa: E402
from app.routers.auth import router as auth_router  # noqa: E402
from app.routers.company import router as company_router  # noqa: E402
from app.routers.courses import router as courses_router  # noqa: E402
from app.routers.employer import router as employer_router  # noqa: E402
from app.routers.faculty import router as faculty_router  # noqa: E402
from app.routers.gauntlets import router as gauntlets_router  # noqa: E402
from app.routers.institution import router as provider_router  # noqa: E402
from app.routers.matching import router as matching_router  # noqa: E402
from app.routers.notifications import router as notifications_router  # noqa: E402
from app.routers.officer import router as officer_router  # noqa: E402
from app.routers.opportunities import router as opportunities_router  # noqa: E402
from app.routers.portfolio import router as portfolio_router  # noqa: E402
from app.routers.public import router as public_router  # noqa: E402
from app.routers.resume import router as resume_router  # noqa: E402
from app.routers.skills import router as skills_router  # noqa: E402
from app.routers.trainee_outcomes import router as trainee_outcomes_router  # noqa: E402

app.include_router(auth_router)
app.include_router(skills_router)
app.include_router(assessment_router)
app.include_router(resume_router)
app.include_router(matching_router)
app.include_router(opportunities_router)
app.include_router(applications_router)
app.include_router(gauntlets_router)
app.include_router(company_router)
app.include_router(employer_router)
app.include_router(portfolio_router)
app.include_router(provider_router)
app.include_router(faculty_router)
app.include_router(courses_router)
app.include_router(notifications_router)
app.include_router(public_router)
app.include_router(admin_router)
app.include_router(officer_router)
app.include_router(trainee_outcomes_router)


@app.get("/")
async def root():
    return {"name": "ExcelUp AI API", "status": "ok",
            "docs": "/docs", "tagline": "Skilling outcomes, measured honestly."}


@app.get("/health")
async def health():
    try:
        async with get_sessionmaker()() as session:
            await session.execute(text("SELECT 1"))
        return {"ok": True, "db": "up"}
    except Exception as exc:
        return {"ok": False, "db": str(exc)}
