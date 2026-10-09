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



def test_catalog_and_enabled_groups():
    cfg = config.load()
    assert list(cfg.damage_groups) == ["Front_End", "Rear_End", "Side", "Flood",
                                       "Rollover", "All_Over", "Undercarriage"]
    assert {"Hail", "Fire", "Misc"} <= set(cfg.catalog)
    assert cfg.catalog["Fire"] == {"BURN", "BURN - ENGINE", "BURN - INTERIOR"}
    assert cfg.group_for("HAIL") is None  # off: filtered out
    assert cfg.folder_for("HAIL") == "Hail"  # but has a folder
    assert cfg.folder_for("SOMETHING NEW") == "Other"


def test_catalog_covers_every_value_seen_in_sales_data():
    seen = {"FRONT END", "REAR END", "SIDE", "MINOR DENT/SCRATCHES", "MECHANICAL", "NORMAL WEAR",
            "WATER/FLOOD", "ALL OVER", "ROLLOVER", "VANDALISM", "UNDERCARRIAGE", "BURN", "HAIL",
            "TOP/ROOF", "STRIPPED", "BURN - ENGINE", "BURN - INTERIOR", "FRAME DAMAGE",
            "DAMAGE HISTORY", "BIOHAZARD/CHEMICAL", "MISSING/ALTERED VIN", "PARTIAL REPAIR",
            "REPLACED VIN", "REJECTED REPAIR", "UNKNOWN"}
    cfg = config.load()
    assert all(cfg.folder_for(v) != "Other" for v in seen)


def test_old_config_without_catalog(tmp_path):
    path = tmp_path / "old.toml"
    path.write_text("""
[filters]
year_min = 2015
makes = ["BMW"]

[damage_groups]
Front_End = ["FRONT END"]
Side = ["SIDE"]

[layout]
other_group = "Other"

[photos]
quality = "full"
""", encoding="utf-8")
    cfg = config.load(path)
    assert set(cfg.damage_groups) == set(cfg.catalog) == {"Front_End", "Side"}  # all on, as before


def test_unknown_enabled_group(tmp_path):
    bad = REPO_CONFIG.read_text(encoding="utf-8").replace('"Front_End", "Rear_End"', '"Nope", "Rear_End"', 1)
    path = tmp_path / "bad.toml"
    path.write_text(bad, encoding="utf-8")
    import pytest
    with pytest.raises(ValueError, match="Nope"):
        config.load(path)
