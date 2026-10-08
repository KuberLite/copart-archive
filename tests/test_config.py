from pathlib import Path

from copart_archive import config

# the repo copy, reachable whether the package is installed or not
REPO_CONFIG = Path(__file__).resolve().parents[1] / "config" / "archive.toml"


def test_default_config_loads():
    cfg = config.load()
    assert cfg.year_min == 2015
    assert len(cfg.makes) == 21
    assert "MERCEDES-BENZ" in cfg.makes
    assert cfg.photo_quality == "full"


def test_group_for():
    cfg = config.load()
    assert cfg.group_for("FRONT END") == "Front_End"
    assert cfg.group_for("water/flood ") == "Flood"
    assert cfg.group_for("HAIL") is None


def test_config_path_from_environment(tmp_path, monkeypatch):
    custom = tmp_path / "archive.toml"
    custom.write_text(REPO_CONFIG.read_text(encoding="utf-8").replace(
        'quality = "full"', 'quality = "high_res"'), encoding="utf-8")
    monkeypatch.setenv("COPART_ARCHIVE_CONFIG", str(custom))
    assert config.load().photo_quality == "high_res"


def test_missing_config_says_what_to_set(tmp_path, monkeypatch):
    monkeypatch.setenv("COPART_ARCHIVE_CONFIG", str(tmp_path / "nope.toml"))
    try:
        config.load()
    except FileNotFoundError as error:
        assert "COPART_ARCHIVE_CONFIG" in str(error)
    else:
        raise AssertionError("ожидалась ошибка")


def test_found_next_to_the_working_directory(tmp_path, monkeypatch):
    monkeypatch.delenv("COPART_ARCHIVE_CONFIG", raising=False)
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "archive.toml").write_text(
        REPO_CONFIG.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert config.find() == tmp_path / "config" / "archive.toml"
    assert config.load().year_min == 2015


def test_falls_back_to_the_repo_copy(tmp_path, monkeypatch):
    monkeypatch.delenv("COPART_ARCHIVE_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)
    assert config.find() == config.REPO_PATH


def test_vehicle_types_empty_means_everything():
    assert config.load().vehicle_types == frozenset()
