from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from typing import Any, Literal

from app.clients.openaq import AirQualityProvider
from app.core.config import Settings, settings
from app.db.repositories.air_quality import (
    AirQualityRepository,
    RepositoryWriteResult,
)
from app.ingestion.air_quality.normalizer import (
    MeasurementNormalizationError,
    MeasurementNormalizer,
)
from app.ingestion.air_quality.station_discovery import (
    DiscoveryStats,
    DiscoveredStation,
    StationDiscoveryService,
)
from app.ingestion.air_quality.validator import (
    AirQualityMeasurementValidator,
)
from app.schemas.air_quality import MeasurementIngestion, SensorIngestion


JobType = Literal["discovery", "backfill", "incremental"]


@dataclass
class AirQualityIngestionResult:
    job_type: JobType
    discovery_stats: DiscoveryStats
    stations_upserted: int = 0
    sensors_upserted: int = 0
    measurements_fetched: int = 0
    measurements_upserted: int = 0
    measurements_rejected: int = 0
    measurements_suspect: int = 0
    sensors_skipped: int = 0
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
    ) -> AirQualityIngestionResult:
        if job_type not in ("discovery", "backfill", "incremental"):
            raise ValueError("Unsupported air quality job type")
        now = self._utc_now(now)
        if self.session.in_transaction():
            raise RuntimeError(
                "Air quality sync requires a session without an active transaction"
            )

        discovery = self.discovery.discover(now=now)
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
            sensor_writes = self.repository.upsert_sensors(sensors, now)
        result.stations_upserted = station_writes.records_upserted
        result.sensors_upserted = sensor_writes.records_upserted

        if job_type == "discovery":
            return result

        sensor_pollutants = {
            sensor.external_id: sensor.pollutant
            for sensor in sensors
        }
        for item in discovery.stations:
            for sensor in item.sensors:
                window = self._measurement_window(job_type, sensor, now)
                if window is None:
                    result.sensors_skipped += 1
                    continue

                start, end = window
                raw_records = self.provider.fetch_hourly_measurements(
                    int(sensor.external_id),
                    datetime_from=start,
                    datetime_to=end,
                )
                result.measurements_fetched += len(raw_records)
                measurements = self._validated_measurements(
                    raw_records,
                    item,
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

        return result

    def _validated_measurements(
        self,
        raw_records: list[dict[str, Any]],
        station: DiscoveredStation,
        sensor_external_id: str,
        sensor_pollutants: dict[str, str],
        now: datetime,
        result: AirQualityIngestionResult,
    ) -> list[MeasurementIngestion]:
        measurements: list[MeasurementIngestion] = []
        coordinates = {
            "latitude": station.station.latitude,
            "longitude": station.station.longitude,
        }

        for record in raw_records:
            try:
                measurement = self.normalizer.normalize(
                    record,
                    sensor_external_id,
                    aggregation_type="hourly",
                )
            except MeasurementNormalizationError as error:
                result.reject_measurement((str(error),))
                continue

            validation = self.validator.validate(
                measurement,
                sensor_pollutants,
                coordinates=coordinates,
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

    def _measurement_window(
        self,
        job_type: JobType,
        sensor: SensorIngestion,
        now: datetime,
    ) -> tuple[datetime, datetime] | None:
        if job_type == "backfill":
            start = datetime.combine(
                self.config.air_quality_historical_start,
                time.min,
                tzinfo=timezone.utc,
            )
            end = min(
                datetime.combine(
                    self.config.air_quality_historical_end,
                    time.min,
                    tzinfo=timezone.utc,
                ),
                now,
            )
            if end <= start:
                raise ValueError("Historical measurement range is empty")
            return start, end

        if sensor.last_measurement_at is None:
            return None
        start = sensor.last_measurement_at - timedelta(
            seconds=self.config.incremental_overlap_seconds
        )
        if start >= now:
            return None
        return start, now

    @staticmethod
    def _utc_now(now: datetime | None) -> datetime:
        if now is None:
            return datetime.now(timezone.utc)
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must include timezone information")
        return now.astimezone(timezone.utc)