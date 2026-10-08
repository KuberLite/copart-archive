"""Copart Sales Data subscription file ("Get New CSV Sales Data").

Unlike the CSV export from the website this one carries the full VIN, the trim,
the secondary damage and — most importantly — an "Image URL" pointing at
Copart's own image API, which is how photos are meant to be obtained.
"""

import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .lotsearch import TZ_OFFSETS, Lot, parse_sale_name
from .tabular import FormatError, read_tables

REQUIRED_COLUMNS = ("Lot number", "VIN", "Year", "Make", "Damage Description")
ODOMETER_BRANDS = {"A": "ACTUAL", "N": "NOT ACTUAL", "E": "EXEMPT"}
AUTOMOBILE = "V"  # Vehicle Type; K and L are trailers and the like
USELESS_GROUPS = {"", "UNKNOWN", "ALL OTHER"}


def model_for_path(group: str, detail: str) -> str:
    """Folder model name. "Model Group" is the family the client wants to group by
    ("5 SERIES" for a 530), but Copart cuts it to 10 characters ("GRAND CHER")
    and sometimes fills it with "ALL OTHER". "Model Detail" covers those cases."""
    group, detail = group.strip().upper(), detail.strip().upper()
    if group in USELESS_GROUPS:
        return detail or group
    truncated = len(detail) > len(group) and detail.startswith(group[:6])
    return detail if truncated and detail else group


def _int(text: str) -> int | None:
    digits = re.match(r"\d+", text.replace(",", ""))
    return int(digits[0]) if digits else None


def _positive(text: str) -> int | None:
    """Money and mileage: Copart writes 0 where it has no figure."""
    return _int(text) or None


def parse_sale_date(day: str, hhmm: str, tz: str) -> tuple[date | None, datetime | None]:
    """'20261002' + '1200' + 'PDT'. A zero day means the sale is not scheduled."""
    if not re.fullmatch(r"\d{8}", day.strip()) or day.strip() == "00000000":
        return None, None
    local = datetime.strptime(day.strip(), "%Y%m%d")
    minutes = _int(hhmm) if re.fullmatch(r"\d{1,4}", hhmm.strip()) else None
    if minutes is not None and minutes // 100 < 24 and minutes % 100 < 60:
        local = local.replace(hour=minutes // 100, minute=minutes % 100)
    offset = TZ_OFFSETS.get(tz.strip().upper())
    aware = local.replace(tzinfo=timezone(timedelta(hours=offset))) if offset is not None else None
    return local.date(), aware


def from_row(row: dict[str, str], line: int) -> Lot:
    get = lambda name: (row.get(name) or "").strip()
    lot = get("Lot number")
    sale_date, sale_datetime = parse_sale_date(
        get("Sale Date M/D/CY"), get("Sale time (HHMM)"), get("Time Zone"))
    state, yard = parse_sale_name(get("Yard name"))
    year = get("Year")
    return Lot(
        lot=lot,
        lot_url=get("Copart URL") or f"https://www.copart.com/lot/{lot}",
        year=int(year) if year.isdigit() else None,
        make=get("Make").upper(),
        model=model_for_path(get("Model Group"), get("Model Detail")),
        vin=get("VIN").upper(),
        primary_damage=get("Damage Description").upper(),
        sale_date_raw=get("Sale Date M/D/CY"),
        sale_date=sale_date,
        sale_datetime=sale_datetime,
        sale_name=get("Yard name"),
        state=get("Location state") or state,
        yard=yard or get("Location city"),
        title=get("Sale Title Type"),
        odometer=_int(get("Odometer")),
        odometer_status=ODOMETER_BRANDS.get(get("Odometer Brand"), get("Odometer Brand")),
        est_retail_usd=_positive(get("Est. Retail Value")),
        engine=get("Engine"),
        cylinders=get("Cylinders"),
        row=line,
        raw=dict(row),
        source="salesdata",
        trim=get("Trim") or None,
        secondary_damage=get("Secondary Damage").upper() or None,
        vehicle_type=get("Vehicle Type") or None,
        body_style=get("Body Style") or None,
        color=get("Color") or None,
        drive=get("Drive") or None,
        transmission=get("Transmission") or None,
        fuel=get("Fuel Type") or None,
        keys=get("Has Keys-Yes or No") or None,
        runs_drives=get("Runs/Drives") or None,
        title_type=get("Sale Title Type") or None,
        lot_cond_code=get("Lot Cond. Code") or None,
        repair_cost_usd=_positive(get("Repair cost")),
        seller=get("Seller Name") or None,
        image_api_url=get("Image URL") or None,
    )


def read(path: Path) -> list[Lot]:
    """Lots of a subscription file. The first table with the right columns wins."""
    for _, table in read_tables(path):
        if not table:
            continue
        header = [h.strip() for h in table[0]]
        if any(c not in header for c in REQUIRED_COLUMNS):
            continue
        lots = []
        for line, values in enumerate(table[1:], start=2):
            if not any(values):
                continue
            row = dict(zip(header, values))
            if (row.get("Lot number") or "").strip():
                lots.append(from_row(row, line))
        return lots
    raise FormatError(f"{path.name}: не похоже на выгрузку Sales Data, нет колонок {REQUIRED_COLUMNS}")
