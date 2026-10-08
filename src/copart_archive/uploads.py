"""Files the client sends through the bot.

Each one is kept in cases/ exactly as received — the raw source the archive was
built from — and, if it is a zip, the table inside is unpacked for processing.
Telegram hands bots files of up to 20 MB, so a large export arrives zipped.
"""

import hashlib
import json
import os
import re
import shutil
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path, PurePosixPath

from .cases import AUCTION, MANIFEST, load_manifest
from .tabular import CSV_SUFFIXES, XLSX_SUFFIXES, FormatError

MSK = timezone(timedelta(hours=3))  # the client's day; Moscow has no DST
TABLE_SUFFIXES = XLSX_SUFFIXES + CSV_SUFFIXES
MAX_UNPACKED = 512 * 1024**2  # a zip that unpacks bigger than this is refused
NAME_RE = re.compile(r"Upload_(\d{3,})\.")


@dataclass(frozen=True)
class Stored:
    path: Path  # the raw file in cases/
    table: Path  # what to read: the same file, or the table unpacked from a zip
    duplicate: bool  # the same bytes were stored before


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _find_stored(root: Path, sha: str) -> Path | None:
    for manifest in (root / "cases" / AUCTION).glob(f"*/{MANIFEST}"):
        for entry in load_manifest(manifest.parent):
            if entry.get("sha256") == sha:
                return manifest.parent / entry["file"]
    return None


def unpack(archive: Path, work: Path) -> Path:
    """The single table inside a zip, extracted to `work`. Names inside the zip
    are not trusted: only the base name is used, so nothing lands outside."""
    try:
        zf = zipfile.ZipFile(archive)
    except zipfile.BadZipFile as error:
        raise FormatError(f"{archive.name}: архив повреждён") from error
    with zf:
        tables = [i for i in zf.infolist()
                  if not i.is_dir() and not PurePosixPath(i.filename).name.startswith(".")
                  and "__MACOSX" not in i.filename
                  and PurePosixPath(i.filename).suffix.lower() in TABLE_SUFFIXES]
        if len(tables) != 1:
            raise FormatError(f"{archive.name}: в архиве должна быть одна таблица (.xlsx или .csv), "
                              f"найдено {len(tables)}")
        info = tables[0]
        if info.file_size > MAX_UNPACKED:
            raise FormatError(f"{archive.name}: таблица в архиве больше {MAX_UNPACKED // 1024**2} МБ")
        work.mkdir(parents=True, exist_ok=True)
        target = work / PurePosixPath(info.filename).name
        with zf.open(info) as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)
        return target


def store(source: Path, root: Path, name: str | None = None, received: date | None = None) -> Stored:
    """Keeps the file in cases/COPART/<day>/ under a numbered name and returns
    the table to process. The same file sent twice is stored once."""
    name = name or source.name
    suffix = PurePosixPath(name).suffix.lower()
    if suffix not in TABLE_SUFFIXES + (".zip",):
        raise FormatError(f"{name}: нужен .xlsx, .csv или .zip")

    sha = _sha256(source)
    stored = _find_stored(root, sha)
    duplicate = stored is not None
    if stored is None:
        day = received or datetime.now(MSK).date()
        directory = root / "cases" / AUCTION / day.isoformat()
        directory.mkdir(parents=True, exist_ok=True)
        # the next number after the largest, so a deleted file is never overwritten
        numbers = [int(m[1]) for p in directory.iterdir() if (m := NAME_RE.match(p.name))]
        number = max(numbers, default=0) + 1
        stored = directory / f"Upload_{number:03d}{suffix}"
        shutil.copyfile(source, stored)
        stored.chmod(0o444)
        manifest = load_manifest(directory)
        manifest.append({"file": stored.name, "source_name": name, "sha256": sha,
                         "bytes": stored.stat().st_size,
                         "received_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        tmp = directory / (MANIFEST + ".tmp")
        tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, directory / MANIFEST)

    table = unpack(stored, root / "work" / sha[:16]) if suffix == ".zip" else stored
    return Stored(path=stored, table=table, duplicate=duplicate)
