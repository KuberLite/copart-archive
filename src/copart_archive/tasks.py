"""Photo task: a file with lots sent by the client."""

from collections import Counter
from dataclasses import dataclass, field, replace
from pathlib import Path

from . import cases, layout, lotsearch, metadata, taskfile
from .config import Config


@dataclass
class Prepared:
    task: taskfile.TaskFile
    dirs: list[Path] = field(default_factory=list)
    by_group: Counter[str] = field(default_factory=Counter)
    created: int = 0
    not_in_cases: list[str] = field(default_factory=list)  # placed from the task row
    unplaced: list[str] = field(default_factory=list)  # no make/damage data at all

    def report(self) -> str:
        lines = [self.task.report(), f"Папок лотов: {len(self.dirs)}, новых: {self.created}"]
        lines += [f"  {n:5}  {g}" for g, n in sorted(self.by_group.items())]
        if self.not_in_cases:
            lines.append(f"Нет в cases/, данные взяты из файла: {len(self.not_in_cases)}")
        if self.unplaced:
            sample = ", ".join(self.unplaced[:10])
            lines.append(f"Нет данных о лоте, пропущено: {len(self.unplaced)} ({sample})")
        return "\n".join(lines)


def _lot_data(lot: str, task: taskfile.TaskFile, index) -> tuple[lotsearch.Lot | None, cases.Source | None]:
    if lot in index:
        source, data = index[lot]
        return data, source
    row = task.rows[lot]
    if not lotsearch.missing_columns(row):
        # the number may have come from Lot URL while "Lot #" is blank
        return replace(lotsearch.from_row(row, 0), lot=lot), None
    return None, None


def prepare(task_path: Path, root: Path, cfg: Config) -> Prepared:
    """Creates lot folders and metadata.json. Filters are not applied:
    whatever the client sent is taken; damage outside groups goes to Other.
    Lot data comes from cases/ when available, otherwise from the task row."""
    task = taskfile.read(task_path)
    index = cases.lot_index(root, set(task.lots))
    existing = layout.existing_lot_dirs(root)
    result = Prepared(task=task)

    for lot_number in task.lots:
        lot, source = _lot_data(lot_number, task, index)
        if lot is None:
            result.unplaced.append(lot_number)
            continue
        if source is None:
            result.not_in_cases.append(lot_number)
        lot_dir = existing.get(lot.lot) or layout.lot_dir(root, lot, cfg)
        if not lot_dir.exists():
            lot_dir.mkdir(parents=True)
            result.created += 1
        group = lot_dir.relative_to(root / layout.PHOTOS).parts[0]
        metadata.write(lot_dir, metadata.build(lot, group, source))
        result.dirs.append(lot_dir)
        result.by_group[group] += 1
    return result
