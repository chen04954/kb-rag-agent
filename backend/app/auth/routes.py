import jwt
from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.auth.dependencies import (
    BearerCredentials,
    CurrentUser,
    DatabaseSession,
    unauthorized,
)
from app.auth.schemas import AccessToken, Credentials, TokenPair
from app.auth.utils import create_token, decode_token, hash_password, verify_password
from app.db.models import User
from app.users.schemas import UserResponse


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def signup(payload: Credentials, session: DatabaseSession) -> UserResponse:
    existing = await session.scalar(select(User).where(User.email == payload.email))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )
    user = User(
        email=str(payload.email).lower(),
        password_hash=hash_password(payload.password),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return UserResponse.model_validate(user)


@router.post("/login", response_model=TokenPair)
async def login(payload: Credentials, session: DatabaseSession) -> TokenPair:
    user = await session.scalar(
        select(User).where(User.email == str(payload.email).lower())
    )
    if user is None or not verify_password(payload.password, user.password_hash):
        raise unauthorized()
    return TokenPair(
        access_token=create_token(user.id, "access"),
        refresh_token=create_token(user.id, "refresh"),
    )


@router.get("/refresh-token", response_model=AccessToken)
async def refresh_token(
    credentials: BearerCredentials,
    session: DatabaseSession,
) -> AccessToken:
    if credentials is None:
        raise unauthorized()
    try:
        user_id = decode_token(credentials.credentials, "refresh")
    except (jwt.PyJWTError, ValueError, KeyError):
        raise unauthorized() from None
    user = await session.scalar(select(User).where(User.id == user_id))
    if user is None:
        raise unauthorized()
    return AccessToken(access_token=create_token(user.id, "access"))


@router.get("/logout")
async def logout(_: CurrentUser) -> dict[str, str]:
    return {"status": "logged_out"}
