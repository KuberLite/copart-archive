import argparse
import csv
from pathlib import Path

from . import config, filters, lotsearch


def cmd_filter(args: argparse.Namespace) -> int:
    cfg = config.load()
    lots = [lot for path in args.csv for lot in lotsearch.read(path)]
    result = filters.apply(lots, cfg)
    print(result.report())
    if args.out:
        write_lots(args.out, result.passed)
        print(f"Записано {len(result.passed)} строк: {args.out}")
    return 0


def write_lots(path: Path, lots: list[lotsearch.Lot]) -> None:
    """Строки в исходном формате выгрузки — такой файл можно отдать в задачу на фото."""
    columns = list(lots[0].raw) if lots else list(lotsearch.REQUIRED_COLUMNS)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(lot.raw for lot in lots)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="copart-archive")
    commands = parser.add_subparsers(dest="command", required=True)

    p = commands.add_parser("filter", help="применить фильтры заказчика к CSV")
    p.add_argument("csv", nargs="+", type=Path)
    p.add_argument("--out", type=Path, help="сохранить прошедшие лоты в CSV")
    p.set_defaults(func=cmd_filter)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
