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
