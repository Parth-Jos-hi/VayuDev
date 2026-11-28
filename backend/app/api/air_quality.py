from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security.auth import get_current_user
from app.db.models.air_quality import AirQualityStation
from app.db.repositories.air_quality_reads import AirQualityReads
from app.db.session import get_db
from app.schemas.air_quality import (
    AirQualityPage,
    FreshnessCoverageResponse,
    HistoricalMeasurementQuery,
    LatestObservationResponse,
    MeasurementResponse,
    Pollutant,
    SensorQuery,
    SensorResponse,
    StationResponse,
)
from app.services.air_quality_reads import require_station, station_coverage


router = APIRouter(
    prefix="/air-quality",
    tags=["Air quality"],
    dependencies=[Depends(get_current_user)],
)


def get_repository(db: Annotated[Session, Depends(get_db)]) -> AirQualityReads:
    return AirQualityReads(db)


Repository = Annotated[AirQualityReads, Depends(get_repository)]
Page = Annotated[AirQualityPage, Query()]


def get_station(station_id: UUID, repository: Repository) -> AirQualityStation:
    try:
        return require_station(repository, station_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


Station = Annotated[AirQualityStation, Depends(get_station)]


@router.get("/stations", response_model=list[StationResponse])
def list_stations(repository: Repository, page: Page):
    return repository.stations(page)


@router.get("/stations/{station_id}", response_model=StationResponse)
def station_detail(station: Station):
    return station


@router.get("/stations/{station_id}/sensors", response_model=list[SensorResponse])
def list_sensors(
    repository: Repository, filters: Annotated[SensorQuery, Query()],
    station: Station,
):
    return repository.sensors(station.id, filters.pollutant, filters)


@router.get("/stations/{station_id}/latest", response_model=list[LatestObservationResponse])
def latest(
    repository: Repository, station: Station,
    pollutant: Pollutant | None = None,
):
    return repository.latest(station.id, pollutant)


@router.get("/stations/{station_id}/measurements", response_model=list[MeasurementResponse])
def measurements(
    repository: Repository,
    filters: Annotated[HistoricalMeasurementQuery, Query()], station: Station,
):
    return repository.measurements(station.id, filters)


@router.get("/status", response_model=list[FreshnessCoverageResponse])
def status(repository: Repository, page: Page):
    return station_coverage(repository, page)
