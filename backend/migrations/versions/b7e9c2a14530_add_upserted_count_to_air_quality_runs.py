"""Add an upserted count to air-quality ingestion runs.

Revision ID: b7e9c2a14530
Revises: 0f4c2a7d8e91
Create Date: 2026-11-28 09:05:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7e9c2a14530"
down_revision: Union[str, Sequence[str], None] = "0f4c2a7d8e91"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "air_quality_ingestion_runs",
        sa.Column(
            "records_upserted",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("air_quality_ingestion_runs", "records_upserted")
