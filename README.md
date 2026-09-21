# copart-archive

Photo archive of Copart lots.

- `archive/cases/COPART/<date>/` — raw auction tables (never modified)
- `archive/photos/<DAMAGE>/<MAKE>/<YEAR>/<MODEL>/COPART_<lot>/` — photos + `metadata.json`

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

## Usage

```bash
# 1. put an auction table into cases/ (copied as is; the day comes from Sale date)
.venv/bin/copart-archive ingest LotSearchresults.csv

# 2. client filters: a report and a task file with the lots that passed
.venv/bin/copart-archive filter archive/cases/COPART/2026-09-18/*.csv --out task.csv

# 3. lot folders and metadata.json from a task file
.venv/bin/copart-archive prepare task.csv
```

The archive root is `./archive`; override with `--root` or `COPART_ARCHIVE_ROOT`.
Filters and damage groups live in `config/archive.toml`.
