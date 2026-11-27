import argparse
from pathlib import Path

from app.core.logging import configure_logging, get_logger
from app.db.session import SessionLocal
from app.services.venue_ingestion_service import ingest_venue_dataset
from app.services.venue_loader import DEFAULT_BATCH_SIZE

logger = get_logger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]

DEFAULT_DATASET = (
    PROJECT_ROOT / "data" / "processed"
    / "vayudev_master_facilities.csv"
)


def parse_args(args=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import and synchronize VayuDev venues"
    )

    parser.add_argument(
        "--file", type=Path, default=DEFAULT_DATASET
    )
    parser.add_argument(
        "--batch-size", type=int, default=DEFAULT_BATCH_SIZE
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
    )

    return parser.parse_args(args)


def main(args=None) -> int:
    options = parse_args(args)
    configure_logging(options.log_level)

    try:
        with SessionLocal() as session:
            result = ingest_venue_dataset(
                session=session,
                file_path=options.file,
                batch_size=options.batch_size,
            )

        preparation = result.preparation
        loading = result.loading

        logger.info(
            "event=job_completed total=%d transformed=%d "
            "invalid=%d duplicates=%d affected=%d batches=%d",
            preparation.total_records,
            preparation.transformed_records,
            preparation.invalid_records,
            preparation.duplicate_records,
            loading.affected_records,
            loading.batches_executed,
        )

        if preparation.has_errors:
            logger.warning("event=job_completed_with_rejections")

        return 0

    except KeyboardInterrupt:
        logger.warning("event=job_interrupted")
        return 130

    except Exception as error:
        logger.error(
            "event=job_failed error_type=%s",
            type(error).__name__,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())