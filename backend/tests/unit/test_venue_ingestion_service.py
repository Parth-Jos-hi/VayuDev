import csv

from datetime import (
    UTC,
    datetime,
    timedelta,
    timezone,
)

import pytest

from app.integrations.venue_dataset import (
    DatasetHeaderError,
    DatasetPathError,
    DatasetRowError,
    EXPECTED_COLUMNS,
)

from app.services import venue_ingestion_service

from app.services.venue_ingestion_service import (
    IngestionResult,
    prepare_venue_ingestion,
)


# ==========================================
# TEST DATA HELPERS
# ==========================================

def make_venue_row(**overrides):

    row = {
        column: ""
        for column in EXPECTED_COLUMNS
    }

    row.update({
        "osm_type": "node",
        "osm_id": "12345",
        "name": "Test Library",
        "category": "library",
        "latitude": "28.61",
        "longitude": "77.20",
        "access_classification": "unknown",
        "verification_priority": "medium",
        "verification_status": "pending",
        "public_access_verified": "unknown",
        "indoor_space_verified": "unknown",
        "air_conditioning_verified": "unknown",
        "emergency_access_verified": "unknown",
    })

    row.update(overrides)

    return row


def create_dataset(tmp_path, rows):

    path = tmp_path / "venues.csv"

    with path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=EXPECTED_COLUMNS,
        )

        writer.writeheader()

        writer.writerows(rows)

    return path


def assert_processing_invariants(result):

    assert result.total_records == (
        result.valid_records
        + result.invalid_records
    )

    assert result.valid_records == (
        result.transformed_records
        + result.duplicate_records
    )

    assert result.total_records == (
        result.transformed_records
        + result.rejected_records
    )

    assert len(result.issues) == (
        result.rejected_records
    )


# ==========================================
# SUCCESSFUL PREPARATION
# ==========================================

def test_valid_dataset(tmp_path):

    path = create_dataset(
        tmp_path,
        [
            make_venue_row(osm_id="100"),
            make_venue_row(osm_id="200"),
            make_venue_row(osm_id="300"),
        ],
    )

    result = prepare_venue_ingestion(path)

    assert result.total_records == 3

    assert result.valid_records == 3

    assert result.transformed_records == 3

    assert result.invalid_records == 0

    assert result.duplicate_records == 0

    assert result.rejected_records == 0

    assert result.has_errors is False

    assert result.issues == []

    assert_processing_invariants(result)


# ==========================================
# RECOVERABLE VALIDATION ERRORS
# ==========================================

def test_invalid_record_does_not_stop_ingestion(
    tmp_path,
):

    path = create_dataset(
        tmp_path,
        [
            make_venue_row(osm_id="100"),

            make_venue_row(
                osm_id="200",
                latitude="95",
            ),

            make_venue_row(osm_id="300"),
        ],
    )

    result = prepare_venue_ingestion(path)

    assert result.total_records == 3

    assert result.valid_records == 2

    assert result.invalid_records == 1

    assert result.transformed_records == 2

    assert result.rejected_records == 1

    assert result.has_errors is True

    issue = result.issues[0]

    assert issue.record_number == 3

    assert issue.stage == "validation"

    assert "latitude" in issue.message

    assert_processing_invariants(result)


def test_multiple_validation_errors(tmp_path):

    path = create_dataset(
        tmp_path,
        [
            make_venue_row(
                latitude="100",
                category="invalid",
            )
        ],
    )

    result = prepare_venue_ingestion(path)

    assert result.invalid_records == 1

    assert len(result.issues) == 1

    assert "latitude" in result.issues[0].message

    assert "category" in result.issues[0].message

    assert_processing_invariants(result)


# ==========================================
# DUPLICATE DETECTION
# ==========================================

def test_duplicate_osm_identity(tmp_path):

    path = create_dataset(
        tmp_path,
        [
            make_venue_row(
                osm_id="100",
                name="First Library",
            ),

            make_venue_row(
                osm_id="100",
                name="Duplicate Library",
            ),
        ],
    )

    result = prepare_venue_ingestion(path)

    assert result.total_records == 2

    assert result.valid_records == 2

    assert result.duplicate_records == 1

    assert result.transformed_records == 1

    assert result.records[0]["name"] == (
        "First Library"
    )

    issue = result.issues[0]

    assert issue.record_number == 3

    assert issue.stage == "duplicate"

    assert "node/100" in issue.message

    assert_processing_invariants(result)


def test_composite_osm_identity(tmp_path):

    path = create_dataset(
        tmp_path,
        [
            make_venue_row(
                osm_type="node",
                osm_id="100",
            ),

            make_venue_row(
                osm_type="way",
                osm_id="100",
            ),

            make_venue_row(
                osm_type="relation",
                osm_id="100",
            ),
        ],
    )

    result = prepare_venue_ingestion(path)

    assert result.transformed_records == 3

    assert result.duplicate_records == 0

    assert_processing_invariants(result)


def test_duplicate_detection_after_normalization(
    tmp_path,
):

    path = create_dataset(
        tmp_path,
        [
            make_venue_row(
                osm_type="node",
                osm_id="100",
            ),

            make_venue_row(
                osm_type=" NODE ",
                osm_id="00100",
            ),
        ],
    )

    result = prepare_venue_ingestion(path)

    assert result.transformed_records == 1

    assert result.duplicate_records == 1

    assert_processing_invariants(result)


def test_invalid_identity_does_not_block_valid_record(
    tmp_path,
):

    path = create_dataset(
        tmp_path,
        [
            make_venue_row(
                osm_id="100",
                latitude="95",
            ),

            make_venue_row(
                osm_id="100",
                latitude="28.61",
            ),
        ],
    )

    result = prepare_venue_ingestion(path)

    assert result.invalid_records == 1

    assert result.duplicate_records == 0

    assert result.transformed_records == 1

    assert_processing_invariants(result)


# ==========================================
# EMPTY DATASET
# ==========================================

def test_header_only_dataset(tmp_path):

    path = create_dataset(tmp_path, [])

    result = prepare_venue_ingestion(path)

    assert result.total_records == 0

    assert result.valid_records == 0

    assert result.transformed_records == 0

    assert result.rejected_records == 0

    assert result.has_errors is False

    assert_processing_invariants(result)


# ==========================================
# FATAL DATASET ERRORS
# ==========================================

def test_missing_dataset(tmp_path):

    path = tmp_path / "missing.csv"

    with pytest.raises(DatasetPathError):

        prepare_venue_ingestion(path)


def test_invalid_dataset_header(tmp_path):

    path = tmp_path / "venues.csv"

    path.write_text(
        "osm_type,osm_id\nnode,123\n",
        encoding="utf-8",
    )

    with pytest.raises(DatasetHeaderError):

        prepare_venue_ingestion(path)


def test_malformed_dataset_row(tmp_path):

    path = create_dataset(
        tmp_path,
        [make_venue_row()],
    )

    with path.open(
        "a",
        encoding="utf-8",
    ) as file:

        file.write("node,123\n")

    with pytest.raises(DatasetRowError):

        prepare_venue_ingestion(path)


# ==========================================
# SYNCHRONIZATION TIMESTAMPS
# ==========================================

def test_shared_synchronization_timestamp(tmp_path):

    path = create_dataset(
        tmp_path,
        [
            make_venue_row(osm_id="100"),
            make_venue_row(osm_id="200"),
        ],
    )

    timestamp = datetime(
        2026, 11, 27, 10, 0,
        tzinfo=UTC,
    )

    result = prepare_venue_ingestion(
        path,
        synced_at=timestamp,
    )

    assert result.synced_at == timestamp

    for record in result.records:

        assert record["last_synced_at"] == timestamp


def test_timestamp_converted_to_utc(tmp_path):

    path = create_dataset(
        tmp_path,
        [make_venue_row()],
    )

    ist = timezone(
        timedelta(hours=5, minutes=30)
    )

    timestamp = datetime(
        2026, 11, 27, 10, 0,
        tzinfo=ist,
    )

    result = prepare_venue_ingestion(
        path,
        synced_at=timestamp,
    )

    expected = datetime(
        2026, 11, 27, 4, 30,
        tzinfo=UTC,
    )

    assert result.synced_at == expected

    assert result.synced_at.tzinfo == UTC


def test_naive_timestamp_rejected(tmp_path):

    path = create_dataset(tmp_path, [])

    timestamp = datetime(
        2026, 11, 27, 10, 0
    )

    with pytest.raises(
        ValueError,
        match="timezone-aware",
    ):

        prepare_venue_ingestion(
            path,
            synced_at=timestamp,
        )


# ==========================================
# STATE ISOLATION
# ==========================================

def test_result_lists_are_independent():

    timestamp = datetime.now(UTC)

    first = IngestionResult(
        synced_at=timestamp
    )

    second = IngestionResult(
        synced_at=timestamp
    )

    first.records.append({"osm_id": 100})

    assert first.records is not second.records

    assert first.issues is not second.issues

    assert second.records == []

    assert first.transformed_records == 1

    assert second.transformed_records == 0


def test_independent_ingestion_runs(tmp_path):

    path = create_dataset(
        tmp_path,
        [make_venue_row()],
    )

    first = prepare_venue_ingestion(path)

    second = prepare_venue_ingestion(path)

    assert first.transformed_records == 1

    assert second.transformed_records == 1

    assert first.duplicate_records == 0

    assert second.duplicate_records == 0

    assert first.records is not second.records


# ==========================================
# RESOURCE CLEANUP
# ==========================================

def test_transformer_failure_closes_generator(
    monkeypatch,
):

    closed = False

    def fake_reader(file_path):

        nonlocal closed

        try:

            yield 2, make_venue_row()

            yield 3, make_venue_row(
                osm_id="200"
            )

        finally:

            closed = True

    def failing_transformer(*args, **kwargs):

        raise RuntimeError(
            "Unexpected transformation failure"
        )

    monkeypatch.setattr(
        venue_ingestion_service,
        "read_venue_dataset",
        fake_reader,
    )

    monkeypatch.setattr(
        venue_ingestion_service,
        "transform_venue_record",
        failing_transformer,
    )

    with pytest.raises(
        RuntimeError,
        match="Unexpected transformation failure",
    ):

        prepare_venue_ingestion("unused.csv")

    assert closed is True


# ==========================================
# COMPLETE MIXED DATASET
# ==========================================

def test_mixed_dataset(tmp_path):

    path = create_dataset(
        tmp_path,
        [
            make_venue_row(osm_id="100"),

            make_venue_row(osm_id="200"),

            make_venue_row(
                osm_id="300",
                latitude="95",
            ),

            make_venue_row(osm_id="100"),

            make_venue_row(
                osm_type="way",
                osm_id="100",
            ),

            make_venue_row(
                osm_id="400",
                category="invalid",
            ),

            make_venue_row(osm_id="500"),
        ],
    )

    result = prepare_venue_ingestion(path)

    assert result.total_records == 7

    assert result.valid_records == 5

    assert result.invalid_records == 2

    assert result.duplicate_records == 1

    assert result.transformed_records == 4

    assert result.rejected_records == 3

    assert [
        issue.stage
        for issue in result.issues
    ] == [
        "validation",
        "duplicate",
        "validation",
    ]

    assert_processing_invariants(result)