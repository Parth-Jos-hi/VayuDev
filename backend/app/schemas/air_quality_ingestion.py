from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


IngestionJobType = Literal["discovery", "backfill", "incremental"]
IngestionStatus = Literal["running", "success", "partial", "failed"]
DataSource = Literal["openaq", "cpcb"]


class IngestionExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    source: DataSource
    job_type: IngestionJobType
    status: IngestionStatus
    started_at: datetime
    completed_at: datetime | None = None
    records_fetched: int = Field(default=0, ge=0)
    records_inserted: int = Field(default=0, ge=0)
    records_updated: int = Field(default=0, ge=0)
    records_skipped: int = Field(default=0, ge=0)
    records_rejected: int = Field(default=0, ge=0)
    error_message: str | None = None

    @field_validator("started_at", "completed_at")
    @classmethod
    def normalize_timezone(cls, value: datetime | None):
        if value is not None:
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("Ingestion timestamps must include timezone information")
            return value.astimezone(timezone.utc)
        return value

    @model_validator(mode="after")
    def validate_completed_time(self):
        if self.completed_at is not None and self.completed_at < self.started_at:
            raise ValueError("completed_at cannot be earlier than started_at")
        return self
