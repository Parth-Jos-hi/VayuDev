from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.air_quality import (
    AirQualityMeasurement as Measurement,
    AirQualitySensor as Sensor,
    AirQualityStation as Station,
)
from app.schemas.air_quality import AirQualityPage, HistoricalMeasurementQuery, Pollutant


class AirQualityReads:
    def __init__(self, session: Session):
        self.session = session

    def stations(self, page: AirQualityPage) -> list[Station]:
        return list(self.session.scalars(
            select(Station).order_by(Station.id).limit(page.limit).offset(page.offset)
        ))

    def station(self, station_id: UUID) -> Station | None:
        return self.session.get(Station, station_id)

    def sensors(
        self, station_id: UUID, pollutant: Pollutant | None, page: AirQualityPage
    ) -> list[Sensor]:
        query = select(Sensor).where(Sensor.station_id == station_id)
        if pollutant:
            query = query.where(Sensor.pollutant == pollutant)
        return list(self.session.scalars(
            query.order_by(Sensor.id).limit(page.limit).offset(page.offset)
        ))

    def latest(self, station_id: UUID, pollutant: Pollutant | None):
        query = (
            select(
                Station.id.label("station_id"), Station.name.label("station_name"),
                Sensor.pollutant, Measurement.sensor_id, Measurement.value, Measurement.unit,
                Measurement.period_start, Measurement.period_end,
                Measurement.quality_status, Measurement.aggregation_type,
            )
            .select_from(Measurement).join(Measurement.sensor).join(Sensor.station)
            .where(
                Station.id == station_id, Measurement.quality_status == "valid",
                Measurement.period_end <= datetime.now(timezone.utc),
            )
            .distinct(Sensor.pollutant)
            .order_by(Sensor.pollutant, Measurement.period_end.desc(), Measurement.id)
        )
        if pollutant:
            query = query.where(Sensor.pollutant == pollutant)
        return self.session.execute(query).all()

    def measurements(
        self, station_id: UUID, filters: HistoricalMeasurementQuery
    ) -> list[Measurement]:
        query = select(Measurement).join(Measurement.sensor).where(
            Sensor.station_id == station_id,
            Measurement.period_start >= filters.from_at,
            Measurement.period_start < filters.to_at,
            Measurement.quality_status != "rejected",
        )
        if filters.pollutant:
            query = query.where(Sensor.pollutant == filters.pollutant)
        if filters.aggregation_type:
            query = query.where(Measurement.aggregation_type == filters.aggregation_type)
        return list(self.session.scalars(
            query.order_by(Measurement.period_start, Measurement.id)
            .limit(filters.limit).offset(filters.offset)
        ))

    def coverage(self, page: AirQualityPage, now: datetime):
        stations = (
            select(Station.id).order_by(Station.id).limit(page.limit).offset(page.offset)
        ).subquery()
        return self.session.execute(
            select(
                stations.c.id,
                func.min(Measurement.period_start),
                func.max(Measurement.period_end).filter(
                    Measurement.quality_status == "valid", Measurement.period_end <= now
                ),
                func.count(Measurement.id),
            )
            .outerjoin(Sensor, Sensor.station_id == stations.c.id)
            .outerjoin(Sensor.measurements.and_(Measurement.quality_status != "rejected"))
            .group_by(stations.c.id).order_by(stations.c.id)
        ).all()
