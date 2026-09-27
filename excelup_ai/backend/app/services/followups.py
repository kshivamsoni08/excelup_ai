"""Follow-up engine (§5.3): scheduled waves, ad-hoc waves, one-tap responses,
assisted (officer) attempts.

- Scheduled waves auto-generate at completion + 3/6/12/24 months (daily job).
- Ad-hoc waves fire instantly: every eligible trainee gets a notification.
- One-tap response: creates/updates the employment episode + wage event +
  followup attempt in one transaction (~20 seconds of trainee effort).
- Non-response after 14 days surfaces in the officer assisted workbench.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.tables import (
    CohortEnrollment,
    EmploymentEpisode,
    FollowupAttempt,
    FollowupWave,
    Notification,
    User,
    WageEvent,
)
from app.services.events import record_event

MILESTONES = (3, 6, 12, 24)
WAGE_BANDS = [(0, 10000), (10000, 15000), (15000, 20000), (20000, 30000), (30000, None)]
BAND_MIDPOINTS = {0: 6000, 1: 12500, 2: 17500, 3: 25000, 4: 40000}
RESPONSE_TYPES = ("wage", "self_employed", "apprenticeship", "higher_study", "unemployed")


async def ensure_scheduled_waves(session: AsyncSession, as_of: date | None = None) -> int:
    """Daily job: create a wave for every (cohort, milestone) whose due date
    (completion + milestone months) has arrived. Idempotent."""
    as_of = as_of or date.today()
    created = 0
    completions = (await session.execute(
        select(CohortEnrollment)
        .where(CohortEnrollment.status == "completed",
               CohortEnrollment.completed_at.is_not(None))
    )).scalars().all()
    existing = {(w.cohort_id, w.milestone_months, w.kind)
                for w in (await session.execute(select(FollowupWave))).scalars().all()}
    seen_pairs: set[tuple[int, int]] = set()
    for ce in completions:
        for m in MILESTONES:
            if (ce.cohort_id, m, "scheduled") in existing:
                continue
            pair = (ce.cohort_id, m)
            if pair in seen_pairs:
                continue
            due = _add_months(ce.completed_at, m)
            if due <= as_of:
                seen_pairs.add(pair)
                session.add(FollowupWave(
                    cohort_id=ce.cohort_id, milestone_months=m, due_on=due,
                    kind="scheduled", status="active"))
                created += 1
    if created:
        await session.commit()
    return created


async def create_adhoc_wave(session: AsyncSession, cohort_id: int,
                            officer_id: int | None) -> FollowupWave:
    """Officer-triggered wave: active immediately, all eligible trainees get
    an in-app follow-up notification instantly."""
    enrollments = (await session.execute(
        select(CohortEnrollment)
        .where(CohortEnrollment.cohort_id == cohort_id,
               CohortEnrollment.status == "completed")
    )).scalars().all()
    wave = FollowupWave(cohort_id=cohort_id, milestone_months=0,
                        due_on=date.today(), kind="adhoc", status="active",
                        created_by=officer_id)
    session.add(wave)
    await session.flush()

    notified = 0
    for ce in enrollments:
        # one open attempt per trainee per wave
        session.add(FollowupAttempt(
            wave_id=wave.id, user_id=ce.user_id, method="one_tap",
            attempted_at=datetime.now(timezone.utc)))
        session.add(Notification(
            user_id=ce.user_id, type="followup_request",
            payload={"wave_id": wave.id, "cohort_id": cohort_id,
                     "kind": "adhoc"}))
        notified += 1
    await record_event(session, "followup_wave", wave.id, "created",
                       {"cohort_id": cohort_id, "by": officer_id,
                        "notified": notified, "kind": "adhoc"})
    await session.commit()
    return wave


def wage_from_band(band_idx: int) -> float:
    return BAND_MIDPOINTS.get(int(band_idx), 12500)


async def record_one_tap_response(
    session: AsyncSession, wave_id: int, user_id: int,
    response: str, band_idx: int | None = None,
    role_title: str = "", notes: str = "",
) -> dict:
    """The ~20-second trainee interaction. Creates/updates the episode,
    appends a wage event, closes the attempt."""
    if response not in RESPONSE_TYPES:
        raise ValueError(f"response must be one of {RESPONSE_TYPES}")
    wave = (await session.execute(
        select(FollowupWave).where(FollowupWave.id == wave_id)
    )).scalar_one_or_none()
    if wave is None:
        raise ValueError("wave not found")

    attempt = (await session.execute(
        select(FollowupAttempt)
        .where(FollowupAttempt.wave_id == wave_id,
               FollowupAttempt.user_id == user_id)
        .order_by(FollowupAttempt.id.desc())
    )).scalars().first()
    if attempt is None:
        attempt = FollowupAttempt(wave_id=wave_id, user_id=user_id,
                                  method="one_tap",
                                  attempted_at=datetime.now(timezone.utc))

    episode_id = None
    if response == "unemployed":
        episode = EmploymentEpisode(
            user_id=user_id, cohort_id=wave.cohort_id,
            employment_type="unemployed", role_title="",
            start_date=date.today(), status="active",
            source="self_report", validation_status="unvalidated",
        )
        session.add(episode)
        await session.flush()
        episode_id = episode.id
    elif response in ("wage", "self_employed", "apprenticeship"):
        # update the latest active episode of the same type, else create one
        episode = (await session.execute(
            select(EmploymentEpisode)
            .where(EmploymentEpisode.user_id == user_id,
                   EmploymentEpisode.employment_type == response,
                   EmploymentEpisode.status == "active")
            .order_by(EmploymentEpisode.start_date.desc())
        )).scalars().first()
        wage = wage_from_band(band_idx) if band_idx is not None and response == "wage" else None
        if episode is None:
            episode = EmploymentEpisode(
                user_id=user_id, cohort_id=wave.cohort_id,
                employment_type=response, role_title=role_title,
                start_date=date.today(), status="active",
                source="self_report",
                monthly_wage_start=wage, monthly_wage_current=wage,
                validation_status="unvalidated",
            )
            session.add(episode)
            await session.flush()
        elif wage is not None:
            episode.monthly_wage_current = wage
            session.add(episode)
        episode_id = episode.id
        if wage is not None:
            session.add(WageEvent(
                episode_id=episode.id,
                month_index=_months_since(episode.start_date, date.today()),
                monthly_wage=wage, source="self_report"))

    attempt.response = response
    attempt.episode_id = episode_id
    attempt.responded_at = datetime.now(timezone.utc)
    attempt.notes = notes
    session.add(attempt)
    await record_event(session, "followup_attempt", attempt.id, "responded",
                       {"wave_id": wave_id, "user_id": user_id,
                        "response": response, "method": "one_tap"})
    await session.commit()
    return {"attempt_id": attempt.id, "episode_id": episode_id,
            "response": response}


async def non_responders(session: AsyncSession, days: int = 14) -> list[dict]:
    """Attempts issued >= `days` ago with no response - the officer workbench."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (await session.execute(
        select(FollowupAttempt, User)
        .join(User, User.id == FollowupAttempt.user_id)
        .where(FollowupAttempt.responded_at.is_(None),
               FollowupAttempt.attempted_at <= cutoff)
        .order_by(FollowupAttempt.attempted_at)
    )).all()
    out = []
    seen: set[int] = set()
    for attempt, user in rows:
        if attempt.user_id in seen:
            continue  # one row per trainee (latest pending attempt)
        seen.add(attempt.user_id)
        out.append({
            "attempt_id": attempt.id, "wave_id": attempt.wave_id,
            "user_id": user.id, "name": user.name, "email": user.email,
            "attempted_at": attempt.attempted_at.isoformat(),
            "days_waiting": (datetime.now(timezone.utc) - attempt.attempted_at).days,
        })
    return out


async def wave_stats(session: AsyncSession, wave_id: int) -> dict:
    attempts = (await session.execute(
        select(FollowupAttempt).where(FollowupAttempt.wave_id == wave_id)
    )).scalars().all()
    issued = len(attempts)
    responded = sum(1 for a in attempts if a.responded_at is not None
                    and a.response not in (None, "no_response"))
    return {"wave_id": wave_id, "issued": issued, "responded": responded,
            "response_rate": round(responded / issued, 4) if issued else 0.0}


def _add_months(d: date, months: int) -> date:
    mi = (d.month - 1) + months
    year, month = d.year + mi // 12, mi % 12 + 1
    day = d.day
    while day > 28:
        try:
            return date(year, month, day)
        except ValueError:
            day -= 1
    return date(year, month, day)


def _months_since(start: date, as_of: date) -> int:
    months = (as_of.year - start.year) * 12 + (as_of.month - start.month)
    return max(0, months)
