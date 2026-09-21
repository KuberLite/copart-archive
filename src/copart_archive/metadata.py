"""metadata.json in a lot folder."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .cases import AUCTION, Source
from .lotsearch import Lot

FILENAME = "metadata.json"
SCHEMA_VERSION = 1


def build(lot: Lot, group: str, source: Source | None) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "auction": AUCTION,
        "lot": lot.lot,
        "vin": lot.vin,  # Copart masks the tail with asterisks; kept as is
        "year": lot.year,
        "make": lot.make,
        "model": lot.model,
        "trim": None,  # not in the CSV export
        "primary_damage": lot.primary_damage,
        "secondary_damage": None,  # not in the CSV export
        "damage_group": group,
        "sale_date": lot.sale_date.isoformat() if lot.sale_date else None,
        "sale_datetime": lot.sale_datetime.isoformat() if lot.sale_datetime else None,
        "location": lot.yard,
        "state": lot.state,
        "sale_name": lot.sale_name,
        "title": lot.title,
        "odometer": lot.odometer,
        "odometer_status": lot.odometer_status,
        "est_retail_usd": lot.est_retail_usd,
        "engine": lot.engine,
        "cylinders": lot.cylinders,
        "lot_url": lot.lot_url,
        "source": {"file": source.file.as_posix(), "row": source.row} if source else None,
        "source_row": lot.raw,
    }


def read(lot_dir: Path) -> dict | None:
    path = lot_dir / FILENAME
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def write(lot_dir: Path, data: dict) -> None:
    """Updates fields from fresh data but keeps what was accumulated before
    (creation date, photo list)."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    previous = read(lot_dir) or {}
    merged = {**previous, **data, "created_at": previous.get("created_at", now), "updated_at": now}
    tmp = lot_dir / (FILENAME + ".tmp")
    tmp.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, lot_dir / FILENAME)
