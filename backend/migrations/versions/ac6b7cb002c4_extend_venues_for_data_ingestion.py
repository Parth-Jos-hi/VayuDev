"""extend venues for data ingestion

Revision ID: ac6b7cb002c4
Revises: d8f9e6aec627
Create Date: 2026-11-26 16:10:40.577514

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ac6b7cb002c4'
down_revision: Union[str, Sequence[str], None] = 'd8f9e6aec627'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Extend venues table for data ingestion."""

    # ==========================================
    # SOURCE IDENTIFICATION
    # ==========================================

    op.add_column(
        "venues",
        sa.Column(
            "osm_id",
            sa.BigInteger(),
            nullable=True,
        ),
    )

    op.add_column(
        "venues",
        sa.Column(
            "osm_type",
            sa.Text(),
            nullable=True,
        ),
    )

    op.add_column(
        "venues",
        sa.Column(
            "source",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'unknown'"),
        ),
    )

    op.add_column(
        "venues",
        sa.Column(
            "last_synced_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # ==========================================
    # EXISTING COLUMN MODIFICATIONS
    # ==========================================

    op.alter_column(
        "venues",
        "name",
        existing_type=sa.Text(),
        existing_nullable=False,
        nullable=True,
    )

    op.alter_column(
        "venues",
        "access_type",
        existing_type=sa.Text(),
        existing_nullable=False,
        server_default=sa.text("'unknown'"),
    )

    op.alter_column(
        "venues",
        "verification_status",
        existing_type=sa.Text(),
        existing_nullable=False,
        server_default=sa.text("'pending'"),
    )

    # ==========================================
    # VENUE METADATA
    # ==========================================

    op.add_column(
        "venues",
        sa.Column("raw_access", sa.Text(), nullable=True),
    )

    op.add_column(
        "venues",
        sa.Column("opening_hours", sa.Text(), nullable=True),
    )

    op.add_column(
        "venues",
        sa.Column("fee", sa.Text(), nullable=True),
    )

    op.add_column(
        "venues",
        sa.Column("operator", sa.Text(), nullable=True),
    )

    op.add_column(
        "venues",
        sa.Column("website", sa.Text(), nullable=True),
    )

    op.add_column(
        "venues",
        sa.Column("phone", sa.Text(), nullable=True),
    )

    op.add_column(
        "venues",
        sa.Column("email", sa.Text(), nullable=True),
    )

    op.add_column(
        "venues",
        sa.Column("wheelchair", sa.Text(), nullable=True),
    )

    # ==========================================
    # VERIFICATION INFORMATION
    # ==========================================

    op.add_column(
        "venues",
        sa.Column(
            "verification_priority",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'medium'"),
        ),
    )

    op.add_column(
        "venues",
        sa.Column(
            "public_access_verified",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'unknown'"),
        ),
    )

    op.add_column(
        "venues",
        sa.Column(
            "indoor_space_verified",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'unknown'"),
        ),
    )

    op.add_column(
        "venues",
        sa.Column(
            "air_conditioning_verified",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'unknown'"),
        ),
    )

    op.add_column(
        "venues",
        sa.Column(
            "emergency_access_verified",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'unknown'"),
        ),
    )

    # ==========================================
    # VERIFICATION SUMMARY
    # ==========================================

    op.add_column(
        "venues",
        sa.Column(
            "last_verified",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    op.add_column(
        "venues",
        sa.Column(
            "verification_source",
            sa.Text(),
            nullable=True,
        ),
    )

    op.add_column(
        "venues",
        sa.Column(
            "verification_notes",
            sa.Text(),
            nullable=True,
        ),
    )

    # ==========================================
    # COMPOSITE UNIQUE CONSTRAINT
    # ==========================================

    op.create_unique_constraint(
        "uq_venues_osm_identity",
        "venues",
        ["osm_type", "osm_id"],
    )

    # ==========================================
    # OSM CHECK CONSTRAINTS
    # ==========================================

    op.create_check_constraint(
        "ck_venues_osm_type",
        "venues",
        "osm_type IN ('node', 'way', 'relation')",
    )

    op.create_check_constraint(
        "ck_venues_osm_id",
        "venues",
        "osm_id > 0",
    )

    op.create_check_constraint(
        "ck_venues_osm_identity_pair",
        "venues",
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
    )

    op.create_check_constraint(
        "ck_venues_osm_source",
        "venues",
        """
        source <> 'osm'
        OR
        (
            osm_id IS NOT NULL
            AND osm_type IS NOT NULL
        )
        """,
    )

    # ==========================================
    # CATEGORY AND ACCESS CONSTRAINTS
    # ==========================================

    op.create_check_constraint(
        "ck_venues_category",
        "venues",
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
    )

    op.create_check_constraint(
        "ck_venues_access_type",
        "venues",
        """
        access_type IN (
            'unknown',
            'restricted',
            'conditional',
            'explicitly_permitted'
        )
        """,
    )

    # ==========================================
    # VERIFICATION CONSTRAINTS
    # ==========================================

    op.create_check_constraint(
        "ck_venues_verification_priority",
        "venues",
        """
        verification_priority IN (
            'low',
            'medium',
            'high'
        )
        """,
    )

    op.create_check_constraint(
        "ck_venues_verification_status",
        "venues",
        """
        verification_status IN (
            'pending',
            'verified',
            'rejected'
        )
        """,
    )

    op.create_check_constraint(
        "ck_venues_public_access_verified",
        "venues",
        """
        public_access_verified IN (
            'yes', 'no', 'unknown'
        )
        """,
    )

    op.create_check_constraint(
        "ck_venues_indoor_space_verified",
        "venues",
        """
        indoor_space_verified IN (
            'yes', 'no', 'unknown'
        )
        """,
    )

    op.create_check_constraint(
        "ck_venues_air_conditioning_verified",
        "venues",
        """
        air_conditioning_verified IN (
            'yes', 'no', 'unknown'
        )
        """,
    )

    op.create_check_constraint(
        "ck_venues_emergency_access_verified",
        "venues",
        """
        emergency_access_verified IN (
            'yes', 'no', 'unknown'
        )
        """,
    )


def downgrade() -> None:
    """Restore the original venues table structure."""

    # ==========================================
    # DOWNGRADE SAFETY CHECK
    # ==========================================

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM venues
                WHERE name IS NULL
            ) THEN
                RAISE EXCEPTION
                    'Cannot downgrade: unnamed venues exist.';
            END IF;
        END;
        $$;
        """
    )

    # ==========================================
    # REMOVE CHECK CONSTRAINTS
    # ==========================================

    check_constraints = [
        "ck_venues_emergency_access_verified",
        "ck_venues_air_conditioning_verified",
        "ck_venues_indoor_space_verified",
        "ck_venues_public_access_verified",
        "ck_venues_verification_status",
        "ck_venues_verification_priority",
        "ck_venues_access_type",
        "ck_venues_category",
        "ck_venues_osm_source",
        "ck_venues_osm_identity_pair",
        "ck_venues_osm_id",
        "ck_venues_osm_type",
    ]

    for constraint_name in check_constraints:
        op.drop_constraint(
            constraint_name,
            "venues",
            type_="check",
        )

    # ==========================================
    # REMOVE COMPOSITE UNIQUE CONSTRAINT
    # ==========================================

    op.drop_constraint(
        "uq_venues_osm_identity",
        "venues",
        type_="unique",
    )

    # ==========================================
    # RESTORE ORIGINAL COLUMN PROPERTIES
    # ==========================================

    op.alter_column(
        "venues",
        "name",
        existing_type=sa.Text(),
        existing_nullable=True,
        nullable=False,
    )

    op.alter_column(
        "venues",
        "access_type",
        existing_type=sa.Text(),
        existing_nullable=False,
        server_default=None,
    )

    op.alter_column(
        "venues",
        "verification_status",
        existing_type=sa.Text(),
        existing_nullable=False,
        server_default=None,
    )

    # ==========================================
    # REMOVE NEW COLUMNS
    # ==========================================

    new_columns = [
        "verification_notes",
        "verification_source",
        "last_verified",
        "emergency_access_verified",
        "air_conditioning_verified",
        "indoor_space_verified",
        "public_access_verified",
        "verification_priority",
        "wheelchair",
        "email",
        "phone",
        "website",
        "operator",
        "fee",
        "opening_hours",
        "raw_access",
        "last_synced_at",
        "source",
        "osm_type",
        "osm_id",
    ]

    for column_name in new_columns:
        op.drop_column(
            "venues",
            column_name,
        )
