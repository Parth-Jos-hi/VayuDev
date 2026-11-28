from enum import StrEnum


class PollutantType(StrEnum):
    PM25 = "pm25"
    PM10 = "pm10"
    NO2 = "no2"
    SO2 = "so2"
    CO = "co"
    O3 = "o3"
    NH3 = "nh3"
    PB = "pb"


class DataSource(StrEnum):
    OPENAQ = "openaq"
    CPCB = "cpcb"


class AggregationType(StrEnum):
    RAW = "raw"
    HOURLY = "hourly"
    DAILY = "daily"


class MeasurementQuality(StrEnum):
    VALID = "valid"
    SUSPECT = "suspect"
    REJECTED = "rejected"


class IngestionJobType(StrEnum):
    DISCOVERY = "discovery"
    BACKFILL = "backfill"
    INCREMENTAL = "incremental"


class IngestionStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
