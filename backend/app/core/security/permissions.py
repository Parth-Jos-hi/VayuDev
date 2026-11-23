from uuid import UUID
from fastapi import HTTPException, status
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
