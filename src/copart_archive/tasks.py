"""Photo task: a file with lots sent by the client."""

from collections import Counter
from dataclasses import dataclass, field, replace
from pathlib import Path

from . import cases, layout, lotsearch, metadata, salesdata, taskfile
from .config import Config


@dataclass
class Prepared:
    source: str  # описание входного файла для отчёта
    dirs: list[Path] = field(default_factory=list)
    lots: list[lotsearch.Lot] = field(default_factory=list)
    by_group: Counter[str] = field(default_factory=Counter)
    created: int = 0
    not_in_cases: list[str] = field(default_factory=list)  # placed from the task row
    unplaced: list[str] = field(default_factory=list)  # no make/damage data at all

    def report(self) -> str:
        lines = [self.source, f"Папок лотов: {len(self.dirs)}, новых: {self.created}"]
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


def read_lots(path: Path, root: Path) -> tuple[str, list[tuple[lotsearch.Lot | None, cases.Source | None, str]]]:
    """Lots of an input file: a Sales Data subscription file brings everything with
    it, a task file brings lot numbers whose data is looked up in cases/."""
    if salesdata.looks_like(path):
        lots = salesdata.read(path)
        return f"Файл {path.name} (Sales Data): лотов {len(lots)}", [(l, None, l.lot) for l in lots]

    task = taskfile.read(path)
    index = cases.lot_index(root, set(task.lots))
    found = []
    for number in task.lots:
        lot, source = _lot_data(number, task, index)
        found.append((lot, source, number))
    return task.report(), found


def prepare(path: Path, root: Path, cfg: Config) -> Prepared:
    """Creates lot folders and metadata.json. Filters are not applied:
    whatever the client sent is taken; damage outside groups goes to Other."""
    header, found = read_lots(path, root)
    existing = layout.existing_lot_dirs(root)
    result = Prepared(source=header)

    for lot, source, lot_number in found:
        if lot is None:
            result.unplaced.append(lot_number)
            continue
        if source is None and lot.source != "salesdata":
            result.not_in_cases.append(lot_number)
        lot_dir = existing.get(lot.lot) or layout.lot_dir(root, lot, cfg)
        if not lot_dir.exists():
            lot_dir.mkdir(parents=True)
            result.created += 1
        group = lot_dir.relative_to(root / layout.PHOTOS).parts[0]
        metadata.write(lot_dir, metadata.build(lot, group, source))
        result.dirs.append(lot_dir)
        result.lots.append(lot)
        result.by_group[group] += 1
    return result
