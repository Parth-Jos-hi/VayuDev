from datetime import (
    UTC,
    datetime,
    timedelta,
    timezone,
)

import pytest

from geoalchemy2.elements import WKTElement

from app.db.models.venues import Venue

from app.schemas.venues import VenueIngestionSchema

from app.services.venue_transformer import (
    LOCATION_SRID,
    OSM_SOURCE,
    create_venue_location,
    transform_venue_record,
)


# ==========================================
# TEST FIXTURES
# ==========================================

@pytest.fixture
def synced_at():

    return datetime(
        2026, 11, 27, 10, 0,
        tzinfo=UTC,
    )


@pytest.fixture
def venue():

    return VenueIngestionSchema.model_validate({
        "osm_type": "node",
        "osm_id": "266378530",
        "name": "Test Library",
        "category": "library",
        "latitude": "28.5084497",
        "longitude": "77.166546",
        "access": "yes",
        "opening_hours": "09:00-18:00",
        "fee": "no",
        "operator": "Test Organization",
        "website": "https://example.com",
        "phone": "+91 9876543210",
        "email": "test@example.com",
        "wheelchair": "yes",
        "access_classification": "explicitly_permitted",
        "verification_priority": "high",
        "verification_status": "pending",
        "public_access_verified": "unknown",
        "indoor_space_verified": "unknown",
        "air_conditioning_verified": "unknown",
        "emergency_access_verified": "unknown",
    })


# ==========================================
# TRANSFORMATION CONSTANTS
# ==========================================

def test_osm_source():

    assert OSM_SOURCE == "osm"


def test_location_srid():

    assert LOCATION_SRID == 4326


# ==========================================
# GEOSPATIAL TRANSFORMATION
# ==========================================

def test_location_type():

    location = create_venue_location(
        latitude=28.61,
        longitude=77.20,
    )

    assert isinstance(location, WKTElement)


def test_location_srid_value():

    location = create_venue_location(
        latitude=28.61,
        longitude=77.20,
    )

    assert location.srid == 4326


def test_longitude_latitude_order():

    location = create_venue_location(
        latitude=28.5084497,
        longitude=77.166546,
    )

    assert location.data == (
        "POINT(77.166546 28.5084497)"
    )


@pytest.mark.parametrize(
    "latitude,longitude",
    [
        (0.0, 0.0),
        (-90.0, -180.0),
        (90.0, 180.0),
        (-33.86, 151.20),
        (51.50, -0.12),
    ],
)
def test_coordinate_mapping(latitude, longitude):

    location = create_venue_location(
        latitude=latitude,
        longitude=longitude,
    )

    assert location.data == (
        f"POINT({longitude} {latitude})"
    )


# ==========================================
# BASIC FIELD MAPPING
# ==========================================

def test_transformation_returns_dictionary(
    venue,
    synced_at,
):

    result = transform_venue_record(
        venue,
        synced_at,
    )

    assert isinstance(result, dict)


def test_transformed_field_count(
    venue,
    synced_at,
):

    result = transform_venue_record(
        venue,
        synced_at,
    )

    assert len(result) == 26


@pytest.mark.parametrize(
    "field",
    [
        "osm_id",
        "osm_type",
        "name",
        "category",
        "opening_hours",
        "fee",
        "operator",
        "website",
        "phone",
        "email",
        "wheelchair",
        "verification_priority",
        "verification_status",
        "public_access_verified",
        "indoor_space_verified",
        "air_conditioning_verified",
        "emergency_access_verified",
        "last_verified",
        "verification_source",
        "verification_notes",
    ],
)
def test_direct_field_mapping(
    venue,
    synced_at,
    field,
):

    result = transform_venue_record(
        venue,
        synced_at,
    )

    assert result[field] == getattr(
        venue,
        field,
    )


# ==========================================
# RENAMED ATTRIBUTES
# ==========================================

def test_raw_access_mapping(
    venue,
    synced_at,
):

    result = transform_venue_record(
        venue,
        synced_at,
    )

    assert result["raw_access"] == "yes"

    assert "access" not in result


def test_access_classification_mapping(
    venue,
    synced_at,
):

    result = transform_venue_record(
        venue,
        synced_at,
    )

    assert result["access_type"] == (
        "explicitly_permitted"
    )

    assert "access_classification" not in result


# ==========================================
# GENERATED ATTRIBUTES
# ==========================================

def test_source_assignment(
    venue,
    synced_at,
):

    result = transform_venue_record(
        venue,
        synced_at,
    )

    assert result["source"] == "osm"


def test_address_defaults_to_none(
    venue,
    synced_at,
):

    result = transform_venue_record(
        venue,
        synced_at,
    )

    assert result["address"] is None


def test_location_replaces_coordinates(
    venue,
    synced_at,
):

    result = transform_venue_record(
        venue,
        synced_at,
    )

    assert isinstance(
        result["location"],
        WKTElement,
    )

    assert "latitude" not in result

    assert "longitude" not in result


# ==========================================
# TIMESTAMP TRANSFORMATION
# ==========================================

def test_synchronization_timestamp(
    venue,
    synced_at,
):

    result = transform_venue_record(
        venue,
        synced_at,
    )

    assert result["last_synced_at"] == synced_at


def test_timestamp_converted_to_utc(venue):

    ist = timezone(
        timedelta(hours=5, minutes=30)
    )

    timestamp = datetime(
        2026, 11, 27, 10, 0,
        tzinfo=ist,
    )

    result = transform_venue_record(
        venue,
        timestamp,
    )

    expected = datetime(
        2026, 11, 27, 4, 30,
        tzinfo=UTC,
    )

    assert result["last_synced_at"] == expected

    assert result["last_synced_at"].tzinfo == UTC


def test_naive_timestamp_rejected(venue):

    timestamp = datetime(
        2026, 11, 27, 10, 0
    )

    with pytest.raises(
        ValueError,
        match="timezone-aware",
    ):

        transform_venue_record(
            venue,
            timestamp,
        )


# ==========================================
# OPTIONAL METADATA
# ==========================================

def test_optional_fields_preserved(synced_at):

    venue = VenueIngestionSchema.model_validate({
        "osm_type": "node",
        "osm_id": "100",
        "category": "library",
        "latitude": "28.61",
        "longitude": "77.20",
    })

    result = transform_venue_record(
        venue,
        synced_at,
    )

    optional_fields = [
        "name",
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
    ]

    for field in optional_fields:

        assert result[field] is None


def test_verification_information_preserved(
    venue,
    synced_at,
):

    verified_at = datetime(
        2026, 11, 26, 12, 0,
        tzinfo=UTC,
    )

    data = venue.model_dump()

    data.update({
        "verification_status": "verified",
        "public_access_verified": "yes",
        "indoor_space_verified": "yes",
        "air_conditioning_verified": "yes",
        "emergency_access_verified": "no",
        "last_verified": verified_at,
        "verification_source": "manual_review",
        "verification_notes": "Inspection completed",
    })

    verified = VenueIngestionSchema.model_validate(
        data
    )

    result = transform_venue_record(
        verified,
        synced_at,
    )

    assert result["verification_status"] == "verified"

    assert result["public_access_verified"] == "yes"

    assert result["indoor_space_verified"] == "yes"

    assert result["air_conditioning_verified"] == "yes"

    assert result["emergency_access_verified"] == "no"

    assert result["last_verified"] == verified_at

    assert result["verification_source"] == "manual_review"

    assert result["verification_notes"] == (
        "Inspection completed"
    )


# ==========================================
# DATABASE MODEL COMPATIBILITY
# ==========================================

def test_database_generated_fields_excluded(
    venue,
    synced_at,
):

    result = transform_venue_record(
        venue,
        synced_at,
    )

    assert "id" not in result

    assert "created_at" not in result

    assert "updated_at" not in result


def test_sqlalchemy_model_field_mapping(
    venue,
    synced_at,
):

    result = transform_venue_record(
        venue,
        synced_at,
    )

    expected = set(
        Venue.__table__.columns.keys()
    ) - {
        "id",
        "created_at",
        "updated_at",
    }

    assert set(result) == expected


def test_sqlalchemy_object_construction(
    venue,
    synced_at,
):

    result = transform_venue_record(
        venue,
        synced_at,
    )

    model = Venue(**result)

    assert model.osm_id == venue.osm_id

    assert model.osm_type == venue.osm_type

    assert model.category == venue.category

    assert model.source == "osm"


# ==========================================
# TRANSFORMATION INDEPENDENCE
# ==========================================

def test_input_schema_not_modified(
    venue,
    synced_at,
):

    original = venue.model_dump()

    transform_venue_record(
        venue,
        synced_at,
    )

    assert venue.model_dump() == original


def test_independent_transformation_results(
    venue,
    synced_at,
):

    first = transform_venue_record(
        venue,
        synced_at,
    )

    second = transform_venue_record(
        venue,
        synced_at,
    )

    assert first is not second

    first["name"] = "Changed Name"

    assert second["name"] == venue.name


def test_deterministic_transformation(
    venue,
    synced_at,
):

    first = transform_venue_record(
        venue,
        synced_at,
    )

    second = transform_venue_record(
        venue,
        synced_at,
    )

    assert first.keys() == second.keys()

    for key in first:

        if key == "location":

            assert first[key].data == second[key].data

            assert first[key].srid == second[key].srid

        else:

            assert first[key] == second[key]