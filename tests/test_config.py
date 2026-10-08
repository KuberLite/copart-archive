from copart_archive import config


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
    custom.write_text(config.REPO_PATH.read_text(encoding="utf-8").replace(
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
