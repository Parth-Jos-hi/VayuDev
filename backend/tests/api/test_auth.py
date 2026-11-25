
from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from fastapi.testclient import TestClient

from app.main import app
from app.db.models.users import User
from app.db.session import get_db
from app.core.security.auth import get_current_user
from app.core.security.auth import get_current_db_user


@pytest.fixture
def fake_user():    
    now = datetime.now(timezone.utc)

    return User(
        id=uuid4(),
        display_name="Test User",
        role="user",
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def fake_db():
    return MagicMock()


@pytest.fixture
def authenticated_client(fake_user, fake_db):
    previous_overrides = app.dependency_overrides.copy()

    app.dependency_overrides[get_current_db_user] = (
        lambda: fake_user
    )

    app.dependency_overrides[get_db] = (
        lambda: fake_db
    )

    try:
        with TestClient(app) as client:
            yield client

    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(
            previous_overrides
        )


def test_get_profile(authenticated_client, fake_user):
    response = authenticated_client.get(
        "/api/v1/auth/me"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == str(fake_user.id)
    assert data["display_name"] == "Test User"
    assert data["role"] == "user"


def test_update_profile(authenticated_client, fake_db):
    response = authenticated_client.patch(
        "/api/v1/auth/me",
        json={
            "display_name": "Updated User"
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["display_name"] == "Updated User"
    assert data["role"] == "user"

    fake_db.commit.assert_called_once()
    fake_db.refresh.assert_called_once()


def test_invalid_display_name(authenticated_client):
    response = authenticated_client.patch(
        "/api/v1/auth/me",
        json={"display_name": "A"},
    )

    assert response.status_code == 422


def test_role_injection(authenticated_client, fake_db):
    response = authenticated_client.patch(
        "/api/v1/auth/me",
        json={"role": "admin"},
    )

    assert response.status_code == 422

    fake_db.commit.assert_not_called()


def test_user_id_injection(authenticated_client):
    response = authenticated_client.patch(
        "/api/v1/auth/me",
        json={"id": str(uuid4())},
    )

    assert response.status_code == 422


def test_empty_update(authenticated_client, fake_db):
    response = authenticated_client.patch(
        "/api/v1/auth/me",
        json={},
    )

    assert response.status_code == 200

    assert response.json()["display_name"] == "Test User"

    fake_db.commit.assert_not_called()


def test_clear_display_name(authenticated_client):
    response = authenticated_client.patch(
        "/api/v1/auth/me",
        json={"display_name": None},
    )

    assert response.status_code == 200

    assert response.json()["display_name"] is None


def test_whitespace_handling(authenticated_client):
    response = authenticated_client.patch(
        "/api/v1/auth/me",
        json={
            "display_name": "   Updated User   "
        },
    )

    assert response.status_code == 200

    assert response.json()["display_name"] == "Updated User"


@pytest.mark.parametrize("method", ["GET", "PATCH"])
def test_missing_authentication(method):
    previous_overrides = app.dependency_overrides.copy()

    app.dependency_overrides.pop(
        get_current_db_user,
        None,
    )

    app.dependency_overrides.pop(
        get_current_user,
        None,
    )

    app.dependency_overrides[get_db] = (
        lambda: MagicMock()
    )

    try:
        with TestClient(app) as client:

            if method == "GET":
                response = client.get(
                    "/api/v1/auth/me"
                )

            else:
                response = client.patch(
                    "/api/v1/auth/me",
                    json={
                        "display_name": "Unauthorized User"
                    },
                )

            assert response.status_code == 401

    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(
            previous_overrides
        )
