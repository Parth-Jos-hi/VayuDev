
import pytest

from uuid import uuid4
from fastapi import HTTPException

from app.core.security.permissions import (
    check_role,
    check_venue_ownership,
)


# TEST 1: Allowed role
def test_allowed_role() -> None:
    check_role("admin", {"admin"})


# TEST 2: Disallowed role
def test_disallowed_role() -> None:
    with pytest.raises(HTTPException) as exc_info:
        check_role("user", {"admin"})

    assert exc_info.value.status_code == 403


# TEST 3: Multiple allowed roles
def test_multiple_allowed_roles() -> None:
    check_role("moderator", {"admin", "moderator"})


# TEST 4: Correct venue owner
def test_correct_venue_owner() -> None:
    owner_id = uuid4()
    venue_id = uuid4()

    check_venue_ownership(
        owner_id,
        venue_id,
        owner_id,
    )


# TEST 5: Incorrect venue owner
def test_incorrect_venue_owner() -> None:
    owner_id = uuid4()
    other_owner_id = uuid4()
    venue_id = uuid4()

    with pytest.raises(HTTPException) as exc_info:
        check_venue_ownership(
            owner_id,
            venue_id,
            other_owner_id,
        )

    assert exc_info.value.status_code == 403


# TEST 6: No approved owner
def test_no_approved_owner() -> None:
    owner_id = uuid4()
    venue_id = uuid4()

    with pytest.raises(HTTPException) as exc_info:
        check_venue_ownership(
            owner_id,
            venue_id,
            None,
        )

    assert exc_info.value.status_code == 403
