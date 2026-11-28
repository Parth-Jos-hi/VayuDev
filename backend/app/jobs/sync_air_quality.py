import argparse
from collections.abc import Sequence
from datetime import date, datetime, timezone
import json
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.clients.openaq import OpenAQClient
from app.core.config import Settings, settings
from app.core.logging import configure_logging, get_logger
from app.db.repositories.air_quality import AirQualityRepository
from app.db.session import SessionLocal
from app.jobs.air_quality_report import build_report
from app.schemas.air_quality import AirQualityPage
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
        choices=("discovery", "backfill", "incremental", "report"),
    )
    parser.add_argument("--start", type=date.fromisoformat, help="Backfill start date (UTC)")
    parser.add_argument("--end", type=date.fromisoformat, help="Backfill exclusive end date (UTC)")
    parser.add_argument("--pollutants", help="Comma-separated pollutant codes")
    parser.add_argument("--station-limit", type=int, help="Maximum stations to backfill")
    parser.add_argument("--request-budget", type=int, help="Maximum OpenAQ requests")
    parser.add_argument("--offset", type=int, default=0, help="Report page offset")
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
        default="INFO",
    )
    options = parser.parse_args(args)
    if options.job_type != "backfill" and any(
        value is not None for value in (options.start, options.end, options.station_limit)
    ):
        parser.error("--start, --end and --station-limit require a backfill job")
    if options.station_limit is not None and options.station_limit < 1:
        parser.error("--station-limit must be positive")
    overrides = {
        "air_quality_historical_start": options.start,
        "air_quality_historical_end": options.end,
        "supported_pollutants": options.pollutants,
        "openaq_max_request_budget": options.request_budget,
    }
    try:
        options.config = Settings.model_validate(
            settings.model_dump() | {key: value for key, value in overrides.items() if value is not None}
        )
        options.page = AirQualityPage(offset=options.offset)
    except ValidationError as error:
        parser.error("; ".join(item["msg"] for item in error.errors(include_input=False)))
    if options.job_type == "backfill" and (
        options.config.air_quality_historical_end <= options.config.air_quality_historical_start
    ):
        parser.error("backfill end must be after its start")
    return options


def _is_partial(result: AirQualityIngestionResult) -> bool:
    discovery = result.discovery_stats
    return bool(
        result.measurements_rejected
        or result.sensors_skipped
        or (result.job_type == "incremental" and not result.sensors_selected)
        or result.failed_windows
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
    if options.job_type == "report":
        try:
            with SessionLocal() as session:
                report = build_report(session, options.config, options.page)
        except SQLAlchemyError as error:
            logger.error("event=report_failed error_type=%s", type(error).__name__)
            return 1
        print(json.dumps(report, default=str, indent=2))
        return 0

    provider = None
    try:
        with SessionLocal() as session:
            repository = AirQualityRepository(session, batch_size=options.config.ingestion_batch_size)
            job_type: JobType = options.job_type
            started_at = datetime.now(timezone.utc)
            with session.begin():
                run = repository.start_ingestion_run(
                    source="openaq",
                    job_type=job_type,
                    started_at=started_at,
                )
                run_id = run.id

            try:
                provider = OpenAQClient(config=options.config)
                result = AirQualityIngestionService(
                    provider,
                    repository,
                    options.config,
                ).sync(job_type, station_limit=options.station_limit)
            except KeyboardInterrupt:
                _finish_failed_run(
                    session,
                    repository,
                    run_id,
                    "KeyboardInterrupt",
                )
                logger.warning("event=job_interrupted")
                return 130
            except Exception as error:
                error_type = type(error).__name__
                _finish_failed_run(
                    session,
                    repository,
                    run_id,
                    error_type,
                )
                logger.error(
                    "event=job_failed error_type=%s",
                    error_type,
                )
                return 1

            status = "partial" if _is_partial(result) else "success"
            if result.failed_windows and not result.windows_completed:
                status = "failed"
            counts = {
                "records_fetched": result.measurements_fetched,
                "records_upserted": result.measurements_upserted,
                "records_skipped": result.measurements_skipped,
                "records_rejected": result.measurements_rejected,
            }
            if job_type == "discovery":
                stats = result.discovery_stats
                counts = {
                    "records_fetched": stats.locations_seen + stats.sensors_seen,
                    "records_upserted": result.stations_upserted + result.sensors_upserted,
                    "records_rejected": stats.stations_skipped_invalid + stats.sensors_rejected_invalid,
                }
                counts["records_skipped"] = max(
                    0, counts["records_fetched"] - counts["records_upserted"] - counts["records_rejected"]
                )
            with session.begin():
                repository.finish_ingestion_run(
                    run_id,
                    status=status,
                    completed_at=datetime.now(timezone.utc),
                    counts=counts,
                    error_message=", ".join(sorted(set(result.failed_windows.values()))) or None,
                )

        for window, error_type in result.failed_windows.items():
            logger.warning("event=window_failed window=%s error_type=%s", window, error_type)
        logger.info(
            "event=job_completed job_type=%s status=%s "
            "stations_upserted=%d sensors_upserted=%d "
            "measurements_fetched=%d measurements_upserted=%d "
            "measurements_rejected=%d sensors_skipped=%d "
            "sensors_selected=%d sensors_stale=%d sensors_missing=%d windows_completed=%d",
            result.job_type,
            status,
            result.stations_upserted,
            result.sensors_upserted,
            result.measurements_fetched,
            result.measurements_upserted,
            result.measurements_rejected,
            result.sensors_skipped,
            result.sensors_selected,
            result.sensors_stale,
            result.sensors_missing,
            result.windows_completed,
        )
        return int(status == "failed")
    except SQLAlchemyError as error:
        logger.error("event=run_tracking_failed error_type=%s", type(error).__name__)
        return 1
    finally:
        if provider is not None:
            provider.close()


if __name__ == "__main__":
    raise SystemExit(main())
