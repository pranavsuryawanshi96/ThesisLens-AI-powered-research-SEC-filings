from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel

from app.auth.dependencies import CurrentUserDep

router = APIRouter()


class MeResponse(BaseModel):
    id: UUID
    email: str | None


@router.get("/me")
async def me(user: CurrentUserDep) -> MeResponse:
    return MeResponse(id=user.id, email=user.email)
