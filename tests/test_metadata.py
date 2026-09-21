from pathlib import Path

from copart_archive import cases, config, metadata, lotsearch

SAMPLE = Path(__file__).parent / "fixtures" / "lotsearch_sample.csv"


def qx60():
    return next(l for l in lotsearch.read(SAMPLE) if l.lot == "64557536")


def test_build_matches_client_fields():
    source = cases.Source(Path("cases/COPART/2026-09-18/LotSearchresults_001.csv"), 2)
    data = metadata.build(qx60(), "Front_End", source)
    assert data["auction"] == "COPART"
    assert data["vin"] == "5N1DL0MM5KC******"
    assert (data["year"], data["make"], data["model"]) == (2019, "INFINITI", "QX60")
    assert data["primary_damage"] == "FRONT END"
    assert data["sale_date"] == "2026-09-18"
    assert data["source"] == {"file": "cases/COPART/2026-09-18/LotSearchresults_001.csv", "row": 2}
    assert data["source_row"]["Lot #"] == "64557536"


def test_write_keeps_accumulated_fields(tmp_path):
    metadata.write(tmp_path, {"lot": "1", "photos": ["01.jpg"]})
    first = metadata.read(tmp_path)
    metadata.write(tmp_path, {"lot": "1", "model": "QX60"})
    second = metadata.read(tmp_path)
    assert second["photos"] == ["01.jpg"]
    assert second["model"] == "QX60"
    assert second["created_at"] == first["created_at"]


def test_lot_index(tmp_path):
    cases.ingest(SAMPLE, tmp_path)
    index = cases.lot_index(tmp_path, {"64557536", "11111111"})
    assert list(index) == ["64557536"]  # only wanted lots are kept
    source, lot = index["64557536"]
    assert source == cases.Source(Path("cases/COPART/2026-09-18/LotSearchresults_001.csv"), 2)
    assert lot.make == "INFINITI"
