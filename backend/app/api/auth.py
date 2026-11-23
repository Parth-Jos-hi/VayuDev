from typing import Any,Annotated
from fastapi import APIRouter,Depends
from app.core.security.auth import get_current_user
from fastapi.security import HTTPAuthorizationCredentials
router = APIRouter(
    prefix = "/auth",
    tags = ["Authentication"]
)
@router.get("/me")
async def get_my_profile(claims:Annotated[dict[str,Any],Depends(get_current_user)]):
    user_id = claims["sub"]
    role = claims["role"]
    return {
        "user_id": user_id,
        "role": role,
    }