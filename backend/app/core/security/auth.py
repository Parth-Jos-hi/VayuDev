from typing import Any,Annotated
from app.core.security.jwt import verify_access_token
from fastapi import HTTPException,status,Depends
from fastapi.security import HTTPAuthorizationCredentials,HTTPBearer
from sqlalchemy.orm import Session
from app.db.models.users import User
from app.services.user_service import get_or_create_user
from app.db.session import get_db
from uuid import UUID
security = HTTPBearer(auto_error=False  )
def get_current_user(credentials:Annotated[HTTPAuthorizationCredentials|None,Depends(security)])-> dict[str,Any]:
    if credentials is None:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail = "There are no credentials available",
            headers = {"WWW-Authenticate":"Bearer"},          
        )                                                    
    if credentials.scheme.lower()!="bearer":    
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail = "The authentication scheme is not Bearer",
            headers = {"WWW-Authenticate":"Bearer"},
        )
    token = credentials.credentials
    claims = verify_access_token(token)
    return claims   
def get_current_db_user(claims:Annotated[dict[str,Any],Depends(get_current_user),],db: Annotated[Session,Depends(get_db),],) -> User:
        user_id = UUID(claims["sub"])
        user = get_or_create_user(db,user_id)
        return user

