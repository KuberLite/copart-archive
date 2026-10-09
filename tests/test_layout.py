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


def test_damage_off_the_filter_still_gets_its_catalog_folder(tmp_path, lots):
    path = layout.lot_dir(tmp_path, lots["73853305"], config.load())  # MINOR DENT/SCRATCHES
    assert path.relative_to(tmp_path).parts[1] == "Minor_Dent"


def test_unknown_damage_goes_to_other(tmp_path, lots):
    from dataclasses import replace
    odd = replace(lots["73853305"], primary_damage="SOMETHING NEW")
    assert layout.lot_dir(tmp_path, odd, config.load()).relative_to(tmp_path).parts[1] == "Other"


def test_existing_lot_dirs(tmp_path, lots):
    path = layout.lot_dir(tmp_path, lots["64557536"], config.load())
    path.mkdir(parents=True)
    assert layout.existing_lot_dirs(tmp_path) == {"64557536": path}
    assert layout.existing_lot_dirs(tmp_path / "nope") == {}



@pytest.mark.parametrize("vin,expected", [
    ("WBAJA5C50JWA36940", "COPART_1_WBAJA5C50JWA36940"),
    ("wbaja5c50jwa36940", "COPART_1_WBAJA5C50JWA36940"),
    ("YAMC0154G213", "COPART_1_YAMC0154G213"),     # a boat's hull number is still an ID
    ("5N1DL0MM5KC******", "COPART_1"),             # masked in the website export
    ("", "COPART_1"),
    ("ABC 123", "COPART_1"),                       # anything that is not plain letters and digits
])
def test_folder_name(lots, vin, expected):
    from dataclasses import replace
    assert layout.folder_name(replace(lots["64557536"], lot="1", vin=vin)) == expected


def test_existing_dirs_with_and_without_vin(tmp_path):
    base = tmp_path / "photos/Side/JEEP/2015/X"
    (base / "COPART_111").mkdir(parents=True)
    (base / "COPART_222_WBAJA5C50JWA36940").mkdir()
    (base / "COPART_notalot").mkdir()
    found = layout.existing_lot_dirs(tmp_path)
    assert found == {"111": base / "COPART_111", "222": base / "COPART_222_WBAJA5C50JWA36940"}
