"""Hand-rolled JWT auth + bcrypt hashing + role-based access control.

Roles: trainee, trainer, employer, provider, officer, admin.
The role claim lives inside the JWT; FastAPI dependencies enforce RBAC per route.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.config import settings
from app.db.engine import get_session
from app.models.tables import User

ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24 * 7

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

ROLES = ("trainee", "trainer", "employer", "provider", "officer", "admin")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_access_token(user_id: int, role: str, email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    payload = {
        "sub": str(user_id),
        "role": role,
        "email": email,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc


async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )
    payload = decode_token(token)
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        )
    user = (
        await session.execute(select(User).where(User.id == int(user_id)))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
        )
    return user


def require_roles(*roles: str):
    """Dependency factory enforcing RBAC: require_roles('employer', 'admin')."""

    async def _checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role in {list(roles)}",
            )
        return user

    return _checker


# Convenience single-role guards (new vocabulary)
require_trainee = require_roles("trainee", "admin")
require_employer = require_roles("employer", "admin")
require_officer = require_roles("officer", "admin")
require_provider = require_roles("provider", "admin")
require_admin = require_roles("admin")

# Legacy aliases kept so dormant modules (trainer portal, etc.) still import.
require_student = require_trainee
require_faculty = require_roles("trainer", "admin")
require_industry = require_employer
require_institution = require_provider
