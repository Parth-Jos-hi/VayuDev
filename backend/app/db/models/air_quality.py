from datetime import datetime
from uuid import UUID, uuid4

from geoalchemy2 import Geography
from geoalchemy2.elements import WKBElement
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    UUID as SQLAlchemyUUID,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AirQualityStation(Base):
    __tablename__ = "air_quality_stations"

    __table_args__ = (
        UniqueConstraint(
            "source",
            "external_id",
            name="uq_air_quality_stations_source_external_id",
        ),
        CheckConstraint(
            "latitude >= -90 AND latitude <= 90",
            name="ck_air_quality_stations_latitude",
        ),
        CheckConstraint(
            "longitude >= -180 AND longitude <= 180",
            name="ck_air_quality_stations_longitude",
        ),
        CheckConstraint(
            "source IN ('openaq', 'cpcb')",
            name="ck_air_quality_stations_source",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        SQLAlchemyUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    location: Mapped[WKBElement] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=True),
        nullable=False,
    )
    country_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    locality: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_mobile: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    sensors: Mapped[list["AirQualitySensor"]] = relationship(
        back_populates="station",
        cascade="all, delete-orphan",
    )


class AirQualitySensor(Base):
    __tablename__ = "air_quality_sensors"

    __table_args__ = (
        UniqueConstraint(
            "source",
            "external_id",
            name="uq_air_quality_sensors_source_external_id",
        ),
        CheckConstraint(
            "source IN ('openaq', 'cpcb')",
            name="ck_air_quality_sensors_source",
        ),
        CheckConstraint(
            "pollutant IN ('pm25', 'pm10', 'no2', 'so2', 'co', 'o3', 'nh3', 'pb')",
            name="ck_air_quality_sensors_pollutant",
        ),
        Index("idx_air_quality_sensors_station_id", "station_id"),
        Index("idx_air_quality_sensors_pollutant", "pollutant"),
    )

    id: Mapped[UUID] = mapped_column(
        SQLAlchemyUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    station_id: Mapped[UUID] = mapped_column(
        SQLAlchemyUUID(as_uuid=True),
        ForeignKey("air_quality_stations.id", ondelete="CASCADE"),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    pollutant: Mapped[str] = mapped_column(Text, nullable=False)
    original_unit: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_measurement_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    station: Mapped["AirQualityStation"] = relationship(back_populates="sensors")
    measurements: Mapped[list["AirQualityMeasurement"]] = relationship(
        back_populates="sensor",
        cascade="all, delete-orphan",
    )


class AirQualityMeasurement(Base):
    __tablename__ = "air_quality_measurements"

    __table_args__ = (
        UniqueConstraint(
            "sensor_id",
            "period_start",
            "period_end",
            "aggregation_type",
            name="uq_air_quality_measurements_observation",
        ),
        CheckConstraint(
            "period_end >= period_start",
            name="ck_air_quality_measurements_period",
        ),
        CheckConstraint(
            "aggregation_type IN ('raw', 'hourly', 'daily')",
            name="ck_air_quality_measurements_aggregation",
        ),
        CheckConstraint(
            "quality_status IN ('valid', 'suspect', 'rejected')",
            name="ck_air_quality_measurements_quality",
        ),
        Index(
            "idx_air_quality_measurements_sensor_period",
            "sensor_id",
            "period_start",
        ),
        Index(
            "idx_air_quality_measurements_period",
            "period_start",
            "period_end",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        SQLAlchemyUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    sensor_id: Mapped[UUID] = mapped_column(
        SQLAlchemyUUID(as_uuid=True),
        ForeignKey("air_quality_sensors.id", ondelete="CASCADE"),
        nullable=False,
    )
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(Text, nullable=False)
    original_value: Mapped[float] = mapped_column(Float, nullable=False)
    original_unit: Mapped[str] = mapped_column(Text, nullable=False)
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    aggregation_type: Mapped[str] = mapped_column(Text, nullable=False)
    quality_status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="valid",
    )
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    sensor: Mapped["AirQualitySensor"] = relationship(back_populates="measurements")


class AirQualityIngestionRun(Base):
    __tablename__ = "air_quality_ingestion_runs"

    __table_args__ = (
        CheckConstraint(
            "source IN ('openaq', 'cpcb')",
            name="ck_air_quality_ingestion_runs_source",
        ),
        CheckConstraint(
            "job_type IN ('discovery', 'backfill', 'incremental')",
            name="ck_air_quality_ingestion_runs_job_type",
        ),
        CheckConstraint(
            "status IN ('running', 'success', 'partial', 'failed')",
            name="ck_air_quality_ingestion_runs_status",
        ),
        CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at",
            name="ck_air_quality_ingestion_runs_completed",
        ),
        Index(
            "idx_air_quality_ingestion_runs_source_started",
            "source",
            "started_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        SQLAlchemyUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    job_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="running",
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    records_fetched: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    records_upserted: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    records_inserted: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    records_updated: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    records_skipped: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    records_rejected: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)