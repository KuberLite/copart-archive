import csv
from pathlib import Path

from copart_archive import cases, config, metadata, tasks

SAMPLE = Path(__file__).parent / "fixtures" / "lotsearch_sample.csv"


def test_prepare_creates_dirs_with_metadata(tmp_path):
    cases.ingest(SAMPLE, tmp_path)
    result = tasks.prepare(SAMPLE, tmp_path, config.load())
    assert len(result.dirs) == result.created == 11
    assert result.not_in_cases == []
    assert result.by_group["Other"] == 3  # MINOR DENT, TOP/ROOF, BURN

    qx60 = tmp_path / "photos/Front_End/INFINITI/2019/QX60/COPART_64557536"
    data = metadata.read(qx60)
    assert data["damage_group"] == "Front_End"
    assert data["source"]["row"] == 2


def test_prepare_twice_reuses_dirs(tmp_path):
    tasks.prepare(SAMPLE, tmp_path, config.load())
    again = tasks.prepare(SAMPLE, tmp_path, config.load())
    assert again.created == 0


def test_lot_stays_in_its_first_dir(tmp_path):
    cfg = config.load()
    first = tasks.prepare(SAMPLE, tmp_path, cfg).dirs[0]
    moved = SAMPLE.read_text(encoding="utf-8-sig").replace(",FRONT END,", ",SIDE,", 1)
    task = tmp_path / "task.csv"
    task.write_text(moved, encoding="utf-8-sig")
    assert tasks.prepare(task, tmp_path, cfg).dirs[0] == first
    assert metadata.read(first)["primary_damage"] == "SIDE"


def test_lot_missing_from_cases_is_reported(tmp_path):
    result = tasks.prepare(SAMPLE, tmp_path, config.load())
    assert len(result.not_in_cases) == 11
    assert metadata.read(result.dirs[0])["source"] is None


def test_prepare_from_lot_numbers_only(tmp_path):
    cases.ingest(SAMPLE, tmp_path)
    task = tmp_path / "task.csv"
    task.write_bytes("Lot #;Комментарий\n64557536;берём\n11111111;нет такого\n".encode("cp1251"))
    result = tasks.prepare(task, tmp_path, config.load())
    assert [d.name for d in result.dirs] == ["COPART_64557536"]
    assert result.unplaced == ["11111111"]
    assert metadata.read(result.dirs[0])["source"]["row"] == 2


def test_lot_number_from_url_when_lot_column_blank(tmp_path):
    with open(SAMPLE, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows[:2]:
        row["Lot #"] = ""
    task = tmp_path / "task.csv"
    with open(task, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows[:2])
    result = tasks.prepare(task, tmp_path, config.load())
    assert [d.name for d in result.dirs] == ["COPART_64557536", "COPART_68979086"]
    assert metadata.read(result.dirs[0])["lot"] == "64557536"


SALESDATA = Path(__file__).parent / "fixtures" / "salesdata_sample.xlsx"


def test_prepare_from_salesdata_needs_no_cases(tmp_path):
    result = tasks.prepare(SALESDATA, tmp_path, config.load())
    assert len(result.dirs) == 4
    assert result.not_in_cases == [] and result.unplaced == []
    assert "Sales Data" in result.report()
    jeep = tmp_path / "photos/Side/JEEP/2015/GRAND CHEROKEE/COPART_51425816"
    assert jeep in result.dirs
    data = metadata.read(jeep)
    assert data["vin_full"] and data["trim"] == "LIMITED"
    assert data["secondary_damage"] == "MECHANICAL"


def test_filters_and_limit_run_before_folders_are_made(tmp_path):
    cfg = config.load()
    all_lots = tasks.prepare(SAMPLE, tmp_path / "a", cfg)
    assert len(all_lots.dirs) == 11

    filtered = tasks.prepare(SAMPLE, tmp_path / "b", cfg, use_filters=True)
    assert len(filtered.dirs) == 5  # only the lots that pass, no folders for the rest
    assert "прошло: 5" in filtered.report()

    limited = tasks.prepare(SAMPLE, tmp_path / "c", cfg, limit=2)
    assert len(limited.dirs) == 2
    assert sum(1 for _ in (tmp_path / "c").rglob("metadata.json")) == 2
    assert "первые 2 из 11" in limited.report()


def test_filters_on_a_salesdata_file(tmp_path):
    result = tasks.prepare(SALESDATA, tmp_path, config.load(), use_filters=True)
    assert {d.name for d in result.dirs} == {"COPART_47273516", "COPART_51425816"}


def test_unknown_lots_still_reported_when_filtering(tmp_path):
    cases.ingest(SAMPLE, tmp_path)
    task = tmp_path / "task.csv"
    task.write_text("Lot #\n64557536\n11111111\n", encoding="utf-8")
    result = tasks.prepare(task, tmp_path, config.load(), use_filters=True)
    assert [d.name for d in result.dirs] == ["COPART_64557536"]
    assert result.unplaced == ["11111111"]  # not swallowed by the filter
