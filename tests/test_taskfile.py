from pathlib import Path

import openpyxl
import pytest

from copart_archive import taskfile

SAMPLE = Path(__file__).parent / "fixtures" / "lotsearch_sample.csv"


def sample_rows():
    import csv
    with open(SAMPLE, encoding="utf-8-sig", newline="") as f:
        return list(csv.reader(f))


def make_xlsx(path, sheets):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for title, rows in sheets.items():
        ws = wb.create_sheet(title)
        for row in rows:
            ws.append(row)
    wb.save(path)


def test_copart_csv():
    task = taskfile.read(SAMPLE)
    assert task.total_rows == 11
    assert task.lots[0] == "64557536"
    assert task.rows["64557536"]["Make"] == "INFINITI"


def test_xlsx_prefers_all_lots_sheet_and_dedupes(tmp_path):
    header, *rows = sample_rows()
    # like the client's file: numbers stored as numbers, a stats sheet first
    typed = [[int(v) if v.isdigit() else v for v in r] for r in rows]
    path = tmp_path / "task.xlsx"
    make_xlsx(path, {
        "Статистика": [["Марка", "Всего"], ["FORD", 1]],
        "ALL_LOTS": [header, *typed, typed[0], [None] * len(header)],
    })
    task = taskfile.read(path)
    assert task.sheet == "ALL_LOTS"
    assert (task.total_rows, len(task.lots), task.duplicates) == (12, 11, 1)
    assert task.lots[0] == "64557536"
    assert task.rows["64557536"]["Year"] == "2019"


def test_xlsx_without_all_lots_uses_first_sheet(tmp_path):
    path = tmp_path / "task.xlsx"
    make_xlsx(path, {"Лист1": [["Lot #"], [64557536.0]]})
    task = taskfile.read(path)
    assert task.sheet == "Лист1" and task.lots == ["64557536"]


def test_russian_excel_csv(tmp_path):
    path = tmp_path / "task.csv"
    path.write_bytes("Lot #;Марка\n64557536;INFINITI\n".encode("cp1251"))
    task = taskfile.read(path)
    assert task.lots == ["64557536"]
    assert task.rows["64557536"]["Марка"] == "INFINITI"


def test_lot_from_url_only(tmp_path):
    path = tmp_path / "task.csv"
    path.write_text("Lot URL\nhttps://www.copart.com/lot/62398996\n", encoding="utf-8")
    assert taskfile.read(path).lots == ["62398996"]


def test_invalid_rows_are_reported(tmp_path):
    path = tmp_path / "task.csv"
    path.write_text("Lot #\n64557536\nитого\n", encoding="utf-8")
    task = taskfile.read(path)
    assert task.lots == ["64557536"]
    assert task.invalid == [(3, "итого")]
    assert "без номера лота: 1" in task.report()


def test_no_lot_column(tmp_path):
    path = tmp_path / "task.csv"
    path.write_text("Make\nFORD\n", encoding="utf-8")
    with pytest.raises(taskfile.TaskFileError):
        taskfile.read(path)


def test_unsupported_extension(tmp_path):
    path = tmp_path / "task.pdf"
    path.write_bytes(b"%PDF")
    with pytest.raises(taskfile.TaskFileError):
        taskfile.read(path)
