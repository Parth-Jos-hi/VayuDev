from typing import Any,Annotated
from app.core.security.jwt import verify_access_token
from fastapi import HTTPException,status,Depends
from fastapi.security import HTTPAuthorizationCredentials,HTTPBearer
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