"""Чтение CSV-выгрузки Copart (кнопка Export в поиске / списке продажи)."""

import csv
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REQUIRED_COLUMNS = (
    "Lot URL", "Lot #", "Est. Retail value", "Sale date", "Year", "Make", "Model",
    "Engine type", "Cylinders", "VIN", "Title code", "Odometer",
    "Odometer description", "Damage description", "Sale name",
)

# Copart пишет пояс аббревиатурой, какой выбран в аккаунте.
TZ_OFFSETS = {
    "MSK": 3, "UTC": 0, "GMT": 0,
    "EST": -5, "EDT": -4, "CST": -6, "CDT": -5,
    "MST": -7, "MDT": -6, "PST": -8, "PDT": -7,
}


class SchemaError(ValueError):
    """В CSV нет нужных колонок — Copart поменял формат выгрузки."""


@dataclass(frozen=True)
class Lot:
    lot: str
    lot_url: str
    year: int | None
    make: str
    model: str
    vin: str
    primary_damage: str
    sale_date_raw: str
    sale_date: date | None
    sale_datetime: datetime | None
    sale_name: str
    state: str | None
    yard: str
    title: str
    odometer: int | None
    odometer_status: str
    est_retail_usd: int | None
    engine: str
    cylinders: str
    row: int  # номер строки в файле, заголовок — 1
    raw: dict[str, str]

    @property
    def vin_masked(self) -> bool:
        return "*" in self.vin


def _int(text: str) -> int | None:
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


def parse_sale_date(text: str) -> tuple[date | None, datetime | None]:
    """'09/18/2026 04:00 am MSK' -> (дата, время с поясом, если пояс известен)."""
    m = re.fullmatch(r"(\d{2}/\d{2}/\d{4}) (\d{1,2}:\d{2} [ap]m)(?: (\w+))?", text.strip(), re.I)
    if not m:
        return None, None
    local = datetime.strptime(f"{m[1]} {m[2].upper()}", "%m/%d/%Y %I:%M %p")
    offset = TZ_OFFSETS.get((m[3] or "").upper())
    aware = local.replace(tzinfo=timezone(timedelta(hours=offset))) if offset is not None else None
    return local.date(), aware


def parse_sale_name(text: str) -> tuple[str | None, str]:
    """'FL - ORLANDO SOUTH' -> ('FL', 'ORLANDO SOUTH'); спецпродажи — без штата."""
    m = re.fullmatch(r"([A-Z]{2}) - (.+)", text.strip())
    return (m[1], m[2]) if m else (None, text.strip())


def parse_odometer(text: str) -> int | None:
    """'108,972 A' -> 108972. Буква — код, он дублирует колонку описания."""
    return _int(text.split()[0]) if text.strip() else None


def parse_usd(text: str) -> int | None:
    """'14,886 USD' -> 14886. Ноль Copart ставит, когда оценки нет."""
    value = _int(text)
    return value or None


def _lot(row: dict[str, str], line: int) -> Lot:
    sale_date, sale_datetime = parse_sale_date(row["Sale date"])
    state, yard = parse_sale_name(row["Sale name"])
    year = row["Year"].strip()
    return Lot(
        lot=row["Lot #"].strip(),
        lot_url=row["Lot URL"].strip(),
        year=int(year) if year.isdigit() else None,
        make=row["Make"].strip().upper(),
        model=row["Model"].strip().upper(),
        vin=row["VIN"].strip(),
        primary_damage=row["Damage description"].strip().upper(),
        sale_date_raw=row["Sale date"].strip(),
        sale_date=sale_date,
        sale_datetime=sale_datetime,
        sale_name=row["Sale name"].strip(),
        state=state,
        yard=yard,
        title=row["Title code"].strip(),
        odometer=parse_odometer(row["Odometer"]),
        odometer_status=row["Odometer description"].strip(),
        est_retail_usd=parse_usd(row["Est. Retail value"]),
        engine=row["Engine type"].strip(),
        cylinders=row["Cylinders"].strip(),
        row=line,
        raw=dict(row),
    )


def read(path: Path) -> list[Lot]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise SchemaError(f"{path.name}: нет колонок {missing}")
        return [_lot(row, reader.line_num) for row in reader]
