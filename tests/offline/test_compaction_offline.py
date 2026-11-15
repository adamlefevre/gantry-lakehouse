import uuid

import pytest

from pipelines import compact
from pipelines.compact import (
    TARGET_BATCH_BYTES,
    compact_partition_batch,
    discover_small_files,
    get_s3_client,
    init_duckdb,
    pack_batches,
)

ROWS_PER_FILE = 2_000


@pytest.fixture(scope="module")
def s3():
    return get_s3_client()


@pytest.fixture(scope="module")
def con():
    return init_duckdb()


@pytest.fixture
def prefix():
    return f"data/test_runs/run_{uuid.uuid4().hex[:8]}"


def write_files(con, directory, count, start=0):
    for i in range(start, start + count):
        con.execute(f"""
            COPY (
                SELECT ({i} * {ROWS_PER_FILE} + range)::INT AS trip_id,
                       (1 + (range % 2))::INT AS vendor_id
                FROM range({ROWS_PER_FILE})
            ) TO 'r2://{compact.BUCKET_NAME}/{directory}/micro_{i:02d}.parquet'
            (FORMAT PARQUET, COMPRESSION 'SNAPPY');
        """)


def keys(s3, prefix):
    resp = s3.list_objects_v2(Bucket=compact.BUCKET_NAME, Prefix=prefix)
    return [o["Key"] for o in resp.get("Contents", [])]


def row_count(con, key):
    return con.execute(
        f"SELECT count(*) FROM read_parquet('r2://{compact.BUCKET_NAME}/{key}')"
    ).fetchone()[0]


def test_compaction_reduces_files_and_preserves_rows(s3, con, prefix):
    write_files(con, prefix, 5)
    files = discover_small_files(s3, prefix=prefix)[prefix]
    assert len(files) == 5

    batches = pack_batches(files, TARGET_BATCH_BYTES)
    compact_partition_batch(con, prefix, batches[0])

    remaining = keys(s3, prefix)
    assert len(remaining) == 1
    assert "compacted-" in remaining[0]
    assert row_count(con, remaining[0]) == 5 * ROWS_PER_FILE


def test_single_file_batch_is_left_alone(s3, con, prefix):
    write_files(con, prefix, 1)
    before = keys(s3, prefix)

    files = discover_small_files(s3, prefix=prefix)[prefix]
    compact_partition_batch(con, prefix, files)

    assert keys(s3, prefix) == before


def test_main_compacts_every_partition_and_ignores_telemetry(s3, con):
    run = f"data/test_runs/run_{uuid.uuid4().hex[:8]}"
    part_a, part_b = f"{run}/year=2024/month=01", f"{run}/year=2024/month=02"
    write_files(con, part_a, 3)
    write_files(con, part_b, 2)
    telemetry = f"telemetry/year=2024/month=01/{uuid.uuid4().hex[:8]}.json"
    s3.put_object(Bucket=compact.BUCKET_NAME, Key=telemetry, Body=b"{}")

    compact.main()

    for part, total in ((part_a, 3), (part_b, 2)):
        remaining = keys(s3, part)
        assert len(remaining) == 1 and "compacted-" in remaining[0]
        assert row_count(con, remaining[0]) == total * ROWS_PER_FILE
    assert keys(s3, telemetry) == [telemetry]
