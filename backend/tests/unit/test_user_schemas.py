from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4
import pytest
from pydantic import ValidationError
from app.schemas.users import UserUpdate, UserResponse
def test_valid_display_name():
    profile = UserUpdate(
        display_name="VayuDev User"
    )

    assert profile.display_name == "VayuDev User"


def test_short_display_name():
    with pytest.raises(ValidationError):
        UserUpdate(display_name="A")


def test_long_display_name():
    with pytest.raises(ValidationError):
        UserUpdate(display_name="A" * 51)


def test_whitespace_only_display_name():
    with pytest.raises(ValidationError):
        UserUpdate(display_name="   ")


def test_strip_whitespace():
    profile = UserUpdate(
        display_name="   VayuDev User   "
    )

    assert profile.display_name == "VayuDev User"


def test_null_display_name():
    profile = UserUpdate(display_name=None)

    assert profile.display_name is None

    assert profile.model_dump(
        exclude_unset=True
    ) == {"display_name": None}


def test_empty_update():
    profile = UserUpdate()

    assert profile.model_dump(
        exclude_unset=True
    ) == {}


def test_role_injection():
    with pytest.raises(ValidationError):
        UserUpdate(
            display_name="VayuDev User",
            role="admin",
        )


def test_user_id_injection():
    with pytest.raises(ValidationError):
        UserUpdate(
            display_name="VayuDev User",
            id=uuid4(),
        )


def test_user_response_from_attributes():
    user = SimpleNamespace(
        id=uuid4(),
        display_name="VayuDev User",
        role="user",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    response = UserResponse.model_validate(user)

    assert response.id == user.id
    assert response.display_name == user.display_name
    assert response.role == user.role


def test_user_response_with_null_name():
    user = SimpleNamespace(
        id=uuid4(),
        display_name=None,
        role="user",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    response = UserResponse.model_validate(user)

    assert response.display_name is None
