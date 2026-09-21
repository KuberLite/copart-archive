"""Photo task: a file with lots sent by the client."""

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from . import cases, layout, lotsearch, metadata
from .config import Config


@dataclass
class Prepared:
    dirs: list[Path] = field(default_factory=list)
    by_group: Counter[str] = field(default_factory=Counter)
    created: int = 0
    not_in_cases: list[str] = field(default_factory=list)

    def report(self) -> str:
        lines = [f"Лотов: {len(self.dirs)}, новых папок: {self.created}"]
        lines += [f"  {n:4}  {g}" for g, n in sorted(self.by_group.items())]
        if self.not_in_cases:
            lines.append(f"Нет в cases/ ({len(self.not_in_cases)}): {', '.join(self.not_in_cases)}")
        return "\n".join(lines)


def prepare(task_file: Path, root: Path, cfg: Config) -> Prepared:
    """Creates lot folders and metadata.json. Filters are not applied:
    whatever the client sent is taken; damage outside groups goes to Other."""
    lots = lotsearch.read(task_file)
    sources = cases.lot_sources(root)
    existing = layout.existing_lot_dirs(root)
    result = Prepared()

    for lot in lots:
        lot_dir = existing.get(lot.lot) or layout.lot_dir(root, lot, cfg)
        if not lot_dir.exists():
            lot_dir.mkdir(parents=True)
            result.created += 1
        group = lot_dir.relative_to(root / layout.PHOTOS).parts[0]
        source = sources.get(lot.lot)
        if source is None:
            result.not_in_cases.append(lot.lot)
        metadata.write(lot_dir, metadata.build(lot, group, source))
        result.dirs.append(lot_dir)
        result.by_group[group] += 1
    return result
