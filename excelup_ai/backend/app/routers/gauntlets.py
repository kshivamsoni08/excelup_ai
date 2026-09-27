"""Industry Skill Challenges (gauntlets): student browse + submit; company
review queue. Approval mints a verified artifact + signed credential and
recomputes the student's proficiency (genome visibly jumps, sigma tightens)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.db.engine import get_session
from app.models.tables import (
    Application,
    Artifact,
    Company,
    GauntletSubmission,
    Opportunity,
    Proficiency,
    Skill,
    User,
)
from app.security import get_current_user, require_roles
from app.services.credentials import batch_merkle, credential_payload, mint_credential
from app.services.events import record_event
from app.services.matching import load_taxonomy, requirements_for, user_skill_map
from app.services.notifications import notify
from app.services.proficiency import record_evidence_and_notify

router = APIRouter(tags=["gauntlets"])


class SubmitBody(BaseModel):
    submission_url: str
    writeup: str


@router.get("/gauntlets")
async def browse(session: AsyncSession = Depends(get_session),
                 user: User = Depends(get_current_user)):
    rows = (await session.execute(
        select(Opportunity, Company)
        .join(Company, Company.id == Opportunity.company_id)
        .where(Opportunity.kind == "gauntlet", Opportunity.status == "open")
        .order_by(Opportunity.posted_at.desc())
    )).all()
    tax = await load_taxonomy(session)
    req_map = await requirements_for(session, [o.id for o, _c in rows])
    out = []
    for opp, comp in rows:
        out.append({
            "id": opp.id, "title": opp.title, "description": opp.description,
            "company": comp.name, "rubric": opp.rubric, "duration": opp.duration,
            "stipend": opp.stipend,
            "skills": [
                {"skill": tax.skill_names.get(r.skill_id, f"skill {r.skill_id}"),
                 "min_level": r.min_level}
                for r in req_map.get(opp.id, [])
            ],
        })
    return out


@router.post("/gauntlets/{opp_id}/submit")
async def submit(opp_id: int, body: SubmitBody,
                 user: User = Depends(require_roles("trainee")),
                 session: AsyncSession = Depends(get_session)):
    opp = (await session.execute(
        select(Opportunity).where(Opportunity.id == opp_id, Opportunity.kind == "gauntlet")
    )).scalar_one_or_none()
    if opp is None:
        raise HTTPException(404, "Gauntlet not found")
    if not body.submission_url.strip() or not body.writeup.strip():
        raise HTTPException(400, "submission_url and writeup are required")

    sub = GauntletSubmission(opp_id=opp_id, user_id=user.id,
                             submission_url=body.submission_url.strip(),
                             writeup=body.writeup.strip(), status="submitted")
    session.add(sub)
    await session.flush()
    await record_event(session, "gauntlet_submission", sub.id, "submitted",
                       {"opp_id": opp_id})
    await session.commit()

    # notify the company's users
    staff = (await session.execute(
        select(User).where(User.company_id == opp.company_id, User.role == "employer")
    )).scalars().all()
    for s in staff:
        await notify(session, s.id, "gauntlet_submission", {
            "submission_id": sub.id, "opp_title": opp.title, "trainee": "a candidate",
        })
    return {"id": sub.id, "status": sub.status}


@router.get("/me/gauntlet-submissions")
async def my_submissions(user: User = Depends(get_current_user),
                         session: AsyncSession = Depends(get_session)):
    subs = (await session.execute(
        select(GauntletSubmission).where(GauntletSubmission.user_id == user.id)
        .order_by(GauntletSubmission.id.desc())
    )).scalars().all()
    out = []
    for s in subs:
        opp = (await session.execute(select(Opportunity).where(Opportunity.id == s.opp_id))).scalar_one_or_none()
        out.append({"id": s.id, "opp_id": s.opp_id, "title": opp.title if opp else None,
                    "status": s.status, "submission_url": s.submission_url,
                    "writeup": s.writeup,
                    "reviewed_at": s.reviewed_at.isoformat() if s.reviewed_at else None})
    return out


# ------------------------------------------------------------ company side
@router.get("/company/gauntlet-submissions")
async def review_queue(user: User = Depends(require_roles("employer", "admin")),
                       session: AsyncSession = Depends(get_session)):
    q = (select(GauntletSubmission, Opportunity, Company)
         .join(Opportunity, Opportunity.id == GauntletSubmission.opp_id)
         .join(Company, Company.id == Opportunity.company_id)
         .where(GauntletSubmission.status.in_(["submitted", "under_review", "approved", "rejected"])))
    if user.company_id:
        q = q.where(Opportunity.company_id == user.company_id)
    rows = (await session.execute(q.order_by(GauntletSubmission.id.desc()))).all()
    out = []
    for sub, opp, comp in rows:
        out.append({
            "id": sub.id, "opp_id": sub.opp_id, "gauntlet_title": opp.title,
            "company": comp.name, "status": sub.status,
            "submission_url": sub.submission_url, "writeup": sub.writeup,
            "candidate_ref": f"CANDIDATE-{sub.id:04d}",
            "candidate_user_id": sub.user_id,
            "reviewed_at": sub.reviewed_at.isoformat() if sub.reviewed_at else None,
        })
    return out


class ReviewBody(BaseModel):
    decision: str  # "approve" | "reject"
    notes: str = ""


@router.post("/company/gauntlet-submissions/{sub_id}/review")
async def review(sub_id: int, body: ReviewBody,
                 user: User = Depends(require_roles("employer", "admin")),
                 session: AsyncSession = Depends(get_session)):
    if body.decision not in ("approve", "reject"):
        raise HTTPException(400, "decision must be approve|reject")
    sub = (await session.execute(
        select(GauntletSubmission).where(GauntletSubmission.id == sub_id)
    )).scalar_one_or_none()
    if sub is None:
        raise HTTPException(404, "Submission not found")
    opp = (await session.execute(select(Opportunity).where(Opportunity.id == sub.opp_id))).scalar_one_or_none()
    if user.company_id and opp.company_id != user.company_id:
        raise HTTPException(403, "Not your company's gauntlet")

    sub.status = "approved" if body.decision == "approve" else "rejected"
    sub.reviewer_id = user.id
    sub.reviewed_at = datetime.now(timezone.utc)
    session.add(sub)
    await session.flush()

    credential_id = None
    if body.decision == "approve":
        tax = await load_taxonomy(session)
        reqs = (await requirements_for(session, [opp.id])).get(opp.id, [])
        top_skill = tax.skill_names.get(reqs[0].skill_id) if reqs else None
        level = reqs[0].min_level if reqs else 4.0

        artifact = Artifact(
            user_id=sub.user_id, kind="gauntlet",
            title=f"{opp.title} - approved by {await comp_name_async(session, opp.company_id)}",
            payload={
                "gauntlet_id": opp.id, "skills": [top_skill] if top_skill else [],
                "level": level, "submission_url": sub.submission_url,
                "reviewer": user.name, "notes": body.notes,
            },
            verification="verified",
        )
        session.add(artifact)
        await session.flush()

        company_name = await comp_name_async(session, opp.company_id)
        trainee = (await session.execute(select(User).where(User.id == sub.user_id))).scalar_one()
        payload = credential_payload(trainee.name, company_name,
                                     top_skill or opp.title, level, opp.title,
                                     datetime.now(timezone.utc))
        cred = await mint_credential(session, sub.user_id, artifact.id, payload)
        credential_id = cred.id
        # batch ALL active credentials into the Merkle tree so the public
        # /verify page can show a valid proof immediately
        await batch_merkle(session)

        # proficiency recompute for each required skill (genome jumps live)
        for r in reqs:
            await record_evidence_and_notify(
                session, sub.user_id, r.skill_id, "gauntlet",
                {"gauntlet": opp.title, "level": level},
            )

    await record_event(session, "gauntlet_submission", sub.id, sub.status,
                       {"by": user.name, "notes": body.notes})
    await notify(session, sub.user_id, f"gauntlet_{sub.status}", {
        "submission_id": sub.id, "gauntlet": opp.title,
        "credential_id": credential_id,
    })
    await session.commit()
    return {"id": sub.id, "status": sub.status, "credential_id": credential_id}


async def comp_name_async(session: AsyncSession, company_id: int) -> str:
    comp = (await session.execute(select(Company).where(Company.id == company_id))).scalar_one_or_none()
    return comp.name if comp else "a company"
