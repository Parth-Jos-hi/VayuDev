from uuid import UUID
from fastapi import HTTPException,status
def check_role(user_role:str,allowed_roles:set[str]):
    if user_role in allowed_roles:
        pass
    