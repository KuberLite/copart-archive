import json
import shutil
from datetime import date
from pathlib import Path

import pytest

from copart_archive import cases

SAMPLE = Path(__file__).parent / "fixtures" / "lotsearch_sample.csv"


def test_ingest_copies_bytes_and_writes_manifest(tmp_path):
    result = cases.ingest(SAMPLE, tmp_path)
    assert result.path == tmp_path / "cases/COPART/2026-09-18/LotSearchresults_001.csv"
    assert result.path.read_bytes() == SAMPLE.read_bytes()
    assert not result.path.stat().st_mode & 0o222  # только чтение

    [entry] = json.loads((result.path.parent / "manifest.json").read_text())
    assert entry["source_name"] == SAMPLE.name
    assert entry["rows"] == 11
    assert entry["columns"][0] == "Lot URL"


def test_same_file_is_not_ingested_twice(tmp_path):
    cases.ingest(SAMPLE, tmp_path)
    again = cases.ingest(SAMPLE, tmp_path)
    assert again.duplicate
    assert len(cases.load_manifest(again.path.parent)) == 1


def test_next_file_gets_next_number(tmp_path):
    other = tmp_path / "other.csv"
    other.write_bytes(SAMPLE.read_bytes() + b"\r\n")
    cases.ingest(SAMPLE, tmp_path)
    second = cases.ingest(other, tmp_path)
    assert second.path.name == "LotSearchresults_002.csv"


def test_explicit_day(tmp_path):
    result = cases.ingest(SAMPLE, tmp_path, day=date(2026, 9, 15))
    assert result.path.parent.name == "2026-09-15"


def test_bad_file_is_rejected_before_copy(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("Lot #\n1\n", encoding="utf-8")
    with pytest.raises(ValueError):
        cases.ingest(bad, tmp_path / "root")
    assert not (tmp_path / "root").exists()
