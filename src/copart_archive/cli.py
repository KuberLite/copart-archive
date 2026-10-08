import argparse
import csv
import os
from dataclasses import replace
from datetime import date
from pathlib import Path

from . import cases, config, filters, lotsearch, net, photos, tasks

DEFAULT_ROOT = Path(os.environ.get("COPART_ARCHIVE_ROOT", "archive"))


def cmd_ingest(args: argparse.Namespace) -> int:
    for source in args.csv:
        result = cases.ingest(source, args.root, args.date)
        status = "уже был" if result.duplicate else "принят"
        print(f"{source.name} -> {result.path} ({status})")
    return 0


def cmd_filter(args: argparse.Namespace) -> int:
    cfg = config.load()
    lots = [lot for path in args.csv for lot in lotsearch.read(path)]
    result = filters.apply(lots, cfg)
    print(result.report())
    if args.out:
        write_lots(args.out, result.passed)
        print(f"Записано {len(result.passed)} строк: {args.out}")
    return 0


def cmd_prepare(args: argparse.Namespace) -> int:
    result = tasks.prepare(args.task, args.root, config.load())
    print(result.report())
    return 0


def cmd_photos(args: argparse.Namespace) -> int:
    cfg = config.load()
    if args.quality:
        cfg = replace(cfg, photo_quality=args.quality)
    prepared = tasks.prepare(args.file, args.root, cfg)
    print(prepared.report())

    pairs = list(zip(prepared.dirs, prepared.lots))[:args.limit]
    estimate = photos.estimate_bytes(len(pairs), cfg.photo_quality)
    free = photos.free_bytes(args.root)
    print(f"К загрузке {len(pairs)} лотов, качество {cfg.photo_quality}: "
          f"≈{photos.human(estimate)}, свободно {photos.human(free)}")
    if args.dry_run:
        return 0
    warning = photos.space_warning(args.root, len(pairs), cfg.photo_quality)
    if warning:
        print(warning)
        return 1

    http = net.Http(delay=args.delay)
    result = photos.Result()
    for done, (lot_dir, lot) in enumerate(pairs, start=1):
        result.lots.append(photos.sync_lot(lot_dir, lot, cfg, http))
        if done % 25 == 0 or done == len(pairs):
            print(f"  {done}/{len(pairs)} лотов, {photos.human(result.bytes_saved)}")
    print(result.report())
    return 0


def write_lots(path: Path, lots: list[lotsearch.Lot]) -> None:
    """Rows in the original export format, so the file can be used as a photo task."""
    columns = list(lots[0].raw) if lots else list(lotsearch.REQUIRED_COLUMNS)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(lot.raw for lot in lots)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="copart-archive")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="корень архива")
    commands = parser.add_subparsers(dest="command", required=True)

    p = commands.add_parser("ingest", help="положить CSV аукциона в cases/")
    p.add_argument("csv", nargs="+", type=Path)
    p.add_argument("--date", type=date.fromisoformat, help="день торгов, если в файле их несколько")
    p.set_defaults(func=cmd_ingest)

    p = commands.add_parser("filter", help="применить фильтры заказчика к CSV")
    p.add_argument("csv", nargs="+", type=Path)
    p.add_argument("--out", type=Path, help="сохранить прошедшие лоты в CSV")
    p.set_defaults(func=cmd_filter)

    p = commands.add_parser("prepare", help="завести папки лотов и metadata.json по файлу-задаче")
    p.add_argument("task", type=Path)
    p.set_defaults(func=cmd_prepare)

    p = commands.add_parser("photos", help="скачать фото лотов из файла подписки или задачи")
    p.add_argument("file", type=Path)
    p.add_argument("--quality", choices=config.PHOTO_QUALITIES, help="по умолчанию из конфига")
    p.add_argument("--limit", type=int, help="взять только первые N лотов")
    p.add_argument("--delay", type=float, default=0.5, help="пауза между запросами, сек")
    p.add_argument("--dry-run", action="store_true", help="только оценка объёма")
    p.set_defaults(func=cmd_photos)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
