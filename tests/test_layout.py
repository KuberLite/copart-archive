from pathlib import Path

import pytest

from copart_archive import config, layout, lotsearch

SAMPLE = Path(__file__).parent / "fixtures" / "lotsearch_sample.csv"


@pytest.fixture
def lots():
    return {l.lot: l for l in lotsearch.read(SAMPLE)}


@pytest.mark.parametrize("text,expected", [
    ("QX60", "QX60"),
    ("range rover sport", "RANGE ROVER SPORT"),
    ("C/K 1500", "C_K 1500"),
    ('A:B*C?"D', "A_B_C__D"),
    ("MODEL S. ", "MODEL S"),
    ("CON", "CON_"),
    ("com1", "COM1_"),
    ("", "UNKNOWN"),
])
def test_safe_name(text, expected):
    assert layout.safe_name(text) == expected


def test_lot_dir(tmp_path, lots):
    path = layout.lot_dir(tmp_path, lots["64557536"], config.load())
    assert path == tmp_path / "photos/Front_End/INFINITI/2019/QX60/COPART_64557536"


def test_flood_group(tmp_path, lots):
    path = layout.lot_dir(tmp_path, lots["68979086"], config.load())
    assert path.relative_to(tmp_path).parts[:2] == ("photos", "Flood")


def test_off_group_damage_goes_to_other(tmp_path, lots):
    path = layout.lot_dir(tmp_path, lots["73853305"], config.load())  # MINOR DENT/SCRATCHES
    assert path.relative_to(tmp_path).parts[1] == "Other"


def test_existing_lot_dirs(tmp_path, lots):
    path = layout.lot_dir(tmp_path, lots["64557536"], config.load())
    path.mkdir(parents=True)
    assert layout.existing_lot_dirs(tmp_path) == {"64557536": path}
    assert layout.existing_lot_dirs(tmp_path / "nope") == {}
