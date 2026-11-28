"""Track completed incremental windows separately from observation timestamps."""

from alembic import op
import sqlalchemy as sa


revision = "613f09a21d45"
down_revision = "b7e9c2a14530"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "air_quality_sensors",
        sa.Column("synced_through", sa.DateTime(timezone=True)),
    )
    op.execute("""
        UPDATE air_quality_sensors AS sensor
        SET last_synced_at = NULL,
            last_measurement_at = (
                SELECT max(period_end)
                FROM air_quality_measurements
                WHERE sensor_id = sensor.id AND quality_status <> 'rejected'
            )
    """)


def downgrade() -> None:
    op.drop_column("air_quality_sensors", "synced_through")
