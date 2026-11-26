from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Text,
    UniqueConstraint,
    UUID as SQLAlchemyUUID,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from geoalchemy2 import Geography
from geoalchemy2.elements import WKBElement

from app.db.base import Base


class Venue(Base):

    __tablename__ = "venues"

    __table_args__ = (
        # It Prevent duplicate OSM identities
        UniqueConstraint(
            "osm_type",
            "osm_id",
            name="uq_venues_osm_identity",
        ),
        # Validate OSM element type
        CheckConstraint(
            "osm_type IN ('node', 'way', 'relation')",
            name="ck_venues_osm_type",
        ),
        # Validate OSM identifier
        CheckConstraint(
            "osm_id > 0",
            name="ck_venues_osm_id",
        ),
        # Both OSM identifiers must exist together
        CheckConstraint(
            """
            (
                osm_id IS NULL
                AND osm_type IS NULL
            )
            OR
            (
                osm_id IS NOT NULL
                AND osm_type IS NOT NULL
            )
            """,
            name="ck_venues_osm_identity_pair",
        ),

        # OSM-sourced venues require OSM identifiers
        CheckConstraint(
            """
            source <> 'osm'
            OR
            (
                osm_id IS NOT NULL
                AND osm_type IS NOT NULL
            )
            """,
            name="ck_venues_osm_source",
        ),
        # Validate venue category
        CheckConstraint(
            """
            category IN (
                'school',
                'hospital',
                'clinic',
                'community_centre',
                'library',
                'university',
                'public_building'
            )
            """,
            name="ck_venues_category",
        ),

        # Validate access classification
        CheckConstraint(
            """
            access_type IN (
                'unknown',
                'restricted',
                'conditional',
                'explicitly_permitted'
            )
            """,
            name="ck_venues_access_type",
        ),

        # Validate verification priority
        CheckConstraint(
            """
            verification_priority IN (
                'low',
                'medium',
                'high'
            )
            """,
            name="ck_venues_verification_priority",
        ),

        # Validate verification status
        CheckConstraint(
            """
            verification_status IN (
                'pending',
                'verified',
                'rejected'
            )
            """,
            name="ck_venues_verification_status",
        ),

        # Validate public access verification
        CheckConstraint(
            """
            public_access_verified IN (
                'yes', 'no', 'unknown'
            )
            """,
            name="ck_venues_public_access_verified",
        ),

        # Validate indoor space verification
        CheckConstraint(
            """
            indoor_space_verified IN (
                'yes', 'no', 'unknown'
            )
            """,
            name="ck_venues_indoor_space_verified",
        ),

        # Validate air conditioning verification
        CheckConstraint(
            """
            air_conditioning_verified IN (
                'yes', 'no', 'unknown'
            )
            """,
            name="ck_venues_air_conditioning_verified",
        ),

        # Validate emergency access verification
        CheckConstraint(
            """
            emergency_access_verified IN (
                'yes', 'no', 'unknown'
            )
            """,
            name="ck_venues_emergency_access_verified",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        SQLAlchemyUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    osm_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    osm_type: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    source: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="unknown",
        server_default="unknown",
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    name: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    category: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    address: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    location: Mapped[WKBElement] = mapped_column(
        Geography(
            geometry_type="POINT",
            srid=4326,
            spatial_index=True,
        ),
        nullable=False,
    )
    raw_access: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    opening_hours: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    fee: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    operator: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    website: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    phone: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    email: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    wheelchair: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    access_type: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="unknown",
        server_default="unknown",
    )
    verification_priority: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="medium",
        server_default="medium",
    )
    verification_status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="pending",
        server_default="pending",
    )
    public_access_verified: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="unknown",
        server_default="unknown",
    )
    indoor_space_verified: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="unknown",
        server_default="unknown",
    )
    air_conditioning_verified: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="unknown",
        server_default="unknown",
    )
    emergency_access_verified: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="unknown",
        server_default="unknown",
    )
    last_verified: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    verification_source: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    verification_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )