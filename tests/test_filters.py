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


def test_vehicle_type_is_checked_when_known():
    """A listed make can still be a trailer or a boat: BMW trailers exist."""
    from dataclasses import replace

    from copart_archive import salesdata
    cfg = config.load()
    lots = salesdata.read(Path(__file__).parent / "fixtures" / "salesdata_sample.xlsx")
    bmw = next(l for l in lots if l.lot == "47273516")
    assert filters.reject_reason(bmw, cfg) is None
    assert filters.reject_reason(replace(bmw, vehicle_type="K"), cfg) == "vehicle_type"

    result = filters.apply([replace(bmw, vehicle_type="K")], cfg)
    assert result.other_types == {"K": 1}  # reported, not silently dropped


def test_website_export_has_no_vehicle_type_and_still_passes():
    cfg = config.load()
    lots = lotsearch.read(SAMPLE)
    assert all(l.vehicle_type is None for l in lots)
    assert len(filters.apply(lots, cfg).passed) == 5
