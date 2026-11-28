import argparse
from collections.abc import Sequence
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.clients.openaq import OpenAQClient
from app.core.logging import configure_logging, get_logger
from app.db.repositories.air_quality import AirQualityRepository
from app.db.session import SessionLocal
from app.services.air_quality_service import (
    AirQualityIngestionResult,
    AirQualityIngestionService,
    JobType,
)


logger = get_logger(__name__)


def parse_args(args: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Synchronize air-quality data from OpenAQ"
    )
    parser.add_argument(
        "--job-type",
        required=True,
        choices=("discovery", "backfill", "incremental"),
        help="Choose whether to refresh discovery, backfill, or sync recent data",
    )
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
        default="INFO",
    )
    return parser.parse_args(args)


def _is_partial(result: AirQualityIngestionResult) -> bool:
    discovery = result.discovery_stats
    return bool(
        result.measurements_rejected
        or result.sensors_skipped
        or discovery.stations_skipped_invalid
        or discovery.sensors_rejected_invalid
    )


def _finish_failed_run(
    session: Session,
    repository: AirQualityRepository,
    run_id: UUID,
    error_type: str,
) -> None:
    with session.begin():
        repository.finish_ingestion_run(
            run_id,
            status="failed",
            completed_at=datetime.now(timezone.utc),
            error_message=error_type,
        )


def main(args: Sequence[str] | None = None) -> int:
    options = parse_args(args)
    configure_logging(options.log_level)
    provider = OpenAQClient()

    try:
        with SessionLocal() as session:
            repository = AirQualityRepository(session)
            job_type: JobType = options.job_type
            started_at = datetime.now(timezone.utc)
            with session.begin():
                run = repository.start_ingestion_run(
                    source="openaq",
                    job_type=job_type,
                    started_at=started_at,
                )

            try:
                result = AirQualityIngestionService(
                    provider,
                    repository,
                ).sync(job_type)
            except KeyboardInterrupt:
                _finish_failed_run(
                    session,
                    repository,
                    run.id,
                    "KeyboardInterrupt",
                )
                logger.warning("event=job_interrupted")
                return 130
            except Exception as error:
                error_type = type(error).__name__
                _finish_failed_run(
                    session,
                    repository,
                    run.id,
                    error_type,
                )
                logger.error(
                    "event=job_failed error_type=%s",
                    error_type,
                )
                return 1

            status = "partial" if _is_partial(result) else "success"
            with session.begin():
                repository.finish_ingestion_run(
                    run.id,
                    status=status,
                    completed_at=datetime.now(timezone.utc),
                    counts={
                        "records_fetched": result.measurements_fetched,
                        "records_upserted": result.measurements_upserted,
                        "records_rejected": result.measurements_rejected,
                    },
                )

        logger.info(
            "event=job_completed job_type=%s status=%s "
            "stations_upserted=%d sensors_upserted=%d "
            "measurements_fetched=%d measurements_upserted=%d "
            "measurements_rejected=%d sensors_skipped=%d",
            result.job_type,
            status,
            result.stations_upserted,
            result.sensors_upserted,
            result.measurements_fetched,
            result.measurements_upserted,
            result.measurements_rejected,
            result.sensors_skipped,
        )
        return 0
    finally:
        provider.close()


if __name__ == "__main__":
    raise SystemExit(main())
