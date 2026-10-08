"""Photo task: a file with lots sent by the client."""

from collections import Counter
from dataclasses import dataclass, field, replace
from pathlib import Path

from . import cases, filters, layout, lotsearch, metadata, salesdata, taskfile
from .config import Config


@dataclass
class Prepared:
    source: str  # описание входного файла для отчёта
    dirs: list[Path] = field(default_factory=list)
    lots: list[lotsearch.Lot] = field(default_factory=list)
    by_group: Counter[str] = field(default_factory=Counter)
    created: int = 0
    renamed: int = 0  # folders that got the VIN added to their name
    not_in_cases: list[str] = field(default_factory=list)  # placed from the task row
    unplaced: list[str] = field(default_factory=list)  # no make/damage data at all

    def report(self) -> str:
        lines = ([self.source] if self.source else []) + [
            f"Папок лотов: {len(self.dirs)}, новых: {self.created}"
            + (f", добавлен VIN в имя: {self.renamed}" if self.renamed else "")]
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


Found = list[tuple[lotsearch.Lot | None, cases.Source | None, str]]


def read_lots(path: Path, root: Path) -> tuple[str, Found]:
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


def select(found: Found, cfg: Config, use_filters: bool, limit: int | None) -> tuple[Found, str]:
    """Narrows what will be prepared. A subscription file holds tens of thousands
    of lots, so folders must not be created for all of them."""
    notes = []
    if use_filters:
        known = [item for item in found if item[0] is not None]
        unknown = [item for item in found if item[0] is None]  # reported as unplaced
        result = filters.apply([item[0] for item in known], cfg)
        passed = {lot.lot for lot in result.passed}
        found = [item for item in known if item[0].lot in passed] + unknown
        notes.append(result.report())
    if limit is not None and len(found) > limit:
        notes.append(f"Ограничение: берём первые {limit} из {len(found)}")
        found = found[:limit]
    return found, "\n".join(notes)


def _name_with_vin(lot_dir: Path, lot: lotsearch.Lot, result: "Prepared") -> Path:
    """A folder made before its VIN was known gets the VIN added to its name.
    The folder stays where it is, and a VIN once in a name is never taken out:
    a later website export with a masked VIN must not rename it back."""
    wanted = layout.folder_name(lot)
    if (lot_dir.exists() and lot_dir.name != wanted and wanted != f"{layout.LOT_PREFIX}{lot.lot}"
            and not (lot_dir.parent / wanted).exists()):
        renamed = lot_dir.with_name(wanted)
        lot_dir.rename(renamed)
        result.renamed += 1
        return renamed
    return lot_dir


def prepare_lots(found: Found, root: Path, cfg: Config, source: str = "") -> Prepared:
    """Creates lot folders and metadata.json. Writes to disk, so an estimate must
    not call it; damage outside the groups goes to Other."""
    existing = layout.existing_lot_dirs(root)
    result = Prepared(source=source)

    for lot, source, lot_number in found:
        if lot is None:
            result.unplaced.append(lot_number)
            continue
        if source is None and lot.source != "salesdata":
            result.not_in_cases.append(lot_number)
        lot_dir = existing.get(lot.lot) or layout.lot_dir(root, lot, cfg)
        lot_dir = _name_with_vin(lot_dir, lot, result)
        if not lot_dir.exists():
            lot_dir.mkdir(parents=True)
            result.created += 1
        group = lot_dir.relative_to(root / layout.PHOTOS).parts[0]
        metadata.write(lot_dir, metadata.build(lot, group, source))
        result.dirs.append(lot_dir)
        result.lots.append(lot)
        result.by_group[group] += 1
    return result


def prepare(path: Path, root: Path, cfg: Config, use_filters: bool = False,
            limit: int | None = None) -> Prepared:
    header, found = read_lots(path, root)
    found, notes = select(found, cfg, use_filters, limit)
    return prepare_lots(found, root, cfg, "\n".join(p for p in (header, notes) if p))
