"""Слой cases: исходные таблицы аукциона. Копируются байт в байт и больше не меняются."""

import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from . import lotsearch

AUCTION = "COPART"
MANIFEST = "manifest.json"
NAME_RE = re.compile(r"LotSearchresults_(\d{3,})\.csv")


@dataclass(frozen=True)
class Ingested:
    path: Path
    duplicate: bool  # такой файл уже был принят — повторно не копируем


def day_dir(root: Path, day: date) -> Path:
    return root / "cases" / AUCTION / day.isoformat()


def sale_day(path: Path) -> date:
    """День торгов из самой таблицы. Если дней несколько — пусть укажут явно."""
    days = {lot.sale_date for lot in lotsearch.read(path)}
    if len(days) != 1 or None in days:
        raise ValueError(f"{path.name}: в файле дни {sorted(map(str, days))}, укажите дату явно")
    return days.pop()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest(directory: Path) -> list[dict]:
    path = directory / MANIFEST
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def _save_manifest(directory: Path, entries: list[dict]) -> None:
    tmp = directory / (MANIFEST + ".tmp")
    tmp.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, directory / MANIFEST)


def _next_name(directory: Path) -> str:
    numbers = [int(m[1]) for p in directory.iterdir() if (m := NAME_RE.fullmatch(p.name))]
    return f"LotSearchresults_{max(numbers, default=0) + 1:03d}.csv"


def ingest(source: Path, root: Path, day: date | None = None) -> Ingested:
    lots = lotsearch.read(source)  # заодно проверка формата до копирования
    day = day or sale_day(source)
    directory = day_dir(root, day)
    directory.mkdir(parents=True, exist_ok=True)

    sha = _sha256(source)
    manifest = load_manifest(directory)
    for entry in manifest:
        if entry["sha256"] == sha:
            return Ingested(directory / entry["file"], duplicate=True)

    target = directory / _next_name(directory)
    shutil.copyfile(source, target)
    target.chmod(0o444)
    manifest.append({
        "file": target.name,
        "source_name": source.name,
        "sha256": sha,
        "bytes": target.stat().st_size,
        "rows": len(lots),
        "columns": list(lots[0].raw) if lots else [],
        "ingested_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    _save_manifest(directory, manifest)
    return Ingested(target, duplicate=False)
