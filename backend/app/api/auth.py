from typing import Any,Annotated
from fastapi import APIRouter,Depends
from sqlalchemy.orm import Session
import uuid
from app.core.security.auth import get_current_user
from uuid import UUID
from app.services.user_service import get_or_create_user
from app.db.session import get_db
router = APIRouter(
    prefix = "/auth",
    tags = ["Authentication"]
)
@router.get("/me")
def get_my_profile(claims:Annotated[dict[str,Any],Depends(get_current_user)],
                         db:Annotated[Session,Depends(get_db)],)->dict[str,Any]:
    user_id = claims["sub"] 
    user_id_str = uuid.UUID(user_id)
    user = get_or_create_user(db,user_id_str)
    return {
        "user_id": user.id,
        "display_name":user.display_name,
        "role": user.role,
    }