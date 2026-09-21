from pathlib import Path

from copart_archive import config, filters, lotsearch

SAMPLE = Path(__file__).parent / "fixtures" / "lotsearch_sample.csv"


def test_apply_on_sample():
    result = filters.apply(lotsearch.read(SAMPLE), config.load())
    assert {l.lot for l in result.passed} == {
        "64557536",  # INFINITI QX60, FRONT END
        "68979086",  # FORD EXPEDITION, WATER/FLOOD
        "64896396",  # MERCEDES-BENZ SPRINTER, SIDE
        "59110736",  # HONDA CBR500, SIDE — vehicle type is not in the CSV
        "62546106",  # LAND ROVER
    }
    assert result.rejected == {"year": 3, "make": 2, "damage": 1}


def test_trailer_maker_is_not_hyundai():
    result = filters.apply(lotsearch.read(SAMPLE), config.load())
    assert result.other_makes["HYUNDAI TRANSLEAD INC"] == 1


def test_report_lists_rejected_damage():
    result = filters.apply(lotsearch.read(SAMPLE), config.load())
    assert "MINOR DENT/SCRATCHES" in result.report()
