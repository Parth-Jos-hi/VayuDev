from typing import Annotated
from fastapi import APIRouter,Depends
from sqlalchemy.orm import Session
import uuid
from app.services.user_service import update_user_profile
from app.db.session import get_db
from app.schemas.users import UserResponse,UserUpdate
from app.core.security.auth import get_current_db_user
from app.db.models.users import User
router = APIRouter(
    prefix = "/auth",
    tags = ["Authentication"]
)
@router.get("/me",response_model = UserResponse)
def get_my_profile(current_user: Annotated[User,Depends(get_current_db_user),],) -> User:
    return current_user
@router.patch("/me",response_model = UserResponse)
def update_my_profile(profile_data:UserUpdate,
                      current_user:Annotated[User,Depends(get_current_db_user),],
                      db:Annotated[Session,Depends(get_db)],)->User:
    updated_user = update_user_profile(db,current_user,profile_data)
    return updated_user