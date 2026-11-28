"""create air quality tables

Revision ID: 0f4c2a7d8e91
Revises: ac6b7cb002c4
Create Date: 2026-11-28 07:40:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geography


revision: str = "0f4c2a7d8e91"
down_revision: Union[str, Sequence[str], None] = "ac6b7cb002c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_geospatial_table(
        "air_quality_stations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column(
            "location",
            Geography(
                geometry_type="POINT",
                srid=4326,
                spatial_index=False,
                name="geography",
                nullable=False,
            ),
            nullable=False,
        ),
        sa.Column("country_code", sa.Text(), nullable=True),
        sa.Column("locality", sa.Text(), nullable=True),
        sa.Column("provider_name", sa.Text(), nullable=True),
        sa.Column("is_mobile", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "source",
            "external_id",
            name="uq_air_quality_stations_source_external_id",
        ),
        sa.CheckConstraint(
            "latitude >= -90 AND latitude <= 90",
            name="ck_air_quality_stations_latitude",
        ),
        sa.CheckConstraint(
            "longitude >= -180 AND longitude <= 180",
            name="ck_air_quality_stations_longitude",
        ),
        sa.CheckConstraint(
            "source IN ('openaq', 'cpcb')",
            name="ck_air_quality_stations_source",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_geospatial_index(
        "idx_air_quality_stations_location",
        "air_quality_stations",
        ["location"],
        unique=False,
        postgresql_using="gist",
        postgresql_ops={},
    )

    op.create_table(
        "air_quality_sensors",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("station_id", sa.UUID(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("pollutant", sa.Text(), nullable=False),
        sa.Column("original_unit", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_measurement_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["station_id"],
            ["air_quality_stations.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "source",
            "external_id",
            name="uq_air_quality_sensors_source_external_id",
        ),
        sa.CheckConstraint(
            "source IN ('openaq', 'cpcb')",
            name="ck_air_quality_sensors_source",
        ),
        sa.CheckConstraint(
            "pollutant IN ('pm25', 'pm10', 'no2', 'so2', 'co', 'o3', 'nh3', 'pb')",
            name="ck_air_quality_sensors_pollutant",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_air_quality_sensors_station_id",
        "air_quality_sensors",
        ["station_id"],
    )
    op.create_index(
        "idx_air_quality_sensors_pollutant",
        "air_quality_sensors",
        ["pollutant"],
    )

    op.create_table(
        "air_quality_measurements",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("sensor_id", sa.UUID(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.Text(), nullable=False),
        sa.Column("original_value", sa.Float(), nullable=False),
        sa.Column("original_unit", sa.Text(), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("aggregation_type", sa.Text(), nullable=False),
        sa.Column("quality_status", sa.Text(), nullable=False, server_default="valid"),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["sensor_id"],
            ["air_quality_sensors.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "sensor_id",
            "period_start",
            "period_end",
            "aggregation_type",
            name="uq_air_quality_measurements_observation",
        ),
        sa.CheckConstraint(
            "period_end >= period_start",
            name="ck_air_quality_measurements_period",
        ),
        sa.CheckConstraint(
            "aggregation_type IN ('raw', 'hourly', 'daily')",
            name="ck_air_quality_measurements_aggregation",
        ),
        sa.CheckConstraint(
            "quality_status IN ('valid', 'suspect', 'rejected')",
            name="ck_air_quality_measurements_quality",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_air_quality_measurements_sensor_period",
        "air_quality_measurements",
        ["sensor_id", "period_start"],
    )
    op.create_index(
        "idx_air_quality_measurements_period",
        "air_quality_measurements",
        ["period_start", "period_end"],
    )

    op.create_table(
        "air_quality_ingestion_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("job_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="running"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("records_fetched", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_inserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_rejected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "source IN ('openaq', 'cpcb')",
            name="ck_air_quality_ingestion_runs_source",
        ),
        sa.CheckConstraint(
            "job_type IN ('discovery', 'backfill', 'incremental')",
            name="ck_air_quality_ingestion_runs_job_type",
        ),
        sa.CheckConstraint(
            "status IN ('running', 'success', 'partial', 'failed')",
            name="ck_air_quality_ingestion_runs_status",
        ),
        sa.CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at",
            name="ck_air_quality_ingestion_runs_completed",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_air_quality_ingestion_runs_source_started",
        "air_quality_ingestion_runs",
        ["source", "started_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_air_quality_ingestion_runs_source_started",
        table_name="air_quality_ingestion_runs",
    )
    op.drop_table("air_quality_ingestion_runs")
    op.drop_index(
        "idx_air_quality_measurements_period",
        table_name="air_quality_measurements",
    )
    op.drop_index(
        "idx_air_quality_measurements_sensor_period",
        table_name="air_quality_measurements",
    )
    op.drop_table("air_quality_measurements")
    op.drop_index(
        "idx_air_quality_sensors_pollutant",
        table_name="air_quality_sensors",
    )
    op.drop_index(
        "idx_air_quality_sensors_station_id",
        table_name="air_quality_sensors",
    )
    op.drop_table("air_quality_sensors")
    op.drop_geospatial_index(
        "idx_air_quality_stations_location",
        table_name="air_quality_stations",
        postgresql_using="gist",
        column_name="location",
    )
    op.drop_geospatial_table("air_quality_stations")
