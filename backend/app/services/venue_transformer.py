from datetime import UTC, datetime
from typing import Any

from geoalchemy2.elements import WKTElement

from app.schemas.venues import VenueIngestionSchema


# ==========================================
# TRANSFORMATION CONFIGURATION
# ==========================================

OSM_SOURCE = "osm"

LOCATION_SRID = 4326


# ==========================================
# GEOSPATIAL TRANSFORMATION
# ==========================================

def create_venue_location(
    latitude: float,
    longitude: float,
) -> WKTElement:
    """Convert validated coordinates into a PostGIS point."""

    point = f"POINT({longitude} {latitude})"

    return WKTElement(
        point,
        srid=LOCATION_SRID,
    )


# ==========================================
# VENUE RECORD TRANSFORMATION
# ==========================================

def transform_venue_record(
    venue: VenueIngestionSchema,
    synced_at: datetime,
) -> dict[str, Any]:
    """Convert a validated venue into database-compatible data."""

    # Validate synchronization timestamp

    if (
        synced_at.tzinfo is None
        or synced_at.utcoffset() is None
    ):
        raise ValueError(
            "Synchronization timestamp must be timezone-aware"
        )

    synced_at = synced_at.astimezone(UTC)

    # Convert coordinates into a spatial value

    location = create_venue_location(
        latitude=venue.latitude,
        longitude=venue.longitude,
    )

    # Map validated data to database attributes

    return {

        # Source identification

        "osm_id": venue.osm_id,

        "osm_type": venue.osm_type,

        "source": OSM_SOURCE,

        "last_synced_at": synced_at,

        # Basic venue information

        "name": venue.name,

        "category": venue.category,

        "address": None,

        # Geographic location

        "location": location,

        # Original venue metadata

        "raw_access": venue.access,

        "opening_hours": venue.opening_hours,

        "fee": venue.fee,

        "operator": venue.operator,

        "website": venue.website,

        "phone": venue.phone,

        "email": venue.email,

        "wheelchair": venue.wheelchair,

        # Access classification

        "access_type": venue.access_classification,

        # Verification information

        "verification_priority": venue.verification_priority,

        "verification_status": venue.verification_status,

        "public_access_verified": venue.public_access_verified,

        "indoor_space_verified": venue.indoor_space_verified,

        "air_conditioning_verified": venue.air_conditioning_verified,

        "emergency_access_verified": venue.emergency_access_verified,

        # Verification summary

        "last_verified": venue.last_verified,

        "verification_source": venue.verification_source,

        "verification_notes": venue.verification_notes,

    }