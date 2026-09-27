"""Auth + profile routes: register, login, /me, onboarding wizard."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.db.engine import get_session
from app.models.tables import Company, FacultyProfile, Provider, TraineeProfile, User
from app.security import create_access_token, get_current_user, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

ROLE_VALUES = ("trainee", "trainer", "employer", "provider", "officer", "admin")


class RegisterBody(BaseModel):
    email: str
    password: str
    name: str
    role: str = "trainee"
    provider_id: Optional[int] = None
    company_id: Optional[int] = None


class LoginBody(BaseModel):
    email: str
    password: str


class OnboardingBody(BaseModel):
    degree: Optional[str] = None
    year: Optional[str] = None
    interests: Optional[list[str]] = None
    target_role: Optional[str] = None
    headline: Optional[str] = None
    home_district_id: Optional[int] = None
    gender: Optional[str] = None
    social_category: Optional[str] = None
    age: Optional[int] = None
    education_level: Optional[str] = None
    disability: Optional[bool] = None
    migrated: Optional[bool] = None


@router.post("/register")
async def register(body: RegisterBody, session: AsyncSession = Depends(get_session)):
    if body.role not in ROLE_VALUES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"role must be one of {ROLE_VALUES}")
    if len(body.password) < 8:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Password must be at least 8 characters")
    exists = (await session.execute(select(User).where(User.email == body.email.lower()))).scalar_one_or_none()
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    user = User(
        role=body.role, email=body.email.lower(),
        password_hash=hash_password(body.password), name=body.name,
        provider_id=body.provider_id, company_id=body.company_id,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    if body.role == "trainee":
        session.add(TraineeProfile(user_id=user.id))
    elif body.role == "trainer":
        session.add(FacultyProfile(user_id=user.id))
    await session.commit()
    token = create_access_token(user.id, user.role, user.email)
    return {"token": token, "user": _user_json(user)}


@router.post("/login")
async def login(body: LoginBody, session: AsyncSession = Depends(get_session)):
    user = (await session.execute(select(User).where(User.email == body.email.lower()))).scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    token = create_access_token(user.id, user.role, user.email)
    return {"token": token, "user": _user_json(user)}


@router.get("/me")
async def me(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    out = _user_json(user)
    if user.role == "trainee":
        tp = (await session.execute(select(TraineeProfile).where(TraineeProfile.user_id == user.id))).scalar_one_or_none()
        out["profile"] = {
            "degree": tp.degree if tp else "", "year": tp.year if tp else "",
            "interests": (tp.interests if tp else []) or [],
            "target_role": tp.target_role if tp else "",
            "gender": tp.gender if tp else "",
            "social_category": tp.social_category if tp else None,
            "age": tp.age if tp else None,
            "education_level": tp.education_level if tp else "",
            "disability": tp.disability if tp else False,
            "migrated": tp.migrated if tp else False,
            "home_district_id": tp.home_district_id if tp else None,
        }
    elif user.role == "trainer":
        fp = (await session.execute(select(FacultyProfile).where(FacultyProfile.user_id == user.id))).scalar_one_or_none()
        out["profile"] = {
            "department": fp.department if fp else "",
            "expertise": (fp.expertise if fp else []) or [],
            "publications": (fp.publications if fp else []) or [],
        }
    if user.provider_id:
        prov = (await session.execute(select(Provider).where(Provider.id == user.provider_id))).scalar_one_or_none()
        out["provider"] = {"name": prov.name, "kind": prov.kind, "city": prov.city} if prov else None
    if user.company_id:
        comp = (await session.execute(select(Company).where(Company.id == user.company_id))).scalar_one_or_none()
        out["company"] = {"name": comp.name, "verified": comp.verified} if comp else None
    return out


@router.post("/me/onboarding")
async def onboarding(body: OnboardingBody, user: User = Depends(get_current_user),
                     session: AsyncSession = Depends(get_session)):
    if body.headline is not None:
        user.headline = body.headline
        session.add(user)
    if user.role == "trainee":
        tp = (await session.execute(select(TraineeProfile).where(TraineeProfile.user_id == user.id))).scalar_one_or_none()
        if tp is None:
            tp = TraineeProfile(user_id=user.id)
        for field in ("degree", "year", "target_role", "gender", "social_category",
                      "age", "education_level", "home_district_id"):
            val = getattr(body, field)
            if val is not None:
                setattr(tp, field, val)
        if body.interests is not None:
            tp.interests = body.interests
        if body.disability is not None:
            tp.disability = body.disability
        if body.migrated is not None:
            tp.migrated = body.migrated
        session.add(tp)
    await session.commit()
    return {"ok": True}


def _user_json(user: User) -> dict:
    return {
        "id": user.id, "role": user.role, "email": user.email, "name": user.name,
        "provider_id": user.provider_id, "company_id": user.company_id,
        "headline": user.headline,
    }
