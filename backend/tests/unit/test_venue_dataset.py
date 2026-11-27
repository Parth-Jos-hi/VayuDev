import csv

from contextlib import closing

import pytest

from app.integrations.venue_dataset import (
    CSV_ENCODING,
    EXPECTED_COLUMNS,
    DatasetPathError,
    DatasetHeaderError,
    DatasetRowError,
    VenueDatasetError,
    validate_dataset_path,
    validate_csv_header,
    read_venue_dataset,
)


# ==========================================
# TEST DATA HELPERS
# ==========================================

def make_row(**overrides):

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


def create_csv(
    tmp_path,
    rows,
    columns=EXPECTED_COLUMNS,
    encoding=CSV_ENCODING,
):

    path = tmp_path / "venues.csv"

    with path.open(
        "w",
        encoding=encoding,
        newline="",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=columns,
        )

        writer.writeheader()

        writer.writerows(rows)

    return path


# ==========================================
# CONFIGURATION TESTS
# ==========================================

def test_expected_columns():

    assert len(EXPECTED_COLUMNS) == 24

    assert len(set(EXPECTED_COLUMNS)) == 24

    assert "osm_id" in EXPECTED_COLUMNS
    assert "latitude" in EXPECTED_COLUMNS
    assert "longitude" in EXPECTED_COLUMNS


def test_csv_encoding():

    assert CSV_ENCODING == "utf-8-sig"


# ==========================================
# PATH VALIDATION
# ==========================================

def test_valid_dataset_path(tmp_path):

    path = create_csv(
        tmp_path,
        [make_row()],
    )

    result = validate_dataset_path(path)

    assert result == path.resolve()

    assert result.is_file()


def test_string_dataset_path(tmp_path):

    path = create_csv(tmp_path, [])

    result = validate_dataset_path(str(path))

    assert result == path.resolve()


def test_missing_dataset_path(tmp_path):

    path = tmp_path / "missing.csv"

    with pytest.raises(DatasetPathError):

        validate_dataset_path(path)


def test_directory_is_not_dataset(tmp_path):

    with pytest.raises(DatasetPathError):

        validate_dataset_path(tmp_path)


def test_invalid_file_extension(tmp_path):

    path = tmp_path / "venues.txt"

    path.write_text("test", encoding="utf-8")

    with pytest.raises(DatasetPathError):

        validate_dataset_path(path)


def test_uppercase_csv_extension(tmp_path):

    path = tmp_path / "venues.CSV"

    path.write_text("", encoding="utf-8")

    assert validate_dataset_path(path) == (
        path.resolve()
    )


# ==========================================
# HEADER VALIDATION
# ==========================================

def test_valid_header():

    validate_csv_header(
        list(EXPECTED_COLUMNS)
    )


def test_reordered_header():

    validate_csv_header(
        list(reversed(EXPECTED_COLUMNS))
    )


@pytest.mark.parametrize(
    "header",
    [None, []],
)
def test_missing_header(header):

    with pytest.raises(DatasetHeaderError):

        validate_csv_header(header)


@pytest.mark.parametrize(
    "column",
    ["", "   "],
)
def test_blank_column_name(column):

    header = list(EXPECTED_COLUMNS)

    header[0] = column

    with pytest.raises(DatasetHeaderError):

        validate_csv_header(header)


def test_missing_column():

    header = list(EXPECTED_COLUMNS)

    header.remove("osm_id")

    with pytest.raises(
        DatasetHeaderError,
        match="Missing columns",
    ):

        validate_csv_header(header)


def test_unexpected_column():

    header = list(EXPECTED_COLUMNS)

    header.append("unexpected_column")

    with pytest.raises(
        DatasetHeaderError,
        match="Unexpected columns",
    ):

        validate_csv_header(header)


def test_duplicate_column():

    header = list(EXPECTED_COLUMNS)

    header.append("latitude")

    with pytest.raises(
        DatasetHeaderError,
        match="Duplicate CSV columns",
    ):

        validate_csv_header(header)


def test_missing_and_unexpected_columns():

    header = list(EXPECTED_COLUMNS)

    header.remove("osm_id")

    header.append("invalid_column")

    with pytest.raises(DatasetHeaderError) as error:

        validate_csv_header(header)

    message = str(error.value)

    assert "Missing columns" in message
    assert "Unexpected columns" in message


# ==========================================
# VALID DATASET READING
# ==========================================

def test_read_single_record(tmp_path):

    path = create_csv(
        tmp_path,
        [make_row()],
    )

    records = list(read_venue_dataset(path))

    assert len(records) == 1

    number, row = records[0]

    assert number == 2

    assert row["osm_id"] == "12345"

    assert row["name"] == "Test Library"

    assert len(row) == 24


def test_read_multiple_records(tmp_path):

    path = create_csv(
        tmp_path,
        [
            make_row(osm_id="100"),
            make_row(osm_id="200"),
            make_row(osm_id="300"),
        ],
    )

    records = list(read_venue_dataset(path))

    assert len(records) == 3

    assert [number for number, _ in records] == [
        2, 3, 4
    ]

    assert [
        row["osm_id"]
        for _, row in records
    ] == [
        "100", "200", "300"
    ]


def test_header_only_dataset(tmp_path):

    path = create_csv(tmp_path, [])

    assert list(read_venue_dataset(path)) == []


def test_raw_values_are_preserved(tmp_path):

    path = create_csv(
        tmp_path,
        [
            make_row(
                name="  Test Library  ",
                osm_id="00100",
                phone="",
            )
        ],
    )

    _, row = next(
        iter(list(read_venue_dataset(path)))
    )

    assert row["name"] == "  Test Library  "

    assert row["osm_id"] == "00100"

    assert row["phone"] == ""

    assert isinstance(row["latitude"], str)


def test_reordered_csv_columns(tmp_path):

    path = create_csv(
        tmp_path,
        [make_row()],
        columns=list(reversed(EXPECTED_COLUMNS)),
    )

    records = list(read_venue_dataset(path))

    assert len(records) == 1

    assert records[0][1]["osm_id"] == "12345"


# ==========================================
# ENCODING AND SPECIAL CHARACTERS
# ==========================================

@pytest.mark.parametrize(
    "encoding",
    ["utf-8", "utf-8-sig"],
)
def test_supported_encoding(tmp_path, encoding):

    path = create_csv(
        tmp_path,
        [
            make_row(name="दिल्ली पुस्तकालय")
        ],
        encoding=encoding,
    )

    records = list(read_venue_dataset(path))

    assert records[0][1]["name"] == (
        "दिल्ली पुस्तकालय"
    )


def test_quoted_commas(tmp_path):

    name = "Library, New Delhi"

    path = create_csv(
        tmp_path,
        [make_row(name=name)],
    )

    records = list(read_venue_dataset(path))

    assert records[0][1]["name"] == name


def test_multiline_csv_value(tmp_path):

    notes = "First line\nSecond line"

    path = create_csv(
        tmp_path,
        [
            make_row(verification_notes=notes),
            make_row(osm_id="200"),
        ],
    )

    records = list(read_venue_dataset(path))

    assert records[0][1]["verification_notes"] == notes

    assert records[1][0] == 3


def test_invalid_encoding(tmp_path):

    path = tmp_path / "venues.csv"

    path.write_bytes(b"\xff\xfe\xff")

    with pytest.raises(
        VenueDatasetError,
        match="encoding",
    ):

        list(read_venue_dataset(path))


# ==========================================
# INVALID CSV STRUCTURE
# ==========================================

def test_empty_file(tmp_path):

    path = tmp_path / "venues.csv"

    path.write_text("", encoding="utf-8")

    with pytest.raises(DatasetHeaderError):

        list(read_venue_dataset(path))


def test_invalid_file_header(tmp_path):

    path = tmp_path / "venues.csv"

    path.write_text(
        "osm_id,name\n100,Library\n",
        encoding="utf-8",
    )

    with pytest.raises(DatasetHeaderError):

        list(read_venue_dataset(path))


def test_row_with_missing_values(tmp_path):

    path = create_csv(tmp_path, [])

    with path.open(
        "a",
        encoding="utf-8",
        newline="",
    ) as file:

        writer = csv.writer(file)

        writer.writerow(["node", "12345"])

    with pytest.raises(
        DatasetRowError,
        match="missing values",
    ):

        list(read_venue_dataset(path))


def test_row_with_extra_values(tmp_path):

    path = create_csv(tmp_path, [])

    with path.open(
        "a",
        encoding="utf-8",
        newline="",
    ) as file:

        writer = csv.writer(file)

        writer.writerow(
            list(make_row().values())
            + ["extra_value"]
        )

    with pytest.raises(
        DatasetRowError,
        match="extra field values",
    ):

        list(read_venue_dataset(path))


def test_malformed_csv_quotation(tmp_path):

    path = create_csv(tmp_path, [])

    with path.open(
        "a",
        encoding="utf-8",
    ) as file:

        file.write('"unclosed quotation')

    with pytest.raises(DatasetRowError):

        list(read_venue_dataset(path))


# ==========================================
# GENERATOR BEHAVIOUR
# ==========================================

def test_lazy_execution(tmp_path):

    path = tmp_path / "missing.csv"

    with closing(read_venue_dataset(path)) as records:

        with pytest.raises(DatasetPathError):

            next(records)


def test_incremental_reading(tmp_path):

    path = create_csv(
        tmp_path,
        [
            make_row(osm_id="100"),
            make_row(osm_id="200"),
        ],
    )

    with closing(read_venue_dataset(path)) as records:

        first = next(records)

        second = next(records)

        assert first[1]["osm_id"] == "100"

        assert second[1]["osm_id"] == "200"

        with pytest.raises(StopIteration):

            next(records)


def test_reader_does_not_validate_field_values(tmp_path):

    path = create_csv(
        tmp_path,
        [make_row(latitude="invalid")],
    )

    records = list(read_venue_dataset(path))

    assert records[0][1]["latitude"] == "invalid"


def test_custom_exception_hierarchy():

    assert issubclass(
        DatasetPathError,
        VenueDatasetError,
    )

    assert issubclass(
        DatasetHeaderError,
        VenueDatasetError,
    )

    assert issubclass(
        DatasetRowError,
        VenueDatasetError,
    )

    assert issubclass(
        VenueDatasetError,
        ValueError,
    )