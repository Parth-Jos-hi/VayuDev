from uuid import UUID
from fastapi import HTTPException, status
from app.db.models.users import User
from app.core.security.auth import get_or_create_user
from fastapi import Depends
from collections.abc import Callable
from typing import Annotated,Any
from app.core.security.auth import get_current_db_user
def check_role(
    user_role: str,
    allowed_roles: set[str],
) -> None:
    if user_role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this action",
        )
def check_venue_ownership(
    user_id: UUID,
    venue_id: UUID,
    approved_owner_id: UUID | None,
) -> None:
    if approved_owner_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This venue has no approved owner",
        )
    if user_id != approved_owner_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to manage this venue",
        )
def require_roles(allowed_roles:set[str],)->Callable[...,User]:
    def role_checker(current_user:Annotated[dict[str,Any],Depends(get_current_db_user)])->User:
        user_role = current_user.role
        check_role(user_role,allowed_roles)
        return current_user
    return role_checker    

        
