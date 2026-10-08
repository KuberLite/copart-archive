from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from copart_archive import salesdata
from copart_archive.tabular import FormatError

SAMPLE = Path(__file__).parent / "fixtures" / "salesdata_sample.xlsx"


def lots():
    return {lot.lot: lot for lot in salesdata.read(SAMPLE)}


def test_read_sample():
    assert len(lots()) == 4


def test_full_vin_and_extra_fields():
    bmw = lots()["47273516"]
    assert bmw.vin == "WBAJA5C50JWA00003" and bmw.vin_full and not bmw.vin_masked
    assert (bmw.year, bmw.make, bmw.model) == (2018, "BMW", "5 SERIES")
    assert bmw.trim == "I"
    assert bmw.source == "salesdata"
    assert "lotImages/47273516" in bmw.image_api_url
    assert bmw.sale_date == date(2026, 9, 29)
    assert bmw.sale_datetime == datetime(2026, 9, 29, 18, 0, tzinfo=timezone(timedelta(hours=-7)))


def test_secondary_damage_and_title():
    jeep = lots()["51425816"]
    assert jeep.primary_damage == "SIDE"
    assert jeep.secondary_damage == "MECHANICAL"
    assert jeep.model == "GRAND CHEROKEE"  # "Model Group" is cut to "GRAND CHER"
    assert jeep.title_type and jeep.lot_cond_code


def test_unscheduled_sale_has_no_date():
    ram = lots()["46541345"]
    assert (ram.sale_date, ram.sale_datetime) == (None, None)
    assert ram.sale_date_raw == "0"


def test_vehicle_type_tells_trailers_from_cars():
    assert lots()["46861176"].vehicle_type != salesdata.AUTOMOBILE
    assert lots()["47273516"].vehicle_type == salesdata.AUTOMOBILE


def test_zero_money_and_odometer_brand():
    ram = lots()["46541345"]
    assert ram.odometer == 86816 and ram.odometer_status == "ACTUAL"
    assert ram.repair_cost_usd == 32292
    assert lots()["46861176"].est_retail_usd is None  # Copart writes 0 for "no figure"


@pytest.mark.parametrize("group,detail,expected", [
    ("5 SERIES", "530", "5 SERIES"),      # family, as the client asked
    ("GRAND CHER", "GRAND CHEROKEE", "GRAND CHEROKEE"),  # group cut to 10 chars
    ("EXPRESS", "EXPRESS G2500", "EXPRESS G2500"),
    ("ALL OTHER", "BROUGHAM", "BROUGHAM"),
    ("UNKNOWN", "", "UNKNOWN"),
    ("MALIBU", "MALIBU", "MALIBU"),
])
def test_model_for_path(group, detail, expected):
    assert salesdata.model_for_path(group, detail) == expected


def test_wrong_file_is_rejected():
    with pytest.raises(FormatError):
        salesdata.read(Path(__file__).parent / "fixtures" / "lotsearch_sample.csv")


@pytest.mark.parametrize("day,hhmm,tz", [
    ("20261002", "2500", "PDT"),  # hours out of range
    ("20261002", "1270", "PDT"),  # minutes out of range
    ("20261002", "noon", "PDT"),
])
def test_broken_sale_time_keeps_the_day(day, hhmm, tz):
    parsed, aware = salesdata.parse_sale_date(day, hhmm, tz)
    assert parsed == date(2026, 10, 2)
    assert aware.hour == 0  # time dropped, not crashed


def test_hawaii_time_zone_is_known():
    _, aware = salesdata.parse_sale_date("20261002", "1200", "HST")
    assert aware == datetime(2026, 10, 2, 12, 0, tzinfo=timezone(timedelta(hours=-10)))


@pytest.mark.parametrize("day", ["0", "", "2026-10-02", "202610"])
def test_unparseable_day(day):
    assert salesdata.parse_sale_date(day, "1200", "PDT") == (None, None)
