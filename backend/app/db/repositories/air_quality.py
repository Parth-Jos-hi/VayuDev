from collections.abc import Hashable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import batched
from typing import Callable, Literal, TypeVar
from uuid import UUID

from geoalchemy2.elements import WKTElement
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import MAX_INGESTION_BATCH_SIZE, settings
from app.db.models.air_quality import (
    AirQualityIngestionRun,
    AirQualityMeasurement,
    AirQualitySensor,
    AirQualityStation,
)
from app.schemas.air_quality import (
    DataSource,
    MeasurementIngestion,
    SensorIngestion,
    StationIngestion,
)


CompletedRunStatus = Literal["success", "partial", "failed"]
IngestionJobType = Literal["discovery", "backfill", "incremental"]
Record = TypeVar("Record")


@dataclass
class RepositoryWriteResult:
    records_received: int = 0
    records_upserted: int = 0
    batches_executed: int = 0


def _deduplicate_batch(
    records: tuple[Record, ...],
    identity: Callable[[Record], Hashable],
) -> tuple[Record, ...]:
    unique_records = {}
    for record in records:
        unique_records[identity(record)] = record
    return tuple(unique_records.values())


def _utc_timestamp(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if not isinstance(value, datetime):
        raise ValueError("Timestamp must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamp must include timezone information")
    return value.astimezone(timezone.utc)


class AirQualityRepository:
    def __init__(
        self,
        session: Session,
        batch_size: int | None = None,
    ):
        self.session = session
        self.batch_size = (
            settings.ingestion_batch_size if batch_size is None else batch_size
        )
        self._validate_batch_size(self.batch_size)

    def upsert_stations(
        self,
        records: Iterable[StationIngestion],
        synced_at: datetime | None = None,
    ) -> RepositoryWriteResult:
        self._require_transaction()
        synced_at = _utc_timestamp(synced_at)
        result = RepositoryWriteResult()
        table = AirQualityStation.__table__

        for batch in batched(records, self.batch_size):
            result.records_received += len(batch)
            unique = _deduplicate_batch(
                batch,
                lambda record: (record.source, record.external_id),
            )
            rows = []
            for record in unique:
                row = record.model_dump()
                latitude = row["latitude"]
                longitude = row["longitude"]
                row["location"] = WKTElement(
                    f"POINT({longitude} {latitude})",
                    srid=4326,
                )
                row["last_synced_at"] = synced_at
                rows.append(row)

            statement = insert(table).values(rows)
            incoming = statement.excluded
            updates = {
                "name": func.coalesce(incoming.name, table.c.name),
                "latitude": incoming.latitude,
                "longitude": incoming.longitude,
                "location": incoming.location,
                "country_code": func.coalesce(
                    incoming.country_code,
                    table.c.country_code,
                ),
                "locality": func.coalesce(incoming.locality, table.c.locality),
                "provider_name": func.coalesce(
                    incoming.provider_name,
                    table.c.provider_name,
                ),
                "is_mobile": incoming.is_mobile,
                "is_active": incoming.is_active,
                "last_synced_at": incoming.last_synced_at,
                "updated_at": func.now(),
            }
            statement = statement.on_conflict_do_update(
                constraint="uq_air_quality_stations_source_external_id",
                set_=updates,
            ).returning(table.c.id)
            result.records_upserted += len(
                self.session.execute(statement).scalars().all()
            )
            result.batches_executed += 1

        return result

    def upsert_sensors(
        self,
        records: Iterable[SensorIngestion],
        synced_at: datetime | None = None,
    ) -> RepositoryWriteResult:
        self._require_transaction()
        synced_at = _utc_timestamp(synced_at)
        result = RepositoryWriteResult()
        table = AirQualitySensor.__table__

        for batch in batched(records, self.batch_size):
            result.records_received += len(batch)
            unique = _deduplicate_batch(
                batch,
                lambda record: (record.source, record.external_id),
            )
            station_ids = self._station_ids(unique)
            rows = [
                {
                    "station_id": station_ids[
                        (record.source, record.station_external_id)
                    ],
                    "source": record.source,
                    "external_id": record.external_id,
                    "pollutant": record.pollutant,
                    "original_unit": record.original_unit,
                    "is_active": record.is_active,
                    "last_measurement_at": record.last_measurement_at,
                    "last_synced_at": synced_at,
                }
                for record in unique
            ]

            statement = insert(table).values(rows)
            incoming = statement.excluded
            statement = statement.on_conflict_do_update(
                constraint="uq_air_quality_sensors_source_external_id",
                set_={
                    "station_id": incoming.station_id,
                    "pollutant": incoming.pollutant,
                    "original_unit": incoming.original_unit,
                    "is_active": incoming.is_active,
                    "last_measurement_at": func.coalesce(
                        incoming.last_measurement_at,
                        table.c.last_measurement_at,
                    ),
                    "last_synced_at": incoming.last_synced_at,
                    "updated_at": func.now(),
                },
            ).returning(table.c.id)
            result.records_upserted += len(
                self.session.execute(statement).scalars().all()
            )
            result.batches_executed += 1

        return result

    def upsert_measurements(
        self,
        records: Iterable[MeasurementIngestion],
        source: DataSource,
    ) -> RepositoryWriteResult:
        self._require_transaction()
        self._validate_source(source)

        result = RepositoryWriteResult()
        table = AirQualityMeasurement.__table__

        for batch in batched(records, self.batch_size):
            result.records_received += len(batch)
            unique = _deduplicate_batch(
                batch,
                lambda record: (
                    record.sensor_external_id,
                    record.period_start,
                    record.period_end,
                    record.aggregation_type,
                ),
            )
            sensor_ids = self._sensor_ids(
                source,
                {record.sensor_external_id for record in unique},
            )
            rows = [
                {
                    "sensor_id": sensor_ids[record.sensor_external_id],
                    "value": record.value,
                    "unit": record.unit,
                    "original_value": record.original_value,
                    "original_unit": record.original_unit,
                    "period_start": record.period_start,
                    "period_end": record.period_end,
                    "aggregation_type": record.aggregation_type,
                    "quality_status": record.quality_status,
                }
                for record in unique
            ]

            statement = insert(table).values(rows)
            incoming = statement.excluded
            statement = statement.on_conflict_do_update(
                constraint="uq_air_quality_measurements_observation",
                set_={
                    "value": incoming.value,
                    "unit": incoming.unit,
                    "original_value": incoming.original_value,
                    "original_unit": incoming.original_unit,
                    "quality_status": incoming.quality_status,
                    "ingested_at": func.now(),
                },
            ).returning(table.c.id)
            result.records_upserted += len(
                self.session.execute(statement).scalars().all()
            )
            result.batches_executed += 1

        return result

    def get_sensor_pollutants(self, source: DataSource) -> dict[str, str]:
        self._validate_source(source)
        rows = self.session.execute(
            select(AirQualitySensor.external_id, AirQualitySensor.pollutant).where(
                AirQualitySensor.source == source
            )
        ).all()
        return {external_id: pollutant for external_id, pollutant in rows}

    def start_ingestion_run(
        self,
        source: DataSource,
        job_type: IngestionJobType,
        started_at: datetime | None = None,
    ) -> AirQualityIngestionRun:
        self._require_transaction()
        self._validate_source(source)
        if job_type not in ("discovery", "backfill", "incremental"):
            raise ValueError("Unsupported ingestion job type")
        run = AirQualityIngestionRun(
            source=source,
            job_type=job_type,
            status="running",
            started_at=_utc_timestamp(started_at),
        )
        self.session.add(run)
        self.session.flush()
        return run

    def finish_ingestion_run(
        self,
        run_id: UUID,
        status: CompletedRunStatus,
        completed_at: datetime | None = None,
        counts: Mapping[str, int] | None = None,
        error_message: str | None = None,
    ) -> AirQualityIngestionRun:
        self._require_transaction()
        if status not in ("success", "partial", "failed"):
            raise ValueError("A completed run must have a final status")

        run = self.session.get(AirQualityIngestionRun, run_id)
        if run is None:
            raise LookupError(f"Ingestion run not found: {run_id}")
        if run.status != "running":
            raise ValueError("Only a running ingestion run can be completed")

        completed_at = _utc_timestamp(completed_at)
        if completed_at < _utc_timestamp(run.started_at):
            raise ValueError("Completion time cannot precede the start time")

        allowed_counts = {
            "records_fetched",
            "records_inserted",
            "records_updated",
            "records_skipped",
            "records_rejected",
        }
        if counts is None:
            counts = {}
        elif not isinstance(counts, Mapping):
            raise TypeError("Ingestion run counts must be a mapping")
        unknown_counts = set(counts) - allowed_counts
        if unknown_counts:
            raise ValueError(
                f"Unknown ingestion run counts: {', '.join(sorted(unknown_counts))}"
            )
        for name, count in counts.items():
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
            setattr(run, name, count)

        run.status = status
        run.completed_at = completed_at
        run.error_message = error_message
        self.session.flush()
        return run

    @staticmethod
    def _validate_source(source: str) -> None:
        if source not in ("openaq", "cpcb"):
            raise ValueError("Unsupported air quality data source")

    def _station_ids(
        self,
        sensors: tuple[SensorIngestion, ...],
    ) -> dict[tuple[str, str], UUID]:
        sources = {sensor.source for sensor in sensors}
        external_ids = {sensor.station_external_id for sensor in sensors}
        rows = self.session.execute(
            select(
                AirQualityStation.id,
                AirQualityStation.source,
                AirQualityStation.external_id,
            ).where(
                AirQualityStation.source.in_(sources),
                AirQualityStation.external_id.in_(external_ids),
            )
        ).all()
        station_ids = {
            (source, external_id): station_id
            for station_id, source, external_id in rows
        }
        missing = {
            (sensor.source, sensor.station_external_id)
            for sensor in sensors
        } - station_ids.keys()
        if missing:
            source, external_id = sorted(missing)[0]
            raise ValueError(
                f"Station not found for sensor: {source}/{external_id}"
            )
        return station_ids

    def _sensor_ids(
        self,
        source: DataSource,
        external_ids: set[str],
    ) -> dict[str, UUID]:
        rows = self.session.execute(
            select(AirQualitySensor.id, AirQualitySensor.external_id).where(
                AirQualitySensor.source == source,
                AirQualitySensor.external_id.in_(external_ids),
            )
        ).all()
        sensor_ids = {
            external_id: sensor_id
            for sensor_id, external_id in rows
        }
        missing = external_ids - sensor_ids.keys()
        if missing:
            raise ValueError(
                f"Unknown sensors for {source}: {', '.join(sorted(missing))}"
            )
        return sensor_ids

    def _require_transaction(self) -> None:
        if not self.session.in_transaction():
            raise RuntimeError(
                "Air quality repository writes require an active transaction"
            )

    @staticmethod
    def _validate_batch_size(batch_size: int) -> None:
        if (
            isinstance(batch_size, bool)
            or not isinstance(batch_size, int)
            or not 1 <= batch_size <= MAX_INGESTION_BATCH_SIZE
        ):
            raise ValueError(
                "Batch size must be an integer between 1 and "
                f"{MAX_INGESTION_BATCH_SIZE}"
            )
