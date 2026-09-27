"""ExcelUp AI SQLModel tables - longitudinal skilling-outcomes schema on Neon Postgres + pgvector.

Kept from SkillSetu (function unchanged): skills graph, proficiencies, IRT assessment,
opportunities, applications, gauntlets, artifacts, courses, credentials, share tokens,
notifications, events. New: districts, programmes, cohorts, employment episodes,
wage events, follow-up waves/attempts, reason codes, consents.
"""
from datetime import datetime, timezone
from typing import Any, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, Column, Date, DateTime, Float, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------ geography
class District(SQLModel, table=True):
    __tablename__ = "districts"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    division: str = ""
    key_sectors: Any = Field(default=None, sa_column=Column(JSONB))


# ------------------------------------------------------------------- org units
class Provider(SQLModel, table=True):
    """Skilling provider (formerly institution): ITI / polytechnic / private / NGO."""

    __tablename__ = "providers"
    __table_args__ = (
        CheckConstraint("kind IN ('iti','polytechnic','private','ngo')", name="providers_kind_check"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    city: str = ""
    kind: str = "iti"
    district_id: Optional[int] = Field(default=None, foreign_key="districts.id", index=True)


class Company(SQLModel, table=True):
    __tablename__ = "companies"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    industry: str = ""
    city: str = ""
    about: str = ""
    verified: bool = False
    logo_seed: str = ""
    district_id: Optional[int] = Field(default=None, foreign_key="districts.id", index=True)
    sector: str = Field(default="", index=True)


# ---------------------------------------------------------------------- users
class User(SQLModel, table=True):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('trainee','trainer','employer','provider','officer','admin')",
            name="users_role_check",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    role: str = Field(index=True)
    email: str = Field(unique=True, index=True)
    password_hash: str
    name: str
    provider_id: Optional[int] = Field(default=None, foreign_key="providers.id")
    company_id: Optional[int] = Field(default=None, foreign_key="companies.id")
    headline: str = ""
    created_at: datetime = Field(default_factory=_now, sa_column=Column(DateTime(timezone=True)))


class TraineeProfile(SQLModel, table=True):
    __tablename__ = "trainee_profiles"
    __table_args__ = (
        CheckConstraint(
            "social_category IN ('gen','obc','sc','st','nt') OR social_category IS NULL",
            name="trainee_category_check",
        ),
    )

    user_id: int = Field(primary_key=True, foreign_key="users.id")
    degree: str = ""
    year: str = ""
    interests: Any = Field(default=None, sa_column=Column(JSONB))
    target_role: str = ""
    gender: str = ""
    social_category: Optional[str] = None
    age: Optional[int] = None
    disability: bool = False
    education_level: str = ""
    home_district_id: Optional[int] = Field(default=None, foreign_key="districts.id")
    migrated: bool = False
    created_at: datetime = Field(default_factory=_now, sa_column=Column(DateTime(timezone=True)))


class FacultyProfile(SQLModel, table=True):
    """Trainer profile (kept dormant - trainer portal nav removed)."""

    __tablename__ = "faculty_profiles"

    user_id: int = Field(primary_key=True, foreign_key="users.id")
    department: str = ""
    expertise: Any = Field(default=None, sa_column=Column(JSONB))
    publications: Any = Field(default=None, sa_column=Column(JSONB))


# --------------------------------------------------------- programmes & cohorts
class Programme(SQLModel, table=True):
    """A govt-funded skilling course run by a provider."""

    __tablename__ = "programmes"

    id: Optional[int] = Field(default=None, primary_key=True)
    provider_id: int = Field(foreign_key="providers.id", index=True)
    title: str = Field(index=True)
    sector: str = Field(index=True)
    nsqf_level: int = 3
    duration_months: int = 6
    status: str = "active"


class Cohort(SQLModel, table=True):
    __tablename__ = "cohorts"

    id: Optional[int] = Field(default=None, primary_key=True)
    programme_id: int = Field(foreign_key="programmes.id", index=True)
    batch_code: str = Field(index=True)
    start_date: Optional[Any] = Field(default=None, sa_column=Column(Date))
    end_date: Optional[Any] = Field(default=None, sa_column=Column(Date))
    planned_size: int = 0


class CohortEnrollment(SQLModel, table=True):
    __tablename__ = "cohort_enrollments"
    __table_args__ = (
        CheckConstraint("status IN ('enrolled','completed','dropped')", name="cohort_enrollment_status_check"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    cohort_id: int = Field(foreign_key="cohorts.id", index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    enrolled_at: Optional[Any] = Field(default=None, sa_column=Column(Date))
    completed_at: Optional[Any] = Field(default=None, sa_column=Column(Date))
    cert_date: Optional[Any] = Field(default=None, sa_column=Column(Date))
    status: str = "enrolled"


# ---------------------------------------------------------------- skill graph
class Skill(SQLModel, table=True):
    __tablename__ = "skills"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    domain: str = Field(index=True)
    nsqf_level: int = 4
    half_life_class: str = Field(
        sa_column=Column(
            String,
            CheckConstraint("half_life_class IN ('volatile','moderate','stable')", name="skills_hlc_check"),
            index=True,
        )
    )
    synonyms: Any = Field(default=None, sa_column=Column(JSONB))
    embedding: Any = Field(default=None, sa_column=Column(Vector(384)))


class SkillEdge(SQLModel, table=True):
    __tablename__ = "skill_edges"
    __table_args__ = (
        CheckConstraint("type IN ('prerequisite','related')", name="skill_edges_type_check"),
    )

    src_id: int = Field(primary_key=True, foreign_key="skills.id")
    dst_id: int = Field(primary_key=True, foreign_key="skills.id")
    type: str = "prerequisite"
    weight: float = 1.0


# ------------------------------------------------------------- proficiencies
class Proficiency(SQLModel, table=True):
    __tablename__ = "proficiencies"

    user_id: int = Field(primary_key=True, foreign_key="users.id")
    skill_id: int = Field(primary_key=True, foreign_key="skills.id")
    mu: float = 0.0
    sigma_sq: float = 0.10
    last_evidence_at: datetime = Field(default_factory=_now, sa_column=Column(DateTime(timezone=True)))
    source: str = Field(
        sa_column=Column(
            String,
            CheckConstraint(
                "source IN ('assessment','gauntlet','course','declared','vouch')",
                name="proficiencies_source_check",
            ),
        )
    )


class ProficiencyHistory(SQLModel, table=True):
    __tablename__ = "proficiency_history"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    skill_id: int = Field(foreign_key="skills.id", index=True)
    mu: float
    sigma_sq: float
    ts: datetime = Field(default_factory=_now, sa_column=Column(DateTime(timezone=True), index=True))


# --------------------------------------------------------------- assessment
class Item(SQLModel, table=True):
    __tablename__ = "items"
    __table_args__ = (
        CheckConstraint("skill_type IN ('technical','soft','aptitude')", name="items_skill_type_check"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    skill_id: int = Field(foreign_key="skills.id", index=True)
    stem: str
    options: Any = Field(default=None, sa_column=Column(JSONB))
    correct_idx: int
    a: float = 1.2
    b: float = 0.0
    calibrated: bool = False
    skill_type: str = "technical"


class AssessSession(SQLModel, table=True):
    __tablename__ = "assess_sessions"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    skill_id: int = Field(foreign_key="skills.id", index=True)
    theta: float = 0.0
    sem: float = 1.0
    answered: Any = Field(default=None, sa_column=Column(JSONB))
    status: str = "active"
    started_at: datetime = Field(default_factory=_now, sa_column=Column(DateTime(timezone=True)))
    completed_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class Response(SQLModel, table=True):
    __tablename__ = "responses"

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="assess_sessions.id", index=True)
    item_id: int = Field(foreign_key="items.id")
    chosen_idx: int
    correct: bool
    theta_after: float
    sem_after: float
    ts: datetime = Field(default_factory=_now, sa_column=Column(DateTime(timezone=True)))


# ------------------------------------------------------------- opportunities
class Opportunity(SQLModel, table=True):
    __tablename__ = "opportunities"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('job','internship','apprenticeship','live_project','gauntlet',"
            "'faculty_internship','industrial_training','fdp','consultancy','training_program')",
            name="opportunities_kind_check",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    company_id: int = Field(foreign_key="companies.id", index=True)
    kind: str = Field(index=True)
    title: str
    description: str = ""
    location: str = ""
    stipend: str = ""
    duration: str = ""
    rubric: Any = Field(default=None, sa_column=Column(JSONB))
    status: str = "open"
    posted_at: datetime = Field(default_factory=_now, sa_column=Column(DateTime(timezone=True), index=True))


class OppRequirement(SQLModel, table=True):
    __tablename__ = "opp_requirements"

    opp_id: int = Field(primary_key=True, foreign_key="opportunities.id")
    skill_id: int = Field(primary_key=True, foreign_key="skills.id")
    min_level: float = 3.0
    weight: float = 1.0
    essential: bool = False


# -------------------------------------------------------------- applications
class Application(SQLModel, table=True):
    __tablename__ = "applications"
    __table_args__ = (
        CheckConstraint(
            "status IN ('applied','viewed','shortlisted','interviewed','offered','accepted','rejected')",
            name="applications_status_check",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    opp_id: int = Field(foreign_key="opportunities.id", index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    score: float = 0.0
    explanation: Any = Field(default=None, sa_column=Column(JSONB))
    status: str = "applied"
    feedback: Any = Field(default=None, sa_column=Column(JSONB))
    created_at: datetime = Field(default_factory=_now, sa_column=Column(DateTime(timezone=True)))
    updated_at: datetime = Field(default_factory=_now, sa_column=Column(DateTime(timezone=True)))


class GauntletSubmission(SQLModel, table=True):
    __tablename__ = "gauntlet_submissions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('submitted','under_review','approved','rejected')",
            name="gauntlet_status_check",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    opp_id: int = Field(foreign_key="opportunities.id", index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    submission_url: str = ""
    writeup: str = ""
    status: str = "submitted"
    reviewer_id: Optional[int] = Field(default=None, foreign_key="users.id")
    reviewed_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))


# ------------------------------------------------- outcomes: episodes & wages
class EmploymentEpisode(SQLModel, table=True):
    """One employment spell for a trainee - the core Outcome Ledger row."""

    __tablename__ = "employment_episodes"
    __table_args__ = (
        CheckConstraint(
            "employment_type IN ('wage','self_employed','apprenticeship','unemployed','higher_study')",
            name="episode_type_check",
        ),
        CheckConstraint("status IN ('active','ended')", name="episode_status_check"),
        CheckConstraint(
            "source IN ('self_report','employer_validated','platform_placement','officer_verified')",
            name="episode_source_check",
        ),
        CheckConstraint(
            "validation_status IN ('unvalidated','pending','validated','disputed')",
            name="episode_validation_check",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    cohort_id: Optional[int] = Field(default=None, foreign_key="cohorts.id", index=True)
    company_id: Optional[int] = Field(default=None, foreign_key="companies.id", index=True)
    employment_type: str = Field(index=True)
    role_title: str = ""
    district_id: Optional[int] = Field(default=None, foreign_key="districts.id", index=True)
    start_date: Any = Field(sa_column=Column(Date, index=True))
    end_date: Optional[Any] = Field(default=None, sa_column=Column(Date))
    monthly_wage_start: Optional[float] = None
    monthly_wage_current: Optional[float] = None
    status: str = "active"
    source: str = "self_report"
    validation_status: str = "unvalidated"
    validated_by: Optional[int] = Field(default=None, foreign_key="users.id")
    validated_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    created_at: datetime = Field(default_factory=_now, sa_column=Column(DateTime(timezone=True)))
    updated_at: datetime = Field(default_factory=_now, sa_column=Column(DateTime(timezone=True)))


class WageEvent(SQLModel, table=True):
    __tablename__ = "wage_events"

    id: Optional[int] = Field(default=None, primary_key=True)
    episode_id: int = Field(foreign_key="employment_episodes.id", index=True)
    month_index: int = Field(index=True)
    monthly_wage: float
    source: str = "self_report"
    recorded_at: datetime = Field(default_factory=_now, sa_column=Column(DateTime(timezone=True)))


# --------------------------------------------------------- follow-up engine
class FollowupWave(SQLModel, table=True):
    __tablename__ = "followup_waves"
    __table_args__ = (
        CheckConstraint("kind IN ('scheduled','adhoc')", name="wave_kind_check"),
        CheckConstraint("status IN ('pending','active','closed')", name="wave_status_check"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    cohort_id: int = Field(foreign_key="cohorts.id", index=True)
    milestone_months: int = Field(index=True)
    due_on: Any = Field(sa_column=Column(Date, index=True))
    kind: str = "scheduled"
    status: str = "pending"
    created_by: Optional[int] = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(default_factory=_now, sa_column=Column(DateTime(timezone=True)))


class FollowupAttempt(SQLModel, table=True):
    __tablename__ = "followup_attempts"
    __table_args__ = (
        CheckConstraint(
            "method IN ('one_tap','assisted')", name="attempt_method_check"
        ),
        CheckConstraint(
            "response IN ('wage','self_employed','apprenticeship','higher_study',"
            "'unemployed','no_response') OR response IS NULL",
            name="attempt_response_check",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    wave_id: int = Field(foreign_key="followup_waves.id", index=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    method: str = "one_tap"
    response: Optional[str] = None
    episode_id: Optional[int] = Field(default=None, foreign_key="employment_episodes.id")
    reason_codes: Any = Field(default=None, sa_column=Column(JSONB))
    notes: str = ""
    officer_id: Optional[int] = Field(default=None, foreign_key="users.id")
    responded_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    attempted_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class ReasonCode(SQLModel, table=True):
    __tablename__ = "reason_codes"
    __table_args__ = (
        CheckConstraint(
            "category IN ('non_placement','attrition','wage_stagnation')",
            name="reason_category_check",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    category: str = Field(index=True)
    code: str = Field(index=True)
    label: str = ""
    description: str = ""


# ---------------------------------------------------------------- consents
class Consent(SQLModel, table=True):
    __tablename__ = "consents"
    __table_args__ = (
        CheckConstraint(
            "grantee_type IN ('department','provider','employer')",
            name="consent_grantee_check",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    grantee_type: str = Field(index=True)
    grantee_id: Optional[int] = Field(default=None)
    scopes: Any = Field(default=None, sa_column=Column(JSONB))  # subset of outcomes/wage/demographics/skills
    purpose: str = ""
    granted_at: datetime = Field(default_factory=_now, sa_column=Column(DateTime(timezone=True)))
    expires_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    revoked: bool = False
    revoked_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))


# ---------------------------------------------------------------- portfolio
class Artifact(SQLModel, table=True):
    __tablename__ = "artifacts"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('project','certificate','internship','achievement','gauntlet')",
            name="artifacts_kind_check",
        ),
        CheckConstraint(
            "verification IN ('verified','pending','rejected')",
            name="artifacts_verification_check",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    kind: str
    title: str
    payload: Any = Field(default=None, sa_column=Column(JSONB))
    verification: str = "pending"
    created_at: datetime = Field(default_factory=_now, sa_column=Column(DateTime(timezone=True)))


class Course(SQLModel, table=True):
    __tablename__ = "courses"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    provider: str = ""
    url: str = ""
    skills: Any = Field(default=None, sa_column=Column(JSONB))  # list[skill name]
    duration_hours: int = 10
    level: str = "intermediate"


class Enrollment(SQLModel, table=True):
    __tablename__ = "enrollments"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    course_id: int = Field(foreign_key="courses.id", index=True)
    progress: float = 0.0
    status: str = "active"
    completed_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))


class Roadmap(SQLModel, table=True):
    __tablename__ = "roadmaps"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    from_role: str = ""
    to_role: str = ""
    steps: Any = Field(default=None, sa_column=Column(JSONB))


# ------------------------------------------------------- credentials & sharing
class Credential(SQLModel, table=True):
    __tablename__ = "credentials"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    artifact_id: int = Field(foreign_key="artifacts.id", index=True)
    payload: Any = Field(default=None, sa_column=Column(JSONB))
    signature: str = ""
    merkle_root: str = ""
    status: str = "active"
    issued_at: datetime = Field(default_factory=_now, sa_column=Column(DateTime(timezone=True)))


class ShareToken(SQLModel, table=True):
    __tablename__ = "share_tokens"

    token: str = Field(primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    scopes: Any = Field(default=None, sa_column=Column(JSONB))
    expires_at: Optional[datetime] = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    revoked: bool = False


class Notification(SQLModel, table=True):
    __tablename__ = "notifications"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    type: str
    payload: Any = Field(default=None, sa_column=Column(JSONB))
    read: bool = False
    created_at: datetime = Field(default_factory=_now, sa_column=Column(DateTime(timezone=True)))


class Event(SQLModel, table=True):
    """Append-only audit trail: timelines, analytics, and PII_VIEWED records."""

    __tablename__ = "events"

    id: Optional[int] = Field(default=None, primary_key=True)
    aggregate_type: str = Field(index=True)
    aggregate_id: int = Field(index=True)
    event_type: str
    payload: Any = Field(default=None, sa_column=Column(JSONB))
    ts: datetime = Field(default_factory=_now, sa_column=Column(DateTime(timezone=True), index=True))


__all__ = [
    "District", "Provider", "Company", "User", "TraineeProfile", "FacultyProfile",
    "Programme", "Cohort", "CohortEnrollment",
    "Skill", "SkillEdge", "Proficiency", "ProficiencyHistory",
    "Item", "AssessSession", "Response",
    "Opportunity", "OppRequirement", "Application", "GauntletSubmission",
    "EmploymentEpisode", "WageEvent",
    "FollowupWave", "FollowupAttempt", "ReasonCode", "Consent",
    "Artifact", "Course", "Enrollment", "Roadmap",
    "Credential", "ShareToken", "Notification", "Event",
]
