"""Platform admin stats."""
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.db.engine import get_session
from app.models.tables import (
    Application, AssessSession, CohortEnrollment, Company, Consent,
    Credential, EmploymentEpisode, Enrollment, FollowupAttempt, WageEvent,
    Opportunity, Proficiency, User,
)
from app.security import require_roles
from app.engines.llm import provider_name
from app.engines.embeddings import embedder_status

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats")
async def stats(session: AsyncSession = Depends(get_session),
                _user=Depends(require_roles("admin"))):
    async def count(model):
        return (await session.execute(select(func.count()).select_from(model))).scalar()

    return {
        "users": await count(User),
        "companies": await count(Company),
        "opportunities": await count(Opportunity),
        "applications": await count(Application),
        "assess_sessions": await count(AssessSession),
        "proficiencies": await count(Proficiency),
        "enrollments": await count(Enrollment),
        "credentials": await count(Credential),
        "outcomes": {
            "cohort_enrollments": await count(CohortEnrollment),
            "employment_episodes": await count(EmploymentEpisode),
            "wage_events": await count(WageEvent),
            "followup_attempts": await count(FollowupAttempt),
            "consents": await count(Consent),
        },
        "engine_status": {
            "llm": provider_name(),
            "embeddings": embedder_status(),
        },
    }
