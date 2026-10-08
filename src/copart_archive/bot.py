"""Telegram bot: the client sends a file, the archive fills up with photos.

Deliberately simple: a file starts a download right away, two buttons show the
status and stop it. Only Telegram IDs from BOT_ALLOWED_IDS may use it; anyone
else is told their ID, which is how new IDs are found out.
"""

import asyncio
import logging
import os
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from . import config, jobs, layout, net, photos, uploads
from .tabular import FormatError

STATUS, STOP = "Статус", "Остановить"
MAX_FILE = 20 * 1024**2  # what the Telegram Bot API lets a bot download
PROGRESS_EVERY = 30.0  # seconds between progress message edits

STATUS_NAMES = {
    jobs.RUNNING: "идёт", jobs.DONE: "завершена", jobs.STOPPED: "остановлена",
    jobs.FAILED: "ошибка", jobs.REFUSED: "отказ", jobs.INTERRUPTED: "прервана перезапуском",
}

log = logging.getLogger("copart_archive.bot")


@dataclass(frozen=True)
class Settings:
    token: str
    allowed: frozenset[int]
    root: Path
    delay: float = 0.5

    @classmethod
    def from_env(cls) -> "Settings":
        token = os.environ.get("BOT_TOKEN", "").strip()
        if not token:
            raise SystemExit("нет BOT_TOKEN")
        ids = os.environ.get("BOT_ALLOWED_IDS", "")
        allowed = frozenset(int(i) for i in ids.replace(",", " ").split() if i.strip())
        return cls(token=token, allowed=allowed,
                   root=Path(os.environ.get("COPART_ARCHIVE_ROOT", "archive")),
                   delay=float(os.environ.get("BOT_DELAY", "0.5")))


def access_denied_text(user_id: int) -> str:
    return f"Доступа нет. Ваш Telegram ID: {user_id} — передайте его администратору."


def too_big_text(size: int) -> str:
    return (f"Файл {size / 1024**2:.1f} МБ, а Telegram отдаёт ботам не больше 20 МБ. "
            "Сожмите его в zip — таблица ужимается в несколько раз.")


def help_text() -> str:
    return ("Пришлите файл выгрузки Copart (.xlsx, .csv или .zip) — загрузка фото начнётся сразу.\n"
            f"«{STATUS}» — что идёт сейчас и сколько места. «{STOP}» — прервать загрузку, "
            "скачанное останется, повторная отправка того же файла докачает остальное.")


def describe_state(state: jobs.State) -> str:
    lines = [f"{state.file}: {STATUS_NAMES.get(state.status, state.status)}", state.progress()]
    if state.error:
        lines.append(f"Ошибка: {state.error}")
    return "\n".join(lines)


def status_text(running: jobs.State | None, root: Path) -> str:
    lines = []
    if running:
        lines.append("Сейчас загрузка:\n" + describe_state(running))
    else:
        last = jobs.last_state(root)
        lines.append("Последняя загрузка:\n" + describe_state(last) if last else "Загрузок ещё не было.")
    lots = len(layout.existing_lot_dirs(root))
    lines.append(f"В архиве лотов: {lots}. Свободно: {photos.human(photos.free_bytes(root))}")
    return "\n\n".join(lines)


class Runner:
    """One download at a time, in a thread, reporting back to the bot's loop."""

    def __init__(self):
        self.job: jobs.Job | None = None
        self._thread: threading.Thread | None = None

    @property
    def busy(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def current(self) -> jobs.State | None:
        return self.job.state if self.busy and self.job else None

    def stop(self) -> bool:
        if not self.busy or not self.job:
            return False
        self.job.stop()
        return True

    def start(self, job: jobs.Job, loop: asyncio.AbstractEventLoop, on_progress, on_done) -> None:
        last = [0.0]

        def progress(state: jobs.State) -> None:
            now = time.monotonic()
            if now - last[0] >= PROGRESS_EVERY or state.done == state.total:
                last[0] = now
                asyncio.run_coroutine_threadsafe(on_progress(state), loop)

        def work() -> None:
            state = job.run(progress)
            asyncio.run_coroutine_threadsafe(on_done(state), loop)

        self.job = job
        self._thread = threading.Thread(target=work, name="photo-job", daemon=True)
        self._thread.start()


def build(settings: Settings, cfg: config.Config):
    from aiogram import Bot, Dispatcher, F
    from aiogram.exceptions import TelegramAPIError
    from aiogram.filters import CommandStart
    from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

    bot = Bot(settings.token)
    dp = Dispatcher()
    runner = Runner()
    dp["runner"] = runner  # reachable from outside: tests, start-up checks
    # held from the busy check until the job has started: two files sent one after
    # the other must not both pass the check while the first is still downloading
    starting = asyncio.Lock()
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=STATUS), KeyboardButton(text=STOP)]],
        resize_keyboard=True, is_persistent=True)

    @dp.message(~F.from_user.id.in_(settings.allowed))
    async def deny(message: Message) -> None:
        user_id = message.from_user.id if message.from_user else 0
        log.info("отказ в доступе: %s", user_id)
        await message.answer(access_denied_text(user_id))

    @dp.message(CommandStart())
    async def start(message: Message) -> None:
        await message.answer(help_text(), reply_markup=keyboard)

    @dp.message(F.text == STATUS)
    async def status(message: Message) -> None:
        text = await asyncio.to_thread(status_text, runner.current(), settings.root)
        await message.answer(text, reply_markup=keyboard)

    @dp.message(F.text == STOP)
    async def stop(message: Message) -> None:
        text = ("Останавливаю после текущего лота, скачанное остаётся."
                if runner.stop() else "Сейчас ничего не качается.")
        await message.answer(text, reply_markup=keyboard)

    @dp.message(F.document)
    async def document(message: Message) -> None:
        doc = message.document
        if runner.busy or starting.locked():
            current = runner.current()
            await message.answer("Уже идёт загрузка" + (":\n" + describe_state(current) if current else ".")
                                 + f"\nДождитесь или нажмите «{STOP}».")
            return
        if doc.file_size and doc.file_size > MAX_FILE:
            await message.answer(too_big_text(doc.file_size))
            return
        async with starting:
            await receive(message, doc)

    async def receive(message: Message, doc) -> None:
        name = PurePosixPath(doc.file_name or "upload").name
        try:
            with tempfile.TemporaryDirectory() as tmp:
                local = Path(tmp) / name
                await bot.download(doc, destination=local)
                stored = await asyncio.to_thread(uploads.store, local, settings.root, name)
            job_plan = await asyncio.to_thread(jobs.plan, stored.table, settings.root, cfg)
        except FormatError as error:
            await message.answer(f"Не получилось прочитать файл: {error}")
            return
        except TelegramAPIError as error:  # e.g. the size was unknown and turned out too big
            await message.answer(f"Telegram не отдал файл: {error}")
            return
        except OSError as error:
            log.exception("не сохранил файл")
            await message.answer(f"Не получилось сохранить файл: {error}")
            return
        text = job_plan.describe(cfg.photo_quality)
        if stored.duplicate:
            text = "Этот файл уже присылали — докачаю то, чего не хватает.\n\n" + text
        await message.answer(text)
        if job_plan.warning or job_plan.count == 0:
            return

        progress_message = await message.answer("Начинаю загрузку…")
        job = jobs.Job(job_plan, settings.root, cfg, net.Http(delay=settings.delay), name)

        async def on_progress(state: jobs.State) -> None:
            try:
                await progress_message.edit_text("Загрузка: " + state.progress())
            except Exception as error:  # an edit can fail (same text, message gone) — not fatal
                log.debug("не обновил прогресс: %s", error)

        async def on_done(state: jobs.State) -> None:
            await message.answer(describe_state(state) + "\n\n" + (state.summary or ""),
                                 reply_markup=keyboard)

        runner.start(job, asyncio.get_running_loop(), on_progress, on_done)

    @dp.message()
    async def other(message: Message) -> None:
        await message.answer(help_text(), reply_markup=keyboard)

    return bot, dp


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = Settings.from_env()
    interrupted = jobs.mark_interrupted(settings.root)
    if interrupted:
        log.warning("прошлая загрузка %s была прервана на %s", interrupted.file, interrupted.progress())
    if not settings.allowed:
        log.warning("BOT_ALLOWED_IDS пуст — бот всем отвечает отказом и показывает их ID")
    bot, dp = build(settings, config.load())
    asyncio.run(dp.start_polling(bot))


if __name__ == "__main__":
    main()
