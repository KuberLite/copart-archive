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
