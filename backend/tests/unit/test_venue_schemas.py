from datetime import datetime

import pytest
from pydantic import ValidationError

from app.schemas.venues import VenueIngestionSchema


# ==========================================
# TEST DATA FACTORY
# ==========================================


def make_venue_data(**overrides) -> dict:

    data = {
        "osm_type": "node",
        "osm_id": "266378530",
        "name": "Test Library",
        "category": "library",
        "latitude": "28.61",
        "longitude": "77.20",
    }

    data.update(overrides)

    return data


# ==========================================
# BASIC SCHEMA VALIDATION
# ==========================================


def test_valid_venue():

    venue = VenueIngestionSchema.model_validate(
        make_venue_data()
    )

    assert venue.osm_type == "node"
    assert venue.osm_id == 266378530
    assert venue.name == "Test Library"
    assert venue.category == "library"

    assert venue.latitude == pytest.approx(28.61)
    assert venue.longitude == pytest.approx(77.20)


def test_schema_field_count():

    assert len(VenueIngestionSchema.model_fields) == 24


def test_numeric_type_conversion():

    venue = VenueIngestionSchema.model_validate(
        make_venue_data()
    )

    assert isinstance(venue.osm_id, int)
    assert isinstance(venue.latitude, float)
    assert isinstance(venue.longitude, float)


# ==========================================
# REQUIRED FIELDS
# ==========================================


@pytest.mark.parametrize(
    "field",
    [
        "osm_type",
        "osm_id",
        "category",
        "latitude",
        "longitude",
    ],
)
def test_missing_required_field(field):

    data = make_venue_data()

    del data[field]

    with pytest.raises(ValidationError):

        VenueIngestionSchema.model_validate(data)


@pytest.mark.parametrize(
    "field",
    [
        "osm_type",
        "osm_id",
        "category",
        "latitude",
        "longitude",
    ],
)
def test_empty_required_field(field):

    with pytest.raises(ValidationError):

        VenueIngestionSchema.model_validate(
            make_venue_data(**{field: ""})
        )


# ==========================================
# OSM ELEMENT TYPES
# ==========================================


@pytest.mark.parametrize(
    "osm_type",
    ["node", "way", "relation"],
)
def test_valid_osm_types(osm_type):

    venue = VenueIngestionSchema.model_validate(
        make_venue_data(osm_type=osm_type)
    )

    assert venue.osm_type == osm_type


@pytest.mark.parametrize(
    "osm_type",
    ["building", "invalid", "", None],
)
def test_invalid_osm_types(osm_type):

    with pytest.raises(ValidationError):

        VenueIngestionSchema.model_validate(
            make_venue_data(osm_type=osm_type)
        )


# ==========================================
# OSM IDENTIFIER VALIDATION
# ==========================================


@pytest.mark.parametrize(
    "osm_id",
    [
        1,
        "123456",
        12_235_020_000,
        9_223_372_036_854_775_807,
    ],
)
def test_valid_osm_identifiers(osm_id):

    venue = VenueIngestionSchema.model_validate(
        make_venue_data(osm_id=osm_id)
    )

    assert venue.osm_id == int(osm_id)


@pytest.mark.parametrize(
    "osm_id",
    [
        0,
        -1,
        "0",
        "-100",
        "abc123",
        "123.45",
        "1e5",
        "",
        "   ",
        None,
        True,
        False,
        123.0,
        9_223_372_036_854_775_808,
    ],
)
def test_invalid_osm_identifiers(osm_id):

    with pytest.raises(ValidationError):

        VenueIngestionSchema.model_validate(
            make_venue_data(osm_id=osm_id)
        )


# ==========================================
# VENUE CATEGORIES
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
def test_valid_categories(category):

    venue = VenueIngestionSchema.model_validate(
        make_venue_data(category=category)
    )

    assert venue.category == category


@pytest.mark.parametrize(
    "category",
    ["invalid_category", "restaurant", "", None],
)
def test_invalid_categories(category):

    with pytest.raises(ValidationError):

        VenueIngestionSchema.model_validate(
            make_venue_data(category=category)
        )


# ==========================================
# COORDINATE BOUNDARY VALIDATION
# ==========================================


@pytest.mark.parametrize(
    "latitude",
    [-90, 0, 90, 28.61],
)
def test_valid_latitude(latitude):

    venue = VenueIngestionSchema.model_validate(
        make_venue_data(latitude=latitude)
    )

    assert venue.latitude == latitude


@pytest.mark.parametrize(
    "longitude",
    [-180, 0, 180, 77.20],
)
def test_valid_longitude(longitude):

    venue = VenueIngestionSchema.model_validate(
        make_venue_data(longitude=longitude)
    )

    assert venue.longitude == longitude


@pytest.mark.parametrize(
    "latitude",
    [
        -90.01,
        90.01,
        "invalid",
        "",
        None,
        True,
        float("inf"),
        float("-inf"),
        float("nan"),
        "NaN",
    ],
)
def test_invalid_latitude(latitude):

    with pytest.raises(ValidationError):

        VenueIngestionSchema.model_validate(
            make_venue_data(latitude=latitude)
        )


@pytest.mark.parametrize(
    "longitude",
    [
        -180.01,
        180.01,
        "invalid",
        "",
        None,
        False,
        float("inf"),
        float("-inf"),
        float("nan"),
        "NaN",
    ],
)
def test_invalid_longitude(longitude):

    with pytest.raises(ValidationError):

        VenueIngestionSchema.model_validate(
            make_venue_data(longitude=longitude)
        )


# ==========================================
# OPTIONAL FIELD NORMALIZATION
# ==========================================


@pytest.mark.parametrize(
    "field",
    [
        "name",
        "access",
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
    ],
)
@pytest.mark.parametrize(
    "value",
    ["", "   ", None],
)
def test_optional_empty_values(field, value):

    venue = VenueIngestionSchema.model_validate(
        make_venue_data(**{field: value})
    )

    assert getattr(venue, field) is None


def test_optional_text_whitespace():

    venue = VenueIngestionSchema.model_validate(
        make_venue_data(
            name="  Heritage School  ",
            operator="  Test Organization  ",
            phone="  +91 9876543210  ",
        )
    )

    assert venue.name == "Heritage School"
    assert venue.operator == "Test Organization"
    assert venue.phone == "+91 9876543210"


# ==========================================
# CATEGORICAL NORMALIZATION
# ==========================================


def test_categorical_normalization():

    venue = VenueIngestionSchema.model_validate(
        make_venue_data(
            osm_type=" NODE ",
            category=" LIBRARY ",
            access_classification=" UNKNOWN ",
            verification_priority=" HIGH ",
            verification_status=" PENDING ",
            public_access_verified=" YES ",
        )
    )

    assert venue.osm_type == "node"
    assert venue.category == "library"
    assert venue.access_classification == "unknown"
    assert venue.verification_priority == "high"
    assert venue.verification_status == "pending"
    assert venue.public_access_verified == "yes"


# ==========================================
# ACCESS CLASSIFICATION
# ==========================================


@pytest.mark.parametrize(
    "access",
    [
        "unknown",
        "restricted",
        "conditional",
        "explicitly_permitted",
    ],
)
def test_valid_access_classification(access):

    venue = VenueIngestionSchema.model_validate(
        make_venue_data(access_classification=access)
    )

    assert venue.access_classification == access


def test_invalid_access_classification():

    with pytest.raises(ValidationError):

        VenueIngestionSchema.model_validate(
            make_venue_data(
                access_classification="invalid"
            )
        )


# ==========================================
# VERIFICATION PRIORITY
# ==========================================


@pytest.mark.parametrize(
    "priority",
    ["low", "medium", "high"],
)
def test_valid_verification_priority(priority):

    venue = VenueIngestionSchema.model_validate(
        make_venue_data(verification_priority=priority)
    )

    assert venue.verification_priority == priority


def test_invalid_verification_priority():

    with pytest.raises(ValidationError):

        VenueIngestionSchema.model_validate(
            make_venue_data(verification_priority="urgent")
        )


# ==========================================
# VERIFICATION STATUS
# ==========================================


@pytest.mark.parametrize(
    "status",
    ["pending", "verified", "rejected"],
)
def test_valid_verification_status(status):

    venue = VenueIngestionSchema.model_validate(
        make_venue_data(verification_status=status)
    )

    assert venue.verification_status == status


def test_invalid_verification_status():

    with pytest.raises(ValidationError):

        VenueIngestionSchema.model_validate(
            make_venue_data(verification_status="invalid")
        )


# ==========================================
# THREE-STATE VERIFICATION
# ==========================================


@pytest.mark.parametrize(
    "field",
    [
        "public_access_verified",
        "indoor_space_verified",
        "air_conditioning_verified",
        "emergency_access_verified",
    ],
)
@pytest.mark.parametrize(
    "value",
    ["yes", "no", "unknown"],
)
def test_valid_verification_values(field, value):

    venue = VenueIngestionSchema.model_validate(
        make_venue_data(**{field: value})
    )

    assert getattr(venue, field) == value


@pytest.mark.parametrize(
    "field",
    [
        "public_access_verified",
        "indoor_space_verified",
        "air_conditioning_verified",
        "emergency_access_verified",
    ],
)
def test_invalid_verification_values(field):

    with pytest.raises(ValidationError):

        VenueIngestionSchema.model_validate(
            make_venue_data(**{field: "invalid"})
        )


# ==========================================
# TIMESTAMP VALIDATION
# ==========================================


@pytest.mark.parametrize(
    "timestamp",
    [
        "2026-11-26T10:30:00+05:30",
        "2026-11-26T05:00:00Z",
    ],
)
def test_timezone_aware_timestamp(timestamp):

    venue = VenueIngestionSchema.model_validate(
        make_venue_data(last_verified=timestamp)
    )

    assert isinstance(venue.last_verified, datetime)

    assert venue.last_verified.tzinfo is not None
    assert venue.last_verified.utcoffset() is not None


@pytest.mark.parametrize(
    "timestamp",
    [
        "2026-11-26T10:30:00",
        "invalid_timestamp",
        "2026-99-99",
    ],
)
def test_invalid_verification_timestamp(timestamp):

    with pytest.raises(ValidationError):

        VenueIngestionSchema.model_validate(
            make_venue_data(last_verified=timestamp)
        )


# ==========================================
# DEFAULT VALUES
# ==========================================


def test_default_values():

    venue = VenueIngestionSchema.model_validate(
        make_venue_data()
    )

    assert venue.access_classification == "unknown"

    assert venue.verification_priority == "medium"
    assert venue.verification_status == "pending"

    assert venue.public_access_verified == "unknown"
    assert venue.indoor_space_verified == "unknown"
    assert venue.air_conditioning_verified == "unknown"
    assert venue.emergency_access_verified == "unknown"

    assert venue.last_verified is None
    assert venue.verification_source is None
    assert venue.verification_notes is None


# ==========================================
# UNEXPECTED ATTRIBUTES
# ==========================================


@pytest.mark.parametrize(
    "field",
    [
        "unexpected_column",
        "id",
        "source",
        "created_at",
        "updated_at",
    ],
)
def test_unexpected_attributes_rejected(field):

    with pytest.raises(ValidationError):

        VenueIngestionSchema.model_validate(
            make_venue_data(**{field: "unexpected"})
        )


# ==========================================
# MODEL SERIALIZATION
# ==========================================


def test_model_dump():

    venue = VenueIngestionSchema.model_validate(
        make_venue_data()
    )

    result = venue.model_dump()

    assert isinstance(result, dict)
    assert len(result) == 24

    assert result["osm_id"] == 266378530
    assert isinstance(result["osm_id"], int)

    assert isinstance(result["latitude"], float)
    assert isinstance(result["longitude"], float)

    assert result["category"] == "library"


# ==========================================
# ACTUAL CSV RECORD STRUCTURE
# ==========================================


def test_complete_csv_record():

    data = {
        "osm_type": "node",
        "osm_id": "266378530",
        "name": "Heritage International School",
        "category": "school",
        "latitude": "28.5084497",
        "longitude": "77.166546",
        "access": "",
        "opening_hours": "",
        "fee": "",
        "operator": "",
        "website": "",
        "phone": "",
        "email": "",
        "wheelchair": "",
        "access_classification": "unknown",
        "verification_priority": "medium",
        "verification_status": "pending",
        "public_access_verified": "unknown",
        "indoor_space_verified": "unknown",
        "air_conditioning_verified": "unknown",
        "emergency_access_verified": "unknown",
        "last_verified": "",
        "verification_source": "",
        "verification_notes": "",
    }

    venue = VenueIngestionSchema.model_validate(data)

    assert venue.osm_id == 266378530
    assert venue.category == "school"

    assert venue.latitude == pytest.approx(28.5084497)
    assert venue.longitude == pytest.approx(77.166546)

    assert venue.name == "Heritage International School"

    assert venue.access is None
    assert venue.phone is None
    assert venue.last_verified is None

    assert venue.verification_status == "pending"