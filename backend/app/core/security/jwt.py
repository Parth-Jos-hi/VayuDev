
from typing import Any
from uuid import UUID
import jwt
from jwt import PyJWKClient
from jwt.exceptions import (
    ExpiredSignatureError,
    InvalidTokenError,
    PyJWKClientConnectionError,
    PyJWKClientError,
)
from fastapi import HTTPException,status
from app.core.config import settings
## public signing key provided by supabase auth
jwks_client = PyJWKClient(
    settings.supabase_jwks_url,
    timeout=5,
)
def verify_access_token(token:str)-> dict[str,Any]:
    ## here first verify the jwt access token.
    ## after that return JWT claims.
    ## then raise
    ## HTTPExceptions
    ## 401: Missing,Expired or invalid token.
    ## 503: Unable to retrieve signing keys.
    if not token or not token.strip():
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail = "Authentication token is required",
            headers = {"WWW-Authenticate":"Bearer"},
        )
    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token)

        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms = ["ES256"],
            issuer = settings.supabase_jwt_issuer,
            audience = "authenticated",
            options = {
                "require":[
                    "exp",
                    "iat",
                    "iss",
                    "aud",
                    "sub",
                    "role", 
                ],
            },
        )
        UUID(claims["sub"])
        if claims["role"]!="authenticated":
            raise HTTPException(
                status_code = status.HTTP_401_UNAUTHORIZED,
                detail = "Invalid authentication role",
                headers = {"WWW-Authenticate":"Bearer"},
            )
        return claims
    except PyJWKClientConnectionError as exc:
        raise HTTPException(
            status_code = status.HTTP_503_SERVICE_UNAVAILABLE,
            detail = "Authentication verification service unavialable",
        ) from exc
    except (
        ExpiredSignatureError,
        InvalidTokenError,
        PyJWKClientError,
        ValueError,
        TypeError,
        RecursionError,
    ) as exc:
        raise HTTPException(
            status_code = status.HTTP_401_UNAUTHORIZED,
            detail = "Invalid or expired authentication token",
            headers = {"WWW-Authenticate":"Bearer"},
        ) from exc
