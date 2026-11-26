from datetime import datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


OSMType = Literal[
    "node",
    "way",
    "relation",
]
VenueCategory = Literal[
    "school",
    "hospital",
    "clinic",
    "community_centre",
    "library",
    "university",
    "public_building",
]


AccessClassification = Literal[
    "unknown",
    "restricted",
    "conditional",
    "explicitly_permitted",
]


VerificationPriority = Literal[
    "low",
    "medium",
    "high",
]


VerificationStatus = Literal[
    "pending",
    "verified",
    "rejected",
]

## literal is used to get the preferred output in the respecctive fields giving the bracket
VerificationValue = Literal[
    "yes",
    "no",
    "unknown",
]


# ==========================================
# VENUE INGESTION SCHEMA
# ==========================================

class VenueIngestionSchema(BaseModel):
    ## set of rules followed throughout the whole models files
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_default=True,
    )


    osm_type: OSMType

    osm_id: int = Field(
        gt=0,
        le=9_223_372_036_854_775_807,
    )

    name: str | None = None

    category: VenueCategory

    latitude: float = Field(
        ge=-90,
        le=90,
        allow_inf_nan=False,
    )

    longitude: float = Field(
        ge=-180,
        le=180,
        allow_inf_nan=False,
    )

    access: str | None = None

    opening_hours: str | None = None

    fee: str | None = None

    operator: str | None = None

    website: str | None = None

    phone: str | None = None

    email: str | None = None

    wheelchair: str | None = None

    access_classification: AccessClassification = "unknown"


    verification_priority: VerificationPriority = "medium"

    verification_status: VerificationStatus = "pending"

    public_access_verified: VerificationValue = "unknown"

    indoor_space_verified: VerificationValue = "unknown"

    air_conditioning_verified: VerificationValue = "unknown"

    emergency_access_verified: VerificationValue = "unknown"

    last_verified: datetime | None = None
    verification_source: str | None = None
    verification_notes: str | None = None
    @field_validator(
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
        mode="before",
    )
    @classmethod
    def normalize_optional_fields(cls, value):
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
        return value
    @field_validator(
        "osm_type",
        "category",
        "access_classification",
        "verification_priority",
        "verification_status",
        "public_access_verified",
        "indoor_space_verified",
        "air_conditioning_verified",
        "emergency_access_verified",
        mode="before",
    )
    @classmethod
    def normalize_categorical_fields(cls, value):

        if isinstance(value, str):
            return value.strip().lower()

        return value

    # ==========================================
    # NUMERICAL INPUT NORMALIZATION
    # ==========================================

    @field_validator(
        "osm_id",
        mode="before",
    )
    @classmethod
    def validate_osm_identifier_input(cls, value):

        if isinstance(value, bool):
            raise ValueError(
                "OSM identifier cannot be a boolean"
            )

        if isinstance(value, str):

            value = value.strip()

            if not value.isascii() or not value.isdigit():
                raise ValueError(
                    "OSM identifier must contain decimal digits"
                )

        elif not isinstance(value, int):

            raise ValueError(
                "OSM identifier must be an integer"
            )

        return value

    @field_validator(
        "latitude",
        "longitude",
        mode="before",
    )
    @classmethod
    def normalize_coordinate_input(cls, value):

        if isinstance(value, bool):
            raise ValueError(
                "Coordinates cannot be boolean values"
            )

        if isinstance(value, str):
            return value.strip()

        return value

    # ==========================================
    # VERIFICATION TIMESTAMP VALIDATION
    # ==========================================

    @field_validator(
        "last_verified",
        mode="after",
    )
    @classmethod
    def validate_verification_timestamp(cls, value):

        if value is not None:

            if value.tzinfo is None or value.utcoffset() is None:

                raise ValueError(
                    "Verification timestamp must include timezone information"
                )

        return value