
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest

from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException

from app.core.config import settings
from app.core.security.jwt import (
    verify_access_token,
    jwks_client,
)


@pytest.fixture
def private_key():
    return ec.generate_private_key(ec.SECP256R1())


@pytest.fixture
def valid_claims():
    now = datetime.now(timezone.utc)

    return {
        "sub": str(uuid4()),
        "iss": settings.supabase_jwt_issuer,
        "aud": "authenticated",
        "role": "authenticated",
        "iat": now,
        "exp": now + timedelta(hours=1),
    }


@pytest.fixture
def mock_signing_key(monkeypatch, private_key):

    def get_signing_key(token):
        return SimpleNamespace(
            key=private_key.public_key()
        )

    monkeypatch.setattr(
        jwks_client,
        "get_signing_key_from_jwt",
        get_signing_key,
    )


def test_valid_token(
    private_key,
    valid_claims,
    mock_signing_key,
):
    token = jwt.encode(
        valid_claims,
        private_key,
        algorithm="ES256",
    )

    claims = verify_access_token(token)

    assert claims["sub"] == valid_claims["sub"]
    assert claims["role"] == "authenticated"


def test_missing_token():
    with pytest.raises(HTTPException) as exc_info:
        verify_access_token("")

    assert exc_info.value.status_code == 401


def test_invalid_token(mock_signing_key):
    with pytest.raises(HTTPException) as exc_info:
        verify_access_token("invalid_token")

    assert exc_info.value.status_code == 401


def test_expired_token(
    private_key,
    valid_claims,
    mock_signing_key,
):
    now = datetime.now(timezone.utc)

    valid_claims["iat"] = now - timedelta(hours=2)
    valid_claims["exp"] = now - timedelta(hours=1)

    token = jwt.encode(
        valid_claims,
        private_key,
        algorithm="ES256",
    )

    with pytest.raises(HTTPException) as exc_info:
        verify_access_token(token)

    assert exc_info.value.status_code == 401


def test_invalid_issuer(
    private_key,
    valid_claims,
    mock_signing_key,
):
    valid_claims["iss"] = "https://invalid-issuer.example"

    token = jwt.encode(
        valid_claims,
        private_key,
        algorithm="ES256",
    )

    with pytest.raises(HTTPException) as exc_info:
        verify_access_token(token)

    assert exc_info.value.status_code == 401


def test_invalid_audience(
    private_key,
    valid_claims,
    mock_signing_key,
):
    valid_claims["aud"] = "invalid-audience"

    token = jwt.encode(
        valid_claims,
        private_key,
        algorithm="ES256",
    )

    with pytest.raises(HTTPException) as exc_info:
        verify_access_token(token)

    assert exc_info.value.status_code == 401


def test_invalid_signature(
    valid_claims,
    mock_signing_key,
):
    different_key = ec.generate_private_key(
        ec.SECP256R1()
    )

    token = jwt.encode(
        valid_claims,
        different_key,
        algorithm="ES256",
    )

    with pytest.raises(HTTPException) as exc_info:
        verify_access_token(token)

    assert exc_info.value.status_code == 401


def test_invalid_role(
    private_key,
    valid_claims,
    mock_signing_key,
):
    valid_claims["role"] = "anon"

    token = jwt.encode(
        valid_claims,
        private_key,
        algorithm="ES256",
    )

    with pytest.raises(HTTPException) as exc_info:
        verify_access_token(token)

    assert exc_info.value.status_code == 401


def test_invalid_user_id(
    private_key,
    valid_claims,
    mock_signing_key,
):
    valid_claims["sub"] = "invalid-uuid"

    token = jwt.encode(
        valid_claims,
        private_key,
        algorithm="ES256",
    )

    with pytest.raises(HTTPException) as exc_info:
        verify_access_token(token)

    assert exc_info.value.status_code == 401
