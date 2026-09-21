import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "archive.toml"
PHOTO_QUALITIES = ("thumbnail", "full", "high_res")


@dataclass(frozen=True)
class Config:
    year_min: int
    makes: frozenset[str]
    damage_groups: dict[str, frozenset[str]]
    other_group: str
    photo_quality: str

    def group_for(self, damage: str) -> str | None:
        """Группа для значения повреждения Copart, None — если вне групп."""
        damage = damage.strip().upper()
        for group, values in self.damage_groups.items():
            if damage in values:
                return group
        return None


def load(path: Path = DEFAULT_PATH) -> Config:
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    quality = raw["photos"]["quality"]
    if quality not in PHOTO_QUALITIES:
        raise ValueError(f"photos.quality: {quality!r}, ожидается одно из {PHOTO_QUALITIES}")

    return Config(
        year_min=raw["filters"]["year_min"],
        makes=frozenset(m.upper() for m in raw["filters"]["makes"]),
        damage_groups={
            group: frozenset(v.upper() for v in values)
            for group, values in raw["damage_groups"].items()
        },
        other_group=raw["layout"]["other_group"],
        photo_quality=quality,
    )
