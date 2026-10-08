import argparse
import csv
import os
from dataclasses import replace
from datetime import date
from pathlib import Path

from . import cases, config, filters, jobs, lotsearch, net, tasks

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
    result = tasks.prepare(args.task, args.root, config.load(),
                           use_filters=args.filter, limit=args.limit)
    print(result.report())
    return 0


def cmd_photos(args: argparse.Namespace) -> int:
    cfg = config.load()
    if args.quality:
        cfg = replace(cfg, photo_quality=args.quality)
    job_plan = jobs.plan(args.file, args.root, cfg, args.filter, args.limit)
    print(job_plan.describe(cfg.photo_quality))
    if args.dry_run:  # оценка ничего не создаёт на диске
        return 0
    if job_plan.warning:
        return 1

    def progress(state: jobs.State) -> None:
        if state.done % 25 == 0 or state.done == state.total:
            print(f"  {state.progress()}")

    state = jobs.Job(job_plan, args.root, cfg, net.Http(delay=args.delay), args.file.name).run(progress)
    print(state.summary or state.error)
    return 0 if state.status == jobs.DONE else 1


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

    p = commands.add_parser("prepare", help="завести папки лотов и metadata.json по файлу")
    p.add_argument("task", type=Path)
    p.add_argument("--filter", action=argparse.BooleanOptionalAction, default=True,
                   help="применять фильтры заказчика (по умолчанию да)")
    p.add_argument("--limit", type=int, help="взять только первые N лотов")
    p.set_defaults(func=cmd_prepare)

    p = commands.add_parser("photos", help="скачать фото лотов из файла подписки или задачи")
    p.add_argument("file", type=Path)
    p.add_argument("--quality", choices=config.PHOTO_QUALITIES, help="по умолчанию из конфига")
    p.add_argument("--filter", action=argparse.BooleanOptionalAction, default=True,
                   help="применять фильтры заказчика (по умолчанию да)")
    p.add_argument("--limit", type=int, help="взять только первые N лотов")
    p.add_argument("--delay", type=float, default=0.5, help="пауза между запросами, сек")
    p.add_argument("--dry-run", action="store_true", help="только оценка объёма")
    p.set_defaults(func=cmd_photos)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
