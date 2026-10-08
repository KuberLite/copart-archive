"""A photo download as a job: planned, run in the background, stoppable, and
recorded on disk so its status survives a restart. Used by the CLI and the bot."""

import json
import os
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import net, photos, tasks
from .config import Config

STATE_FILE = Path("state") / "job.json"
RUNNING, DONE, STOPPED, FAILED, REFUSED = "running", "done", "stopped", "failed", "refused"
INTERRUPTED = "interrupted"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Plan:
    """What a file would give: the lots to take and what they would cost."""
    found: tasks.Found
    header: str
    notes: str
    count: int
    estimate: int
    free: int
    warning: str | None

    def describe(self, quality: str) -> str:
        lines = [line for line in (self.header, self.notes) if line]
        lines.append(f"К загрузке {self.count} лотов, качество {quality}: "
                     f"≈{photos.human(self.estimate)}, свободно {photos.human(self.free)}")
        if self.warning:
            lines.append(self.warning)
        return "\n".join(lines)


def plan(path: Path, root: Path, cfg: Config, use_filters: bool = True,
         limit: int | None = None) -> Plan:
    """Reads and selects only — nothing is written."""
    header, found = tasks.read_lots(path, root)
    found, notes = tasks.select(found, cfg, use_filters, limit)
    count = sum(1 for lot, _, _ in found if lot is not None)
    return Plan(found=found, header=header, notes=notes, count=count,
                estimate=photos.estimate_bytes(count, cfg.photo_quality),
                free=photos.free_bytes(root),
                warning=photos.space_warning(root, count, cfg.photo_quality))


@dataclass
class State:
    file: str
    status: str = RUNNING
    total: int = 0
    done: int = 0
    photos: int = 0
    bytes_saved: int = 0
    started_at: str = field(default_factory=_now)
    finished_at: str | None = None
    summary: str | None = None
    error: str | None = None

    def progress(self) -> str:
        return f"{self.done}/{self.total} лотов, {self.photos} фото, {photos.human(self.bytes_saved)}"


def state_path(root: Path) -> Path:
    return root / STATE_FILE


def last_state(root: Path) -> State | None:
    path = state_path(root)
    if not path.exists():
        return None
    return State(**json.loads(path.read_text(encoding="utf-8")))


def mark_interrupted(root: Path) -> State | None:
    """Called at start-up: a job recorded as running cannot be running any more —
    the process that ran it is gone. Rerunning the file finishes it."""
    state = last_state(root)
    if state and state.status == RUNNING:
        state.status, state.finished_at = INTERRUPTED, _now()
        _save(root, state)
        return state
    return None


def _save(root: Path, state: State) -> None:
    path = state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(asdict(state), ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


class Job:
    def __init__(self, job_plan: Plan, root: Path, cfg: Config, http: net.Http, name: str):
        self.plan, self.root, self.cfg, self.http = job_plan, root, cfg, http
        self.state = State(file=name, total=job_plan.count)
        self._stop = threading.Event()

    def stop(self) -> None:
        """Asks the job to finish after the current lot; what is on disk stays."""
        self._stop.set()

    def run(self, on_progress: Callable[[State], None] | None = None) -> State:
        """Blocking — run it in a thread. Never raises: failures end up in the state."""
        state = self.state
        try:
            if self.plan.warning:
                state.status, state.summary = REFUSED, self.plan.warning
                return state
            _save(self.root, state)
            prepared = tasks.prepare_lots(self.plan.found, self.root, self.cfg)
            result = photos.Result()
            for lot_dir, lot in zip(prepared.dirs, prepared.lots):
                if self._stop.is_set():
                    state.status = STOPPED
                    break
                lot_result = photos.sync_lot(lot_dir, lot, self.cfg, self.http)
                result.lots.append(lot_result)
                state.done += 1
                state.photos += lot_result.saved
                state.bytes_saved += lot_result.bytes_saved
                _save(self.root, state)
                if on_progress:
                    on_progress(state)
            else:
                state.status = DONE
            state.summary = result.report()
        except Exception as error:  # the bot must hear about it, not crash
            state.status, state.error = FAILED, f"{type(error).__name__}: {error}"
        finally:
            state.finished_at = _now()
            _save(self.root, state)
        return state
