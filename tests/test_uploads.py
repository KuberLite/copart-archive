import json
import zipfile
from datetime import date
from pathlib import Path

import pytest

from copart_archive import salesdata, uploads
from copart_archive.tabular import FormatError

SALESDATA = Path(__file__).parent / "fixtures" / "salesdata_sample.xlsx"
DAY = date(2026, 10, 9)


def test_store_keeps_the_file_as_is(tmp_path):
    result = uploads.store(SALESDATA, tmp_path, received=DAY)
    assert result.path == tmp_path / "cases/COPART/2026-10-09/Upload_001.xlsx"
    assert result.path.read_bytes() == SALESDATA.read_bytes()
    assert not result.path.stat().st_mode & 0o222  # read-only
    assert result.table == result.path and not result.duplicate
    [entry] = json.loads((result.path.parent / "manifest.json").read_text())
    assert entry["source_name"] == "salesdata_sample.xlsx"
    assert len(entry["sha256"]) == 64


def test_original_name_from_telegram(tmp_path):
    result = uploads.store(SALESDATA, tmp_path, name="Copart_50000_rows.xlsx", received=DAY)
    [entry] = json.loads((result.path.parent / "manifest.json").read_text())
    assert entry["source_name"] == "Copart_50000_rows.xlsx"


def test_same_file_twice_is_stored_once(tmp_path):
    first = uploads.store(SALESDATA, tmp_path, received=DAY)
    again = uploads.store(SALESDATA, tmp_path, received=date(2026, 10, 10))
    assert again.duplicate and again.path == first.path
    assert not (tmp_path / "cases/COPART/2026-10-10").exists()


def test_numbering_within_a_day(tmp_path):
    other = tmp_path / "other.xlsx"
    other.write_bytes(SALESDATA.read_bytes() + b"\0")
    uploads.store(SALESDATA, tmp_path, received=DAY)
    second = uploads.store(other, tmp_path, received=DAY)
    assert second.path.name == "Upload_002.xlsx"


def test_zip_is_kept_and_its_table_unpacked(tmp_path):
    archive = tmp_path / "export.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(SALESDATA, "folder/data.xlsx")
        zf.writestr("__MACOSX/folder/._data.xlsx", b"junk")
    result = uploads.store(archive, tmp_path / "root", received=DAY)
    assert result.path.name == "Upload_001.zip"
    assert result.table.name == "data.xlsx"
    assert result.table.read_bytes() == SALESDATA.read_bytes()
    assert len(salesdata.read(result.table)) == 4


def test_zip_names_cannot_escape(tmp_path):
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../../escape.csv", "Lot #\n1\n")
    result = uploads.store(archive, tmp_path / "root", received=DAY)
    assert result.table.parent.parent == tmp_path / "root" / "work"
    assert not (tmp_path / "escape.csv").exists()


@pytest.mark.parametrize("members", [[], ["a.csv", "b.xlsx"], ["notes.txt.pdf"]])
def test_zip_needs_exactly_one_table(tmp_path, members):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for m in members:
            zf.writestr(m, "x")
    with pytest.raises(FormatError):
        uploads.store(archive, tmp_path / "root", received=DAY)


def test_unsupported_file(tmp_path):
    pdf = tmp_path / "list.pdf"
    pdf.write_bytes(b"%PDF")
    with pytest.raises(FormatError):
        uploads.store(pdf, tmp_path / "root", received=DAY)


def test_a_gap_in_numbering_does_not_overwrite(tmp_path):
    day_dir = tmp_path / "cases/COPART/2026-10-09"
    day_dir.mkdir(parents=True)
    (day_dir / "Upload_003.xlsx").write_bytes(b"older file")
    result = uploads.store(SALESDATA, tmp_path, received=DAY)
    assert result.path.name == "Upload_004.xlsx"
    assert (day_dir / "Upload_003.xlsx").read_bytes() == b"older file"


def test_broken_zip(tmp_path):
    broken = tmp_path / "broken.zip"
    broken.write_bytes(b"PK not really")
    with pytest.raises(FormatError, match="повреждён"):
        uploads.store(broken, tmp_path / "root", received=DAY)
