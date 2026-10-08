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

The main input is the Sales Data subscription file: it carries the full VIN, the
trim, the secondary damage and an "Image URL" pointing at Copart's image API,
which is where the photos come from.

```bash
# estimate first: how many lots and how much disk
.venv/bin/copart-archive photos SalesData.csv --dry-run

# lot folders, metadata.json and every photo of each lot
.venv/bin/copart-archive photos SalesData.csv

# folders and metadata only, no photos
.venv/bin/copart-archive prepare SalesData.csv
```

A website CSV export works too, through the older route:

```bash
# keep the auction table in cases/ (copied as is; the day comes from Sale date)
.venv/bin/copart-archive ingest LotSearchresults.csv

# client filters: a report and a task file with the lots that passed
.venv/bin/copart-archive filter archive/cases/COPART/2026-09-18/*.csv --out task.csv

# lot folders from a task file (xlsx or csv, needs "Lot #" or "Lot URL")
.venv/bin/copart-archive prepare task.csv
```

Settings are taken from `COPART_ARCHIVE_CONFIG`, else `./config/archive.toml`.
Deployment notes are in [deploy/README.md](deploy/README.md).

Photos live only while the lot is in Copart's inventory — after the sale the
image API answers 404, and such lots are marked `photos_status: gone`.

The archive root is `./archive`; override with `--root` or `COPART_ARCHIVE_ROOT`.
Filters and damage groups live in `config/archive.toml`.
