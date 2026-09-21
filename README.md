# copart-archive

Архив фотографий лотов Copart.

- `archive/cases/COPART/<дата>/` — исходные таблицы аукционов (RAW, не изменяются)
- `archive/photos/<ПОВРЕЖДЕНИЕ>/<МАРКА>/<ГОД>/<МОДЕЛЬ>/COPART_<лот>/` — фото + `metadata.json`

## Установка

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

## Работа

```bash
# 1. таблицу аукциона — в cases/ (копия как есть, день берётся из Sale date)
.venv/bin/copart-archive ingest LotSearchresults.csv

# 2. фильтры заказчика: отчёт и файл-задача с прошедшими лотами
.venv/bin/copart-archive filter archive/cases/COPART/2026-09-18/*.csv --out task.csv

# 3. папки лотов и metadata.json по файлу-задаче
.venv/bin/copart-archive prepare task.csv
```

Корень архива — `./archive`, меняется через `--root` или `COPART_ARCHIVE_ROOT`.
Фильтры и группы повреждений — `config/archive.toml`.
