"""Downloading lot photos into the lot folders.

Photos live only while the lot is in Copart's inventory: once it is sold the
image API answers 404, so a lot is either taken now or lost.
"""

import hashlib
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from . import images, metadata, net
from .config import Config
from .lotsearch import Lot

# измеренные средние: обычное фото ~150 КБ, HD ~250 КБ, 12 снимков на лот
AVERAGE_KB = {"thumbnail": 6, "full": 150, "high_res": 250}
AVERAGE_PHOTOS = 12
RESERVE_BYTES = 2 * 1024**3  # не занимаем диск под ноль

OK, GONE, EMPTY, ERROR = "ok", "gone", "empty", "error"


@dataclass
class LotResult:
    lot: str
    status: str = OK
    saved: int = 0
    skipped: int = 0
    bytes_saved: int = 0
    error: str | None = None


@dataclass
class Result:
    lots: list[LotResult] = field(default_factory=list)

    @property
    def bytes_saved(self) -> int:
        return sum(l.bytes_saved for l in self.lots)

    def report(self) -> str:
        by_status = {s: [l for l in self.lots if l.status == s] for s in (OK, GONE, EMPTY, ERROR)}
        lines = [
            f"Лотов обработано: {len(self.lots)}",
            f"  скачано фото: {sum(l.saved for l in self.lots)} ({self.bytes_saved / 1024**2:.0f} МБ)",
            f"  уже были: {sum(l.skipped for l in self.lots)}",
        ]
        if by_status[GONE]:
            lines.append(f"  нет в инвентаре (проданы): {len(by_status[GONE])}")
        if by_status[EMPTY]:
            lines.append(f"  без фотографий: {len(by_status[EMPTY])}")
        for failed in by_status[ERROR][:5]:
            lines.append(f"  ошибка {failed.lot}: {failed.error}")
        if len(by_status[ERROR]) > 5:
            lines.append(f"  ещё ошибок: {len(by_status[ERROR]) - 5}")
        return "\n".join(lines)


def estimate_bytes(lots: int, quality: str) -> int:
    return lots * AVERAGE_PHOTOS * AVERAGE_KB[quality] * 1024


def free_bytes(root: Path) -> int:
    existing = root
    while not existing.exists() and existing != existing.parent:
        existing = existing.parent
    return shutil.disk_usage(existing).free


def space_warning(root: Path, lots: int, quality: str) -> str | None:
    """Текст предупреждения, если места не хватит; иначе None."""
    need, free = estimate_bytes(lots, quality), free_bytes(root)
    if need + RESERVE_BYTES <= free:
        return None
    return (f"Не хватает места: нужно ≈{need / 1024**3:.1f} ГБ, свободно {free / 1024**3:.1f} ГБ "
            f"(с запасом {RESERVE_BYTES / 1024**3:.0f} ГБ)")


def human(size: int) -> str:
    return f"{size / 1024**3:.1f} ГБ" if size >= 1024**3 else f"{size / 1024**2:.0f} МБ"


def sync_lot(lot_dir: Path, lot: Lot, cfg: Config, http: net.Http) -> LotResult:
    """Downloads what is missing. A file already in place is kept, unless the
    photo at that position has changed: Copart may insert a new shot in the
    middle, which shifts the numbering of everything after it."""
    result = LotResult(lot=lot.lot)
    lot_dir.mkdir(parents=True, exist_ok=True)
    try:
        found = images.fetch(lot.lot, cfg.photo_quality, http, lot.image_api_url)
    except net.NotFound:
        result.status = GONE
        metadata.write(lot_dir, {"photos_status": GONE})
        return result
    except OSError as error:
        result.status, result.error = ERROR, str(error)
        return result

    if not found:
        result.status = EMPTY
        metadata.write(lot_dir, {"photos_status": EMPTY})
        return result

    known = {p.get("file"): p.get("url") for p in (metadata.read(lot_dir) or {}).get("photos") or []}
    entries = []
    for number, photo in enumerate(found, start=1):
        target = lot_dir / f"{number:02d}.jpg"
        unchanged = known.get(target.name, photo.url) == photo.url
        try:
            if target.exists() and target.stat().st_size and unchanged:
                result.skipped += 1
            else:
                size = http.download(photo.url, target)
                result.saved += 1
                result.bytes_saved += size
        except OSError as error:
            result.status, result.error = ERROR, str(error)
            continue
        body = target.read_bytes()
        entries.append({"file": target.name, "sequence": photo.sequence, "url": photo.url,
                        "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()})

    metadata.write(lot_dir, {"photos": entries, "photos_quality": cfg.photo_quality,
                             "photos_status": result.status, "photos_count": len(entries)})
    return result
