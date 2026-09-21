"""Photo tree: photos/<GROUP>/<MAKE>/<YEAR>/<MODEL>/COPART_<lot>/.

The archive is browsed from Windows over a network share, so names are made
Windows-safe: no <>:"/\\|?*, no trailing dot/space, no reserved names.
Upper case, since Windows is case-insensitive.
"""

import re
from pathlib import Path

from .config import Config
from .lotsearch import Lot

PHOTOS = "photos"
LOT_PREFIX = "COPART_"
_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"{p}{i}" for p in ("COM", "LPT") for i in range(1, 10)}


def safe_name(text: str) -> str:
    name = _FORBIDDEN.sub("_", text.upper())
    name = re.sub(r"\s+", " ", name).strip().rstrip(". ")
    if not name:
        return "UNKNOWN"
    if name.split(".")[0] in _RESERVED:
        name += "_"
    return name


def damage_group(lot: Lot, cfg: Config) -> str:
    return cfg.group_for(lot.primary_damage) or cfg.other_group


def lot_dir(root: Path, lot: Lot, cfg: Config) -> Path:
    year = str(lot.year) if lot.year else "UNKNOWN"
    return (root / PHOTOS / damage_group(lot, cfg) / safe_name(lot.make)
            / year / safe_name(lot.model) / f"{LOT_PREFIX}{lot.lot}")


def existing_lot_dirs(root: Path) -> dict[str, Path]:
    """Existing lot folders. If Copart later corrects the make or damage,
    the lot stays where it was first placed instead of being duplicated."""
    base = root / PHOTOS
    if not base.exists():
        return {}
    return {p.name.removeprefix(LOT_PREFIX): p
            for p in base.glob(f"*/*/*/*/{LOT_PREFIX}*") if p.is_dir()}
