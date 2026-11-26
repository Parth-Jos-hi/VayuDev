from uuid import uuid4
import pytest
from geoalchemy2.elements import WKTElement
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.db.models.venues import Venue
def make_venue(**overrides) -> Venue:
    data = {
        "name": f"VayuDev Test Venue {uuid4()}",
        "category": "library",
        "address": "Test Address",
        "location": WKTElement(
            "POINT(77.20 28.61)",
            srid=4326,
        ),
    }

    data.update(overrides)

    return Venue(**data)


def make_osm_id() -> int:

    return 1_000_000_000_000 + (
        uuid4().int % 1_000_000_000_000
    )


def assert_database_error(
    error: IntegrityError,
    expected_code: str,
    constraint_name: str | None = None,
) -> None:

    original_error = error.orig

    actual_code = (
        getattr(original_error, "sqlstate", None)
        or getattr(original_error, "pgcode", None)
    )

    assert actual_code == expected_code

    if constraint_name is not None:

        diagnostics = getattr(
            original_error,
            "diag",
            None,
        )

        assert diagnostics is not None

        assert (
            diagnostics.constraint_name
            == constraint_name
        )


# ==========================================
# BASIC CRUD OPERATIONS
# ==========================================


def test_venue_database_crud(
    db_session: Session,
):

    venue = make_venue()

    db_session.add(venue)
    db_session.flush()

    venue_id = venue.id
    original_name = venue.name

    db_session.expire_all()

    result = db_session.get(Venue, venue_id)

    assert result is not None
    assert result.name == original_name

    result.name = "Updated VayuDev Test Venue"

    db_session.flush()
    db_session.expire_all()

    updated = db_session.get(Venue, venue_id)

    assert updated is not None
    assert updated.name == "Updated VayuDev Test Venue"

    db_session.delete(updated)
    db_session.flush()
    db_session.expire_all()

    deleted = db_session.execute(
        select(Venue).where(Venue.id == venue_id)
    ).scalar_one_or_none()

    assert deleted is None


# ==========================================
# NULLABLE ATTRIBUTES
# ==========================================


def test_venue_without_name(
    db_session: Session,
):

    venue = make_venue(name=None)

    db_session.add(venue)
    db_session.flush()

    db_session.refresh(venue)

    assert venue.id is not None
    assert venue.name is None


def test_optional_venue_metadata(
    db_session: Session,
):

    venue = make_venue(
        address=None,
        raw_access=None,
        opening_hours=None,
        fee=None,
        operator=None,
        website=None,
        phone=None,
        email=None,
        wheelchair=None,
        last_verified=None,
        verification_source=None,
        verification_notes=None,
        last_synced_at=None,
    )

    db_session.add(venue)
    db_session.flush()
    db_session.refresh(venue)

    optional_fields = [
        "address",
        "raw_access",
        "opening_hours",
        "fee",
        "operator",
        "website",
        "phone",
        "email",
        "wheelchair",
        "last_verified",
        "verification_source",
        "verification_notes",
        "last_synced_at",
    ]

    for field in optional_fields:

        assert getattr(venue, field) is None


# ==========================================
# SOURCE IDENTIFICATION
# ==========================================


def test_large_osm_identifier(
    db_session: Session,
):

    osm_id = make_osm_id()

    assert osm_id > 2_147_483_647

    venue = make_venue(
        source="osm",
        osm_type="node",
        osm_id=osm_id,
    )

    db_session.add(venue)
    db_session.flush()
    db_session.refresh(venue)

    assert venue.osm_id == osm_id
    assert venue.osm_type == "node"
    assert venue.source == "osm"


def test_duplicate_osm_identity_rejected(
    db_session: Session,
):

    osm_id = make_osm_id()

    first_venue = make_venue(
        source="osm",
        osm_type="node",
        osm_id=osm_id,
    )

    db_session.add(first_venue)
    db_session.flush()

    duplicate_venue = make_venue(
        source="osm",
        osm_type="node",
        osm_id=osm_id,
    )

    with pytest.raises(IntegrityError) as exc_info:

        with db_session.begin_nested():

            db_session.add(duplicate_venue)
            db_session.flush()

    assert_database_error(
        exc_info.value,
        "23505",
        "uq_venues_osm_identity",
    )


def test_same_osm_id_different_element_types(
    db_session: Session,
):

    osm_id = make_osm_id()

    venues = [
        make_venue(
            source="osm",
            osm_type="node",
            osm_id=osm_id,
        ),
        make_venue(
            source="osm",
            osm_type="way",
            osm_id=osm_id,
        ),
        make_venue(
            source="osm",
            osm_type="relation",
            osm_id=osm_id,
        ),
    ]

    db_session.add_all(venues)
    db_session.flush()

    assert len({venue.id for venue in venues}) == 3


def test_community_venue_without_osm_identity(
    db_session: Session,
):

    venue = make_venue(
        source="community",
        osm_id=None,
        osm_type=None,
    )

    db_session.add(venue)
    db_session.flush()
    db_session.refresh(venue)

    assert venue.source == "community"
    assert venue.osm_id is None
    assert venue.osm_type is None


def test_multiple_non_osm_venues(
    db_session: Session,
):

    first = make_venue(source="community")
    second = make_venue(source="community")

    db_session.add_all([first, second])
    db_session.flush()

    assert first.id != second.id

    assert first.osm_id is None
    assert second.osm_id is None


def test_osm_source_requires_identity(
    db_session: Session,
):

    venue = make_venue(
        source="osm",
        osm_id=None,
        osm_type=None,
    )

    with pytest.raises(IntegrityError) as exc_info:

        with db_session.begin_nested():

            db_session.add(venue)
            db_session.flush()

    assert_database_error(
        exc_info.value,
        "23514",
        "ck_venues_osm_source",
    )


@pytest.mark.parametrize(
    "identity",
    [
        {
            "osm_id": 123456,
            "osm_type": None,
        },
        {
            "osm_id": None,
            "osm_type": "node",
        },
    ],
)
def test_incomplete_osm_identity_rejected(
    db_session: Session,
    identity: dict,
):

    venue = make_venue(
        source="unknown",
        **identity,
    )

    with pytest.raises(IntegrityError) as exc_info:

        with db_session.begin_nested():

            db_session.add(venue)
            db_session.flush()

    assert_database_error(
        exc_info.value,
        "23514",
        "ck_venues_osm_identity_pair",
    )


# ==========================================
# INVALID ATTRIBUTE VALIDATION
# ==========================================


@pytest.mark.parametrize(
    "attribute,value,constraint_name",
    [
        (
            "category",
            "invalid_category",
            "ck_venues_category",
        ),
        (
            "access_type",
            "invalid_access",
            "ck_venues_access_type",
        ),
        (
            "verification_priority",
            "urgent",
            "ck_venues_verification_priority",
        ),
        (
            "verification_status",
            "invalid_status",
            "ck_venues_verification_status",
        ),
        (
            "public_access_verified",
            "invalid",
            "ck_venues_public_access_verified",
        ),
        (
            "indoor_space_verified",
            "invalid",
            "ck_venues_indoor_space_verified",
        ),
        (
            "air_conditioning_verified",
            "invalid",
            "ck_venues_air_conditioning_verified",
        ),
        (
            "emergency_access_verified",
            "invalid",
            "ck_venues_emergency_access_verified",
        ),
    ],
)
def test_invalid_attribute_rejected(
    db_session: Session,
    attribute: str,
    value: str,
    constraint_name: str,
):

    venue = make_venue(
        **{attribute: value}
    )

    with pytest.raises(IntegrityError) as exc_info:

        with db_session.begin_nested():

            db_session.add(venue)
            db_session.flush()

    assert_database_error(
        exc_info.value,
        "23514",
        constraint_name,
    )


@pytest.mark.parametrize(
    "osm_id",
    [0, -1],
)
def test_invalid_osm_identifier(
    db_session: Session,
    osm_id: int,
):

    venue = make_venue(
        source="osm",
        osm_type="node",
        osm_id=osm_id,
    )

    with pytest.raises(IntegrityError) as exc_info:

        with db_session.begin_nested():

            db_session.add(venue)
            db_session.flush()

    assert_database_error(
        exc_info.value,
        "23514",
        "ck_venues_osm_id",
    )


def test_invalid_osm_type(
    db_session: Session,
):

    venue = make_venue(
        source="osm",
        osm_type="invalid",
        osm_id=make_osm_id(),
    )

    with pytest.raises(IntegrityError) as exc_info:

        with db_session.begin_nested():

            db_session.add(venue)
            db_session.flush()

    assert_database_error(
        exc_info.value,
        "23514",
        "ck_venues_osm_type",
    )


# ==========================================
# VALID CATEGORY VALUES
# ==========================================


@pytest.mark.parametrize(
    "category",
    [
        "school",
        "hospital",
        "clinic",
        "community_centre",
        "library",
        "university",
        "public_building",
    ],
)
def test_valid_venue_categories(
    db_session: Session,
    category: str,
):

    venue = make_venue(category=category)

    db_session.add(venue)
    db_session.flush()
    db_session.refresh(venue)

    assert venue.category == category


# ==========================================
# VALID ACCESS CLASSIFICATIONS
# ==========================================


@pytest.mark.parametrize(
    "access_type",
    [
        "unknown",
        "restricted",
        "conditional",
        "explicitly_permitted",
    ],
)
def test_valid_access_classification(
    db_session: Session,
    access_type: str,
):

    venue = make_venue(
        access_type=access_type,
    )

    db_session.add(venue)
    db_session.flush()
    db_session.refresh(venue)

    assert venue.access_type == access_type


# ==========================================
# THREE-STATE VERIFICATION
# ==========================================


@pytest.mark.parametrize(
    "verification_value",
    ["yes", "no", "unknown"],
)
def test_valid_verification_values(
    db_session: Session,
    verification_value: str,
):

    venue = make_venue(
        public_access_verified=verification_value,
        indoor_space_verified=verification_value,
        air_conditioning_verified=verification_value,
        emergency_access_verified=verification_value,
    )

    db_session.add(venue)
    db_session.flush()
    db_session.refresh(venue)

    assert (
        venue.public_access_verified
        == verification_value
    )

    assert (
        venue.indoor_space_verified
        == verification_value
    )

    assert (
        venue.air_conditioning_verified
        == verification_value
    )

    assert (
        venue.emergency_access_verified
        == verification_value
    )


@pytest.mark.parametrize(
    "priority",
    ["low", "medium", "high"],
)
def test_valid_verification_priority(
    db_session: Session,
    priority: str,
):

    venue = make_venue(
        verification_priority=priority,
    )

    db_session.add(venue)
    db_session.flush()
    db_session.refresh(venue)

    assert venue.verification_priority == priority


@pytest.mark.parametrize(
    "status",
    ["pending", "verified", "rejected"],
)
def test_valid_verification_status(
    db_session: Session,
    status: str,
):

    venue = make_venue(
        verification_status=status,
    )

    db_session.add(venue)
    db_session.flush()
    db_session.refresh(venue)

    assert venue.verification_status == status


# ==========================================
# DEFAULT VALUES
# ==========================================


def test_venue_orm_defaults(
    db_session: Session,
):

    venue = make_venue()

    db_session.add(venue)
    db_session.flush()
    db_session.refresh(venue)

    assert venue.id is not None

    assert venue.source == "unknown"
    assert venue.access_type == "unknown"

    assert venue.verification_priority == "medium"
    assert venue.verification_status == "pending"

    assert venue.public_access_verified == "unknown"
    assert venue.indoor_space_verified == "unknown"
    assert venue.air_conditioning_verified == "unknown"
    assert venue.emergency_access_verified == "unknown"

    assert venue.created_at is not None
    assert venue.updated_at is not None


def test_database_server_defaults(
    db_session: Session,
):

    venue_id = uuid4()

    result = db_session.execute(
        text(
            """
            INSERT INTO venues (
                id,
                category,
                location
            )
            VALUES (
                :venue_id,
                'library',
                ST_GeogFromText(
                    'SRID=4326;POINT(77.20 28.61)'
                )
            )
            RETURNING
                source,
                access_type,
                verification_priority,
                verification_status,
                public_access_verified,
                indoor_space_verified,
                air_conditioning_verified,
                emergency_access_verified,
                created_at,
                updated_at
            """
        ),
        {
            "venue_id": venue_id,
        },
    ).mappings().one()

    assert result["source"] == "unknown"
    assert result["access_type"] == "unknown"

    assert result["verification_priority"] == "medium"
    assert result["verification_status"] == "pending"

    assert result["public_access_verified"] == "unknown"
    assert result["indoor_space_verified"] == "unknown"
    assert result["air_conditioning_verified"] == "unknown"
    assert result["emergency_access_verified"] == "unknown"

    assert result["created_at"] is not None
    assert result["updated_at"] is not None


# ==========================================
# POSTGIS LOCATION VALIDATION
# ==========================================


def test_postgis_location_storage(
    db_session: Session,
):

    venue = make_venue(
        location=WKTElement(
            "POINT(77.20 28.61)",
            srid=4326,
        ),
    )

    db_session.add(venue)
    db_session.flush()

    result = db_session.execute(
        text(
            """
            SELECT
                ST_X(location::geometry) AS longitude,
                ST_Y(location::geometry) AS latitude,
                ST_SRID(location::geometry) AS srid
            FROM venues
            WHERE id = :venue_id
            """
        ),
        {
            "venue_id": venue.id,
        },
    ).mappings().one()

    assert result["longitude"] == pytest.approx(77.20)
    assert result["latitude"] == pytest.approx(28.61)

    assert result["srid"] == 4326


# ==========================================
# TRANSACTION RECOVERY
# ==========================================


def test_transaction_recovery_after_violation(
    db_session: Session,
):

    valid_venue = make_venue()

    db_session.add(valid_venue)
    db_session.flush()

    valid_venue_id = valid_venue.id

    invalid_venue = make_venue(
        category="invalid_category",
    )

    with pytest.raises(IntegrityError):

        with db_session.begin_nested():

            db_session.add(invalid_venue)
            db_session.flush()

    db_session.expire_all()

    result = db_session.get(
        Venue,
        valid_venue_id,
    )

    assert result is not None

    another_venue = make_venue()

    db_session.add(another_venue)
    db_session.flush()

    assert another_venue.id is not None


# ==========================================
# REQUIRED ATTRIBUTES
# ==========================================


def test_null_category_rejected(
    db_session: Session,
):

    venue = make_venue(category=None)

    with pytest.raises(IntegrityError) as exc_info:

        with db_session.begin_nested():

            db_session.add(venue)
            db_session.flush()

    assert_database_error(
        exc_info.value,
        "23502",
    )


def test_null_location_rejected(
    db_session: Session,
):

    venue = make_venue(location=None)

    with pytest.raises(IntegrityError) as exc_info:

        with db_session.begin_nested():

            db_session.add(venue)
            db_session.flush()

    assert_database_error(
        exc_info.value,
        "23502",
    )