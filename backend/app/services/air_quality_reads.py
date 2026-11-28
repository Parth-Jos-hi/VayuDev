from datetime import datetime, timezone
from uuid import UUID

from app.core.config import settings
from app.db.models.air_quality import AirQualityStation
from app.db.repositories.air_quality_reads import AirQualityReads
from app.schemas.air_quality import AirQualityPage, FreshnessCoverageResponse


def require_station(repository: AirQualityReads, station_id: UUID) -> AirQualityStation:
    station = repository.station(station_id)
    if station is None:
        raise LookupError("Air quality station not found")
    return station


def station_coverage(
    repository: AirQualityReads, page: AirQualityPage, now: datetime | None = None
) -> list[FreshnessCoverageResponse]:
    now = now or datetime.now(timezone.utc)
    coverage = []
    for station_id, first, latest, count in repository.coverage(page, now):
        age = (now - latest).total_seconds() if latest is not None else None
        coverage.append(FreshnessCoverageResponse(
            station_id=station_id,
            first_measurement_at=first,
            latest_measurement_at=latest,
            age_seconds=int(age) if age is not None else None,
            is_fresh=age is not None and age <= settings.air_quality_freshness_seconds,
            measurement_count=count,
        ))
    return coverage
