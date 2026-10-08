from pathlib import Path

from copart_archive import cli, lotsearch

SAMPLE = Path(__file__).parent / "fixtures" / "lotsearch_sample.csv"


def test_filter_writes_passed_rows(tmp_path, capsys):
    out = tmp_path / "passed.csv"
    assert cli.main(["filter", str(SAMPLE), "--out", str(out)]) == 0
    assert "прошло: 5" in capsys.readouterr().out
    lots = lotsearch.read(out)
    assert len(lots) == 5
    assert lots[0].raw == lotsearch.read(SAMPLE)[0].raw


def test_ingest_command(tmp_path, capsys):
    assert cli.main(["--root", str(tmp_path), "ingest", str(SAMPLE)]) == 0
    assert "принят" in capsys.readouterr().out
    assert (tmp_path / "cases/COPART/2026-09-18/LotSearchresults_001.csv").exists()


SALESDATA = Path(__file__).parent / "fixtures" / "salesdata_sample.xlsx"


def test_photos_dry_run_writes_nothing(tmp_path, capsys):
    root = tmp_path / "archive"
    assert cli.main(["--root", str(root), "photos", str(SALESDATA), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "К загрузке 2 лотов" in out
    assert not root.exists()  # an estimate must not create folders


def test_photos_refuses_when_disk_is_short(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(cli.photos, "free_bytes", lambda root: 1024)
    assert cli.main(["--root", str(tmp_path / "a"), "photos", str(SALESDATA)]) == 1
    assert "Не хватает места" in capsys.readouterr().out
    assert not (tmp_path / "a").exists()
