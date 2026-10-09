import json
import os
import tomllib
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

CONFIG_NAME = Path("config") / "archive.toml"
# When the package is installed (a container, a venv) the repo layout is gone,
# so the file is looked up by the variable or next to where the command is run.
REPO_PATH = Path(__file__).resolve().parents[2] / CONFIG_NAME
PHOTO_QUALITIES = ("thumbnail", "full", "high_res")
# what the client changes from the bot lives next to the archive, outside the
# image, so it survives rebuilds; config/archive.toml stays the defaults
OVERRIDES = Path("state") / "filters.json"


@dataclass(frozen=True)
class Config:
    year_min: int
    makes: frozenset[str]
    vehicle_types: frozenset[str]
    damage_groups: dict[str, frozenset[str]]  # the groups switched on — the filter
    other_group: str
    photo_quality: str
    damage_catalog: dict[str, frozenset[str]] | None = None  # every known group

    @property
    def catalog(self) -> dict[str, frozenset[str]]:
        return self.damage_catalog or self.damage_groups

    def group_for(self, damage: str) -> str | None:
        """Switched-on group for a Copart damage value; None means the lot is filtered out."""
        return _lookup(self.damage_groups, damage)

    def folder_for(self, damage: str) -> str:
        """Where a lot goes in photos/. Uses the whole catalog, so a hail lot taken
        without filters still lands in Hail, not in Other."""
        return _lookup(self.catalog, damage) or self.other_group


def _lookup(groups: dict[str, frozenset[str]], damage: str) -> str | None:
    damage = damage.strip().upper()
    return next((group for group, values in groups.items() if damage in values), None)


def find() -> Path:
    """COPART_ARCHIVE_CONFIG, then ./config/archive.toml, then the repo copy."""
    from_env = os.environ.get("COPART_ARCHIVE_CONFIG")
    if from_env:
        return Path(from_env)
    here = Path.cwd() / CONFIG_NAME
    return here if here.exists() else REPO_PATH


def load(path: Path | None = None) -> Config:
    path = path or find()
    if not path.exists():
        raise FileNotFoundError(
            f"нет файла настроек {path}, задайте COPART_ARCHIVE_CONFIG")
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    quality = raw["photos"]["quality"]
    if quality not in PHOTO_QUALITIES:
        raise ValueError(f"photos.quality: {quality!r}, ожидается одно из {PHOTO_QUALITIES}")

    # older configs had only [damage_groups], all of them on
    catalog = {group: frozenset(v.upper() for v in values)
               for group, values in (raw.get("damage_catalog") or raw["damage_groups"]).items()}
    enabled = raw["filters"].get("damage_groups", list(catalog))
    unknown = [g for g in enabled if g not in catalog]
    if unknown:
        raise ValueError(f"filters.damage_groups: нет таких групп в каталоге: {unknown}")

    return Config(
        year_min=raw["filters"]["year_min"],
        makes=frozenset(m.upper() for m in raw["filters"]["makes"]),
        vehicle_types=frozenset(t.upper() for t in raw["filters"].get("vehicle_types", ())),
        damage_groups={g: catalog[g] for g in catalog if g in enabled},
        other_group=raw["layout"]["other_group"],
        photo_quality=quality,
        damage_catalog=catalog,
    )


def overrides_path(root: Path) -> Path:
    return root / OVERRIDES


def read_overrides(root: Path) -> dict:
    path = overrides_path(root)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def with_overrides(base: Config, root: Path) -> Config:
    """The defaults with the client's changes on top. A group the catalog no
    longer has is dropped instead of failing — the settings file outlives code."""
    data = read_overrides(root)
    changes = {}
    if "year_min" in data:
        changes["year_min"] = int(data["year_min"])
    if "makes" in data:
        changes["makes"] = frozenset(str(m).strip().upper() for m in data["makes"] if str(m).strip())
    if "damage_groups" in data:
        enabled = set(data["damage_groups"])
        changes["damage_groups"] = {g: v for g, v in base.catalog.items() if g in enabled}
    return replace(base, **changes)


def load_for(root: Path, path: Path | None = None) -> Config:
    return with_overrides(load(path), root)


def save_overrides(root: Path, cfg: Config, changed_by: int | str | None = None) -> None:
    path = overrides_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "year_min": cfg.year_min,
        "makes": sorted(cfg.makes),
        "damage_groups": list(cfg.damage_groups),
        "changed_by": changed_by,
        "changed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def reset_overrides(root: Path) -> None:
    overrides_path(root).unlink(missing_ok=True)
