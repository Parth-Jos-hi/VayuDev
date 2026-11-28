from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from typing import Any, Literal

from sqlalchemy.exc import SQLAlchemyError

from app.clients.openaq import AirQualityProvider
from app.core.config import Settings, settings
from app.core.exceptions import (
    AuthenticationError,
    ExternalServiceError,
    RateLimitError,
    RequestBudgetExceeded,
)
from app.db.repositories.air_quality import (
    AirQualityRepository,
    IncrementalSensor,
    RepositoryWriteResult,
)
from app.ingestion.air_quality.incremental_loader import incremental_windows
from app.ingestion.air_quality.normalizer import (
    MeasurementNormalizationError,
    MeasurementNormalizer,
)
from app.ingestion.air_quality.station_discovery import (
    DiscoveryStats,
    StationDiscoveryService,
)
from app.ingestion.air_quality.validator import (
    AirQualityMeasurementValidator,
)
from app.schemas.air_quality import MeasurementIngestion


JobType = Literal["discovery", "backfill", "incremental"]


@dataclass
class AirQualityIngestionResult:
    job_type: JobType
    discovery_stats: DiscoveryStats
    stations_upserted: int = 0
    sensors_upserted: int = 0
    measurements_fetched: int = 0
    measurements_upserted: int = 0
    measurements_skipped: int = 0
    measurements_rejected: int = 0
    measurements_suspect: int = 0
    sensors_skipped: int = 0
    sensors_selected: int = 0
    sensors_stale: int = 0
    sensors_missing: int = 0
    windows_completed: int = 0
    failed_windows: dict[str, str] = field(default_factory=dict)
    rejection_reasons: dict[str, int] = field(default_factory=dict)

    def reject_measurement(self, reasons: tuple[str, ...]) -> None:
        self.measurements_rejected += 1
        for reason in reasons:
            self.rejection_reasons[reason] = (
                self.rejection_reasons.get(reason, 0) + 1
            )


class AirQualityIngestionService:
    def __init__(
        self,
        provider: AirQualityProvider,
        repository: AirQualityRepository,
        config: Settings = settings,
    ):
        self.provider = provider
        self.repository = repository
        self.session = repository.session
        self.config = config
        self.discovery = StationDiscoveryService(provider, config)
        self.normalizer = MeasurementNormalizer()
        self.validator = AirQualityMeasurementValidator(config)

    def sync(
        self,
        job_type: JobType,
        now: datetime | None = None,
        station_limit: int | None = None,
    ) -> AirQualityIngestionResult:
        if job_type not in ("discovery", "backfill", "incremental"):
            raise ValueError("Unsupported air quality job type")
        now = self._utc_now(now)
        if self.session.in_transaction():
            raise RuntimeError(
                "Air quality sync requires a session without an active transaction"
            )

        if job_type == "incremental":
            return self._sync_incremental(now)

        discovery = self.discovery.discover(now=now)
        selected = discovery.stations
        if job_type == "backfill" and station_limit is not None:
            selected = [item for item in selected if not item.station.is_mobile][:station_limit]
        result = AirQualityIngestionResult(
            job_type=job_type,
            discovery_stats=discovery.stats,
        )
        stations = [item.station for item in discovery.stations]
        sensors = [
            sensor
            for item in discovery.stations
            for sensor in item.sensors
        ]

        with self.session.begin():
            station_writes = self.repository.upsert_stations(stations, now)
            sensor_writes = self.repository.upsert_sensors(sensors)
        result.stations_upserted = station_writes.records_upserted
        result.sensors_upserted = sensor_writes.records_upserted

        if job_type == "discovery":
            return result

        sensor_pollutants = {
            sensor.external_id: sensor.pollutant
            for sensor in sensors
        }
        for item in selected:
            for sensor in item.sensors:
                start, end = self._historical_window(now)
                raw_records = self.provider.fetch_hourly_measurements(
                    int(sensor.external_id),
                    datetime_from=start,
                    datetime_to=end,
                )
                result.measurements_fetched += len(raw_records)
                measurements = self._validated_measurements(
                    raw_records,
                    (item.station.latitude, item.station.longitude),
                    sensor.external_id,
                    sensor_pollutants,
                    now,
                    result,
                )
                if not measurements:
                    continue

                with self.session.begin():
                    writes: RepositoryWriteResult = (
                        self.repository.upsert_measurements(
                            measurements,
                            source=sensor.source,
                        )
                    )
                result.measurements_upserted += writes.records_upserted
                result.measurements_skipped += len(measurements) - writes.records_upserted

        return result

    def _sync_incremental(self, now: datetime) -> AirQualityIngestionResult:
        result = AirQualityIngestionResult("incremental", DiscoveryStats())
        with self.session.begin():
            sensors = self.repository.incremental_sensors(self.config)
        result.sensors_selected = len(sensors)
        for sensor in sensors:
            latest = sensor.last_measurement_at
            for start, end in incremental_windows(sensor.synced_through, now, self.config):
                try:
                    written_at = self._sync_window(sensor, start, end, now, result)
                    if written_at is not None:
                        latest = max(latest, written_at) if latest is not None else written_at
                except (ExternalServiceError, SQLAlchemyError) as error:
                    result.failed_windows[f"{sensor.external_id}@{start.isoformat()}"] = (
                        type(error).__name__
                    )
                    if isinstance(error, (AuthenticationError, RateLimitError, RequestBudgetExceeded)):
                        self._count_freshness(latest, now, result)
                        return result
                    break
            self._count_freshness(latest, now, result)
        return result

    def _sync_window(
        self,
        sensor: IncrementalSensor,
        start: datetime,
        end: datetime,
        now: datetime,
        result: AirQualityIngestionResult,
    ) -> datetime | None:
        records = self.provider.fetch_hourly_measurements(
            int(sensor.external_id),
            datetime_from=start - timedelta(hours=1),
            datetime_to=end,
        )
        result.measurements_fetched += len(records)
        measurements = self._validated_measurements(
            records, (sensor.latitude, sensor.longitude),
            sensor.external_id, {sensor.external_id: sensor.pollutant},
            now, result, window=(start, end),
        )
        with self.session.begin():
            writes = self.repository.upsert_measurements(measurements, source="openaq")
            self.repository.complete_sensor_window(sensor.id, end, now)
        result.measurements_upserted += writes.records_upserted
        result.measurements_skipped += len(measurements) - writes.records_upserted
        result.windows_completed += 1
        return max((item.period_end for item in measurements), default=None)

    def _count_freshness(
        self, latest: datetime | None, now: datetime, result: AirQualityIngestionResult
    ) -> None:
        if latest is None:
            result.sensors_missing += 1
        elif now - latest > timedelta(seconds=self.config.air_quality_freshness_seconds):
            result.sensors_stale += 1

    def _validated_measurements(
        self,
        raw_records: list[dict[str, Any]],
        coordinates: tuple[float, float],
        sensor_external_id: str,
        sensor_pollutants: Mapping[str, str],
        now: datetime,
        result: AirQualityIngestionResult,
        window: tuple[datetime, datetime] | None = None,
    ) -> list[MeasurementIngestion]:
        measurements: list[MeasurementIngestion] = []
        latitude, longitude = coordinates
        location = {"latitude": latitude, "longitude": longitude}

        for record in raw_records:
            try:
                measurement = self.normalizer.normalize(
                    record,
                    sensor_external_id,
                    aggregation_type="hourly",
                    expected_pollutant=sensor_pollutants[sensor_external_id],
                )
            except MeasurementNormalizationError as error:
                result.reject_measurement((str(error),))
                continue

            if window is not None and not window[0] < measurement.period_end <= window[1]:
                result.measurements_skipped += 1
                continue

            validation = self.validator.validate(
                measurement,
                sensor_pollutants,
                coordinates=location,
                now=now,
            )
            if not validation.accepted:
                result.reject_measurement(validation.reasons)
                continue
            if validation.measurement is None:
                raise RuntimeError(
                    "Accepted measurement is missing validated data"
                )

            if validation.quality_status == "suspect":
                result.measurements_suspect += 1
            measurements.append(validation.measurement)

        return measurements

    def _historical_window(self, now: datetime) -> tuple[datetime, datetime]:
        start = datetime.combine(self.config.air_quality_historical_start, time.min, timezone.utc)
        end = min(
            datetime.combine(self.config.air_quality_historical_end, time.min, timezone.utc),
            now,
        )
        if end <= start:
            raise ValueError("Historical measurement range is empty")
        return start, end

    @staticmethod
    def _utc_now(now: datetime | None) -> datetime:
        if now is None:
            return datetime.now(timezone.utc)
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must include timezone information")
        return now.astimezone(timezone.utc)
