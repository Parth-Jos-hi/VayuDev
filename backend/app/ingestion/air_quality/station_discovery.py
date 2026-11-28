from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from app.clients.openaq import AirQualityProvider
from app.core.config import Settings, settings
from app.core.exceptions import InvalidProviderResponse
from app.schemas.air_quality import SensorIngestion, StationIngestion


@dataclass
class DiscoveryStats:
    locations_seen: int = 0
    stations_discovered: int = 0
    stations_inactive: int = 0
    stations_skipped_non_monitor: int = 0
    stations_skipped_outside_region: int = 0
    stations_skipped_invalid: int = 0
    stations_skipped_without_supported_sensors: int = 0
    duplicate_locations_skipped: int = 0
    sensors_seen: int = 0
    sensors_discovered: int = 0
    sensors_inactive: int = 0
    sensors_skipped_unsupported: int = 0
    sensors_rejected_invalid: int = 0


@dataclass
class DiscoveredStation:
    station: StationIngestion
    sensors: list[SensorIngestion] = field(default_factory=list)


@dataclass
class DiscoveryResult:
    stations: list[DiscoveredStation]
    stats: DiscoveryStats


class StationDiscoveryService:
    def __init__(
        self,
        provider: AirQualityProvider,
        config: Settings = settings,
    ):
        self.provider = provider
        self.config = config
        self.supported_pollutants = set(config.supported_pollutants)

    def discover(
        self,
        now: datetime | None = None,
        max_pages: int | None = None,
    ) -> DiscoveryResult:
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must include timezone information")
        now = now.astimezone(timezone.utc)

        bbox = ",".join(
            f"{coordinate:.4f}"
            for coordinate in (
                self.config.study_region_west,
                self.config.study_region_south,
                self.config.study_region_east,
                self.config.study_region_north,
            )
        )
        locations = self.provider.fetch_locations(
            bbox=bbox,
            max_pages=max_pages,
        )
        stats = DiscoveryStats(locations_seen=len(locations))
        stations: list[DiscoveredStation] = []
        seen_ids: set[str] = set()

        for location in locations:
            if not isinstance(location, dict):
                stats.stations_skipped_invalid += 1
                continue
            location_id = location.get("id")
            if (
                not isinstance(location_id, int)
                or isinstance(location_id, bool)
                or location_id <= 0
            ):
                stats.stations_skipped_invalid += 1
                continue

            external_id = str(location_id)
            if external_id in seen_ids:
                stats.duplicate_locations_skipped += 1
                continue
            seen_ids.add(external_id)

            if not isinstance(location.get("isMonitor"), bool):
                stats.stations_skipped_invalid += 1
                continue
            if not location["isMonitor"]:
                stats.stations_skipped_non_monitor += 1
                continue

            station_data = self._station_data(location)
            if station_data is None:
                stats.stations_skipped_invalid += 1
                continue

            try:
                station = StationIngestion.model_validate(station_data)
            except ValidationError:
                stats.stations_skipped_invalid += 1
                continue

            if not self._inside_region(station.latitude, station.longitude):
                stats.stations_skipped_outside_region += 1
                continue

            raw_sensors = self.provider.fetch_sensors(location_id)
            sensors = self._supported_sensors(
                raw_sensors,
                external_id,
                now,
                stats,
            )
            if not sensors:
                stats.stations_skipped_without_supported_sensors += 1
                continue

            station.is_active = (
                not station.is_mobile and any(sensor.is_active for sensor in sensors)
            )
            if not station.is_active:
                stats.stations_inactive += 1

            stations.append(DiscoveredStation(station=station, sensors=sensors))
            stats.stations_discovered += 1

        return DiscoveryResult(stations=stations, stats=stats)

    def _station_data(self, location: dict[str, Any]) -> dict[str, Any] | None:
        coordinates = location.get("coordinates")
        if not isinstance(coordinates, dict):
            return None

        country = location.get("country")
        provider = location.get("provider")
        if country is not None and not isinstance(country, dict):
            return None
        if provider is not None and not isinstance(provider, dict):
            return None
        if not isinstance(location.get("isMobile"), bool):
            return None

        return {
            "source": "openaq",
            "external_id": str(location["id"]),
            "name": location.get("name"),
            "latitude": coordinates.get("latitude"),
            "longitude": coordinates.get("longitude"),
            "country_code": country.get("code") if country else None,
            "locality": location.get("locality"),
            "provider_name": provider.get("name") if provider else None,
            "is_mobile": location["isMobile"],
        }

    def _inside_region(self, latitude: float, longitude: float) -> bool:
        return (
            self.config.study_region_south
            <= latitude
            <= self.config.study_region_north
            and self.config.study_region_west
            <= longitude
            <= self.config.study_region_east
        )

    def _supported_sensors(
        self,
        raw_sensors: list[dict[str, Any]],
        station_external_id: str,
        now: datetime,
        stats: DiscoveryStats,
    ) -> list[SensorIngestion]:
        if not isinstance(raw_sensors, list):
            raise InvalidProviderResponse(
                "OpenAQ sensors response must be a list"
            )

        sensors: list[SensorIngestion] = []
        for sensor_data in raw_sensors:
            stats.sensors_seen += 1
            if not isinstance(sensor_data, dict):
                stats.sensors_rejected_invalid += 1
                continue

            parameter = sensor_data.get("parameter")
            if not isinstance(parameter, dict):
                stats.sensors_rejected_invalid += 1
                continue

            pollutant = parameter.get("name")
            if not isinstance(pollutant, str):
                stats.sensors_rejected_invalid += 1
                continue
            pollutant = pollutant.strip().lower()
            if pollutant not in self.supported_pollutants:
                stats.sensors_skipped_unsupported += 1
                continue

            try:
                sensor_id = sensor_data.get("id")
                if (
                    not isinstance(sensor_id, int)
                    or isinstance(sensor_id, bool)
                    or sensor_id <= 0
                ):
                    raise ValueError("Sensor ID must be a positive integer")
                last_measurement_at = self._last_measurement(sensor_data)
                is_active = self._is_fresh(last_measurement_at, now)
                sensor = SensorIngestion.model_validate(
                    {
                        "source": "openaq",
                        "external_id": str(sensor_id),
                        "station_external_id": station_external_id,
                        "pollutant": pollutant,
                        "original_unit": parameter.get("units"),
                        "is_active": is_active,
                        "last_measurement_at": last_measurement_at,
                    }
                )
            except (ValidationError, ValueError):
                stats.sensors_rejected_invalid += 1
                continue

            sensors.append(sensor)
            stats.sensors_discovered += 1
            if not sensor.is_active:
                stats.sensors_inactive += 1

        return sensors

    @staticmethod
    def _last_measurement(sensor: dict[str, Any]) -> datetime | None:
        latest = sensor.get("datetimeLast")
        if latest is None:
            latest = sensor.get("latest")
            if isinstance(latest, dict):
                latest = latest.get("datetime")
        if isinstance(latest, dict):
            latest = latest.get("utc")
        if latest is None:
            return None
        if not isinstance(latest, str):
            raise ValueError("Sensor datetimeLast must be a timestamp")

        value = datetime.fromisoformat(latest.replace("Z", "+00:00"))
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Sensor datetimeLast must include timezone information")
        return value.astimezone(timezone.utc)

    def _is_fresh(self, last_measurement_at: datetime | None, now: datetime) -> bool:
        if last_measurement_at is None:
            return False
        age_seconds = (now - last_measurement_at).total_seconds()
        return 0 <= age_seconds <= self.config.air_quality_freshness_seconds
