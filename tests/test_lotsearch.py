from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from copart_archive import lotsearch

SAMPLE = Path(__file__).parent / "fixtures" / "lotsearch_sample.csv"


def test_read_sample():
    lots = lotsearch.read(SAMPLE)
    assert len(lots) == 11
    qx60 = lots[0]
    assert qx60.lot == "64557536"
    assert (qx60.year, qx60.make, qx60.model) == (2019, "INFINITI", "QX60")
    assert qx60.primary_damage == "FRONT END"
    assert qx60.vin_masked
    assert qx60.row == 2
    assert qx60.raw["Lot #"] == "64557536"


def test_garbage_vin_is_not_masked():
    junk = next(l for l in lotsearch.read(SAMPLE) if l.lot == "97203655")
    assert junk.vin == "123456789" and not junk.vin_masked


def test_parse_sale_date_msk():
    d, dt = lotsearch.parse_sale_date("09/18/2026 04:00 am MSK")
    assert d == date(2026, 9, 18)
    assert dt == datetime(2026, 9, 18, 4, 0, tzinfo=timezone(timedelta(hours=3)))


def test_parse_sale_date_unknown_tz_keeps_date():
    d, dt = lotsearch.parse_sale_date("09/18/2026 08:00 pm XYZ")
    assert d == date(2026, 9, 18) and dt is None


@pytest.mark.parametrize("text,expected", [
    ("FL - ORLANDO SOUTH", ("FL", "ORLANDO SOUTH")),
    ("Equipment Specialty Sale", (None, "Equipment Specialty Sale")),
])
def test_parse_sale_name(text, expected):
    assert lotsearch.parse_sale_name(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("108,972 A", 108972), ("0 N", 0), ("0", 0), ("", None),
])
def test_parse_odometer(text, expected):
    assert lotsearch.parse_odometer(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("14,886 USD", 14886), ("0 USD", None),
])
def test_parse_usd(text, expected):
    assert lotsearch.parse_usd(text) == expected


def test_missing_columns_raise(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("Lot #,Year\n1,2020\n", encoding="utf-8")
    with pytest.raises(lotsearch.SchemaError):
        lotsearch.read(bad)
