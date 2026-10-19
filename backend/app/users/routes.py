from fastapi import APIRouter

from app.auth.dependencies import CurrentUser
from app.users.schemas import UserResponse


router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
async def current_user(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)
