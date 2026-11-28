from datetime import datetime, time, timedelta, timezone

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models.air_quality import (
    AirQualityIngestionRun as Run,
    AirQualityMeasurement as Measurement,
    AirQualitySensor as Sensor,
    AirQualityStation as Station,
)
from app.db.repositories.air_quality_reads import AirQualityReads
from app.schemas.air_quality import AirQualityPage
from app.services.air_quality_reads import station_coverage


def build_report(session: Session, config: Settings, page: AirQualityPage) -> dict:
    now = datetime.now(timezone.utc)
    start = datetime.combine(config.air_quality_historical_start, time.min, timezone.utc)
    end = min(
        datetime.combine(config.air_quality_historical_end, time.min, timezone.utc),
        now.replace(minute=0, second=0, microsecond=0),
    )
    expected = max(0, (end - start) // timedelta(hours=1))
    hourly = Sensor.measurements.and_(
        Measurement.aggregation_type == "hourly",
        Measurement.quality_status != "rejected",
        Measurement.period_start >= start,
        Measurement.period_end <= end,
    )
    observed = func.count(distinct(Measurement.period_start))
    gaps = session.execute(
        select(Sensor.id, Sensor.station_id, Sensor.pollutant, observed.label("observed_hours"))
        .outerjoin(hourly).where(Sensor.is_active.is_(True))
        .group_by(Sensor.id).having(observed < expected)
        .order_by(Sensor.id).limit(page.limit).offset(page.offset)
    ).mappings()
    runs = session.execute(
        select(
            Run.id, Run.source, Run.job_type, Run.status, Run.started_at,
            Run.completed_at, Run.records_fetched, Run.records_upserted,
            Run.records_skipped, Run.records_rejected, Run.error_message,
        ).order_by(Run.started_at.desc(), Run.id).limit(10)
    ).mappings()
    return {
        "stations": session.scalar(select(func.count()).select_from(Station)),
        "active_sensors": session.scalar(
            select(func.count()).select_from(Sensor).where(Sensor.is_active.is_(True))
        ),
        "measurements": session.scalar(select(func.count()).select_from(Measurement)),
        "pollutants": list(session.scalars(select(Sensor.pollutant).distinct().order_by(Sensor.pollutant))),
        "coverage": [
            item.model_dump(mode="json")
            for item in station_coverage(AirQualityReads(session), page, now)
        ],
        "historical_start": start,
        "historical_end": end,
        "expected_hours_per_sensor": expected,
        "incomplete_active_sensors": [
            {**row, "missing_hours": expected - row["observed_hours"]} for row in gaps
        ],
        "recent_runs": [dict(row) for row in runs],
    }
