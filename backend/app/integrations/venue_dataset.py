import csv

from collections.abc import Iterator
from pathlib import Path

from app.schemas.venues import VenueIngestionSchema


# ==========================================
# DATASET CONFIGURATION
# ==========================================

CSV_ENCODING = "utf-8-sig"

EXPECTED_COLUMNS: tuple[str, ...] = tuple(
    VenueIngestionSchema.model_fields.keys()
)


# ==========================================
# CUSTOM DATASET EXCEPTIONS
# ==========================================

class VenueDatasetError(ValueError):
    """Base exception for venue dataset errors."""


class DatasetPathError(VenueDatasetError):
    """Invalid or inaccessible dataset path."""


class DatasetHeaderError(VenueDatasetError):
    """Invalid CSV header structure."""


class DatasetRowError(VenueDatasetError):
    """Malformed CSV record."""


# ==========================================
# DATASET PATH VALIDATION
# ==========================================

def validate_dataset_path(
    file_path: str | Path,
) -> Path:

    path = Path(file_path).expanduser().resolve()

    if not path.exists():

        raise DatasetPathError(
            f"Dataset file does not exist: {path}"
        )

    if not path.is_file():

        raise DatasetPathError(
            f"Dataset path is not a file: {path}"
        )

    if path.suffix.lower() != ".csv":

        raise DatasetPathError(
            f"Dataset must be a CSV file: {path}"
        )

    return path


# ==========================================
# CSV HEADER VALIDATION
# ==========================================

def validate_csv_header(
    fieldnames: list[str] | None,
) -> None:

    if not fieldnames:

        raise DatasetHeaderError(
            "CSV header is missing or empty"
        )

    if any(not column.strip() for column in fieldnames):

        raise DatasetHeaderError(
            "CSV header contains an empty column name"
        )

    actual_columns = set(fieldnames)
    expected_columns = set(EXPECTED_COLUMNS)

    # Detect duplicate column names

    if len(fieldnames) != len(actual_columns):

        duplicate_columns = sorted({
            column
            for column in fieldnames
            if fieldnames.count(column) > 1
        })

        raise DatasetHeaderError(
            f"Duplicate CSV columns: {duplicate_columns}"
        )

    # Detect missing and unexpected columns

    missing_columns = (
        expected_columns - actual_columns
    )

    unexpected_columns = (
        actual_columns - expected_columns
    )

    errors = []

    if missing_columns:

        errors.append(
            f"Missing columns: {sorted(missing_columns)}"
        )

    if unexpected_columns:

        errors.append(
            f"Unexpected columns: {sorted(unexpected_columns)}"
        )

    if errors:

        raise DatasetHeaderError(
            "; ".join(errors)
        )


# ==========================================
# DATASET READER
# ==========================================

def read_venue_dataset(
    file_path: str | Path,
) -> Iterator[tuple[int, dict[str, str]]]:

    path = validate_dataset_path(file_path)

    try:

        with path.open(
            mode="r",
            encoding=CSV_ENCODING,
            newline="",
        ) as file:

            reader = csv.DictReader(
                file,
                strict=True,
            )

            # Validate CSV structure

            try:

                validate_csv_header(
                    reader.fieldnames
                )

            except csv.Error as error:

                raise DatasetHeaderError(
                    f"Unable to parse CSV header: {error}"
                ) from error

            # Read records incrementally

            try:

                for record_number, row in enumerate(
                    reader,
                    start=2,
                ):

                    # Extra CSV values

                    if None in row:

                        raise DatasetRowError(
                            f"Record {record_number}: "
                            "contains extra field values"
                        )

                    # Missing CSV values

                    missing_values = [
                        column
                        for column, value in row.items()
                        if value is None
                    ]

                    if missing_values:

                        raise DatasetRowError(
                            f"Record {record_number}: "
                            f"missing values for "
                            f"{missing_values}"
                        )

                    # Return one record at a time

                    yield record_number, row

            except csv.Error as error:

                raise DatasetRowError(
                    f"Malformed CSV near physical line "
                    f"{reader.line_num}: {error}"
                ) from error

    except OSError as error:

        raise DatasetPathError(
            f"Unable to read dataset: {path}"
        ) from error

    except UnicodeError as error:

        raise VenueDatasetError(
            f"Invalid dataset encoding: {path}"
        ) from error