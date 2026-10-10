"""Telegram bot: the client sends a file, the archive fills up with photos.

Deliberately simple: a file starts a download right away, two buttons show the
status and stop it. Only Telegram IDs from BOT_ALLOWED_IDS may use it; anyone
else is told their ID, which is how new IDs are found out.
"""

import asyncio
import html
import logging
import os
import re
import tempfile
import threading
import time
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path, PurePosixPath

from . import config, jobs, layout, net, photos, uploads
from .tabular import FormatError

STATUS, STOP, RULES, SETTINGS = "Статус", "Остановить", "Правила", "Настройки"
BUTTONS = (STATUS, STOP, RULES, SETTINGS)
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


QUALITY_NAMES = {"thumbnail": "превью", "full": "обычное", "high_res": "HD"}


def help_text() -> str:
    return ("Пришлите файл выгрузки Copart (.xlsx, .csv или .zip) — загрузка фото начнётся сразу.\n"
            f"«{STATUS}» — что идёт сейчас и сколько места. «{STOP}» — прервать загрузку, "
            "скачанное останется, повторная отправка того же файла докачает остальное. "
            f"«{RULES}» — какие лоты берутся из файла. «{SETTINGS}» — поменять год, марки и повреждения.")


def rules_text(cfg: config.Config) -> str:
    """Built from the config, so it always says what the bot actually does."""
    groups = "\n".join(f"  {group} — {', '.join(sorted(values))}"
                       for group, values in cfg.damage_groups.items())
    types = (", ".join(sorted(cfg.vehicle_types)) if cfg.vehicle_types
             else "не фильтруется, берутся все")
    return (
        "Из файла берутся лоты, которые проходят все условия:\n\n"
        f"• Год выпуска: {cfg.year_min} и новее\n"
        f"• Марка ({len(cfg.makes)}): {', '.join(sorted(cfg.makes))}\n"
        f"• Основное повреждение (primary) — одна из групп:\n{groups}\n"
        f"• Тип ТС: {types}\n\n"
        "Остальные лоты пропускаются, в ответе на файл видно, сколько и почему.\n\n"
        f"Фото: качество {QUALITY_NAMES.get(cfg.photo_quality, cfg.photo_quality)}, все снимки лота.\n"
        "Папки: Группа / Марка / Год / Модель / COPART_<лот>_<VIN>")


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


def settings_text(cfg: config.Config, root: Path) -> str:
    saved = config.read_overrides(root)
    origin = (f"изменено: {saved.get('changed_by')}, {saved.get('changed_at', '')[:16].replace('T', ' ')} UTC"
              if saved else "стандартные, из config/archive.toml")
    groups = ", ".join(cfg.damage_groups) or "ни одной"
    return (f"Настройки отбора ({origin}):\n\n"
            f"• Год выпуска: с {cfg.year_min}\n"
            f"• Марки ({len(cfg.makes)}): {', '.join(sorted(cfg.makes))}\n"
            f"• Повреждения ({len(cfg.damage_groups)} из {len(cfg.catalog)}): {groups}\n\n"
            "Изменения действуют со следующего файла; загрузка, которая уже идёт, "
            "доработает по старым правилам.")


def parse_year(text: str, today: date | None = None) -> int:
    today = today or date.today()
    if not re.fullmatch(r"\s*\d{4}\s*", text or ""):
        raise ValueError("Нужен год четырьмя цифрами, например 2015.")
    year = int(text)
    if not 1900 <= year <= today.year + 2:
        raise ValueError(f"Год должен быть между 1900 и {today.year + 2}.")
    return year


def parse_makes(text: str) -> list[str]:
    """Commas, semicolons or new lines — whatever comes out of a copied list."""
    makes = []
    for part in re.split(r"[,;\n]+", text or ""):
        make = re.sub(r"\s+", " ", part).strip().upper()
        if make and make not in makes:
            makes.append(make)
    if not makes:
        raise ValueError("Список пустой — нужна хотя бы одна марка.")
    return makes


def makes_diff(old: frozenset[str], new: list[str]) -> str:
    added = [m for m in new if m not in old]
    removed = sorted(old - set(new))
    lines = [f"Марок теперь: {len(new)}."]
    if added:
        lines.append("Добавлены: " + ", ".join(added))
    if removed:
        lines.append("Убраны: " + ", ".join(removed))
    if not added and not removed:
        lines.append("Список не изменился.")
    return "\n".join(lines)


def damage_buttons(cfg: config.Config):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    rows = [[InlineKeyboardButton(
                text=("✅ " if group in cfg.damage_groups else "▫️ ") + group,
                callback_data=f"dmg:{group}")]
            for group in cfg.catalog]
    rows.append([InlineKeyboardButton(text="Готово", callback_data="dmg:done")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def damage_help(cfg: config.Config) -> str:
    lines = ["Отметьте группы повреждений, которые брать. Что входит в группу (как пишет Copart):", ""]
    lines += [f"{group} — {', '.join(sorted(values))}" for group, values in cfg.catalog.items()]
    return "\n".join(lines)


class Runner:
    """One download at a time, in a thread, reporting back to the bot's loop."""

    def __init__(self):
        self.job: jobs.Job | None = None
        self._thread: threading.Thread | None = None
        self._running = False

    @property
    def busy(self) -> bool:
        # a flag, not thread.is_alive(): the thread outlives the "done" message by a
        # moment, and a file sent right after it must not be told a job is running
        return self._running

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
            try:
                state = job.run(progress)
            finally:
                self._running = False  # before the message goes out
            asyncio.run_coroutine_threadsafe(on_done(state), loop)

        self.job = job
        self._running = True
        self._thread = threading.Thread(target=work, name="photo-job", daemon=True)
        self._thread.start()


def build(settings: Settings, cfg: config.Config):
    from aiogram import Bot, Dispatcher, F
    from aiogram.exceptions import TelegramAPIError
    from aiogram.filters import CommandStart, StateFilter
    from aiogram.fsm.context import FSMContext
    from aiogram.fsm.state import State, StatesGroup
    from aiogram.types import (CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
                               KeyboardButton, Message, ReplyKeyboardMarkup)

    class Editing(StatesGroup):
        year = State()
        makes = State()

    bot = Bot(settings.token)
    dp = Dispatcher()
    runner = Runner()
    dp["runner"] = runner  # reachable from outside: tests, start-up checks
    # held from the busy check until the job has started: two files sent one after
    # the other must not both pass the check while the first is still downloading
    starting = asyncio.Lock()
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=STATUS), KeyboardButton(text=STOP)],
                  [KeyboardButton(text=RULES), KeyboardButton(text=SETTINGS)]],
        resize_keyboard=True, is_persistent=True)
    settings_menu = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Год", callback_data="cfg:year"),
         InlineKeyboardButton(text="Марки", callback_data="cfg:makes")],
        [InlineKeyboardButton(text="Повреждения", callback_data="cfg:damage")],
        [InlineKeyboardButton(text="Сбросить к стандартным", callback_data="cfg:reset")],
    ])
    cancel_menu = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Отмена", callback_data="cfg:cancel")]])

    def current() -> config.Config:
        """Defaults plus what was changed from the bot — read anew every time."""
        return config.with_overrides(cfg, settings.root)

    def who(user) -> str:
        return f"{user.full_name} ({user.id})" if user else "?"

    def save(new: config.Config, user) -> None:
        config.save_overrides(settings.root, new, who(user))
        log.info("настройки изменил %s: год %s, марок %s, группы %s",
                 who(user), new.year_min, len(new.makes), list(new.damage_groups))

    @dp.message(~F.from_user.id.in_(settings.allowed))
    async def deny(message: Message) -> None:
        user_id = message.from_user.id if message.from_user else 0
        log.info("отказ в доступе: %s", user_id)
        await message.answer(access_denied_text(user_id))

    @dp.callback_query(~F.from_user.id.in_(settings.allowed))
    async def deny_button(callback: CallbackQuery) -> None:
        await callback.answer("Доступа нет", show_alert=True)

    # the keyboard buttons come first and drop any half-done input, so pressing
    # «Статус» while the bot waits for a year does not get read as the year
    @dp.message(CommandStart())
    async def start(message: Message, state: FSMContext) -> None:
        await state.clear()
        await message.answer(help_text(), reply_markup=keyboard)

    @dp.message(F.text == STATUS)
    async def status(message: Message, state: FSMContext) -> None:
        await state.clear()
        text = await asyncio.to_thread(status_text, runner.current(), settings.root)
        await message.answer(text, reply_markup=keyboard)

    @dp.message(F.text == RULES)
    async def rules(message: Message, state: FSMContext) -> None:
        await state.clear()
        await message.answer(rules_text(current()), reply_markup=keyboard)

    @dp.message(F.text == STOP)
    async def stop(message: Message, state: FSMContext) -> None:
        await state.clear()
        text = ("Останавливаю после текущего лота, скачанное остаётся."
                if runner.stop() else "Сейчас ничего не качается.")
        await message.answer(text, reply_markup=keyboard)

    @dp.message(F.text == SETTINGS)
    async def show_settings(message: Message, state: FSMContext) -> None:
        await state.clear()
        await message.answer(settings_text(current(), settings.root), reply_markup=settings_menu)

    @dp.callback_query(F.data == "cfg:year")
    async def ask_year(callback: CallbackQuery, state: FSMContext) -> None:
        await state.set_state(Editing.year)
        await callback.message.answer(
            f"Пришлите год, начиная с которого брать лоты. Сейчас: {current().year_min}.",
            reply_markup=cancel_menu)
        await callback.answer()

    @dp.callback_query(F.data == "cfg:makes")
    async def ask_makes(callback: CallbackQuery, state: FSMContext) -> None:
        await state.set_state(Editing.makes)
        makes = "\n".join(sorted(current().makes))
        await callback.message.answer(
            "Пришлите новый список марок — он заменит текущий. Проще всего скопировать "
            "список ниже, поправить и отправить обратно; можно через запятую или каждую "
            "марку с новой строки. Пишите, как Copart: MERCEDES-BENZ, LAND ROVER.\n\n"
            f"<code>{html.escape(makes)}</code>",
            parse_mode="HTML", reply_markup=cancel_menu)
        await callback.answer()

    @dp.callback_query(F.data == "cfg:damage")
    async def ask_damage(callback: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        now = current()
        await callback.message.answer(damage_help(now), reply_markup=damage_buttons(now))
        await callback.answer()

    @dp.callback_query(F.data.startswith("dmg:") & (F.data != "dmg:done"))
    async def toggle_damage(callback: CallbackQuery) -> None:
        group = callback.data.removeprefix("dmg:")
        now = current()
        if group not in now.catalog:
            await callback.answer("Такой группы больше нет", show_alert=True)
            return
        enabled = set(now.damage_groups)
        if group in enabled and len(enabled) == 1:
            await callback.answer("Хотя бы одна группа должна остаться", show_alert=True)
            return
        enabled ^= {group}
        new = replace(now, damage_groups={g: v for g, v in now.catalog.items() if g in enabled})
        save(new, callback.from_user)
        await callback.message.edit_reply_markup(reply_markup=damage_buttons(new))
        await callback.answer(f"{group}: {'включено' if group in enabled else 'выключено'}")

    @dp.callback_query(F.data == "dmg:done")
    async def damage_done(callback: CallbackQuery) -> None:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(settings_text(current(), settings.root), reply_markup=settings_menu)
        await callback.answer()

    @dp.callback_query(F.data == "cfg:reset")
    async def reset(callback: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        config.reset_overrides(settings.root)
        log.info("настройки сбросил %s", who(callback.from_user))
        await callback.message.answer("Вернул стандартные настройки.\n\n"
                                      + settings_text(current(), settings.root), reply_markup=settings_menu)
        await callback.answer()

    @dp.callback_query(F.data == "cfg:cancel")
    async def cancel(callback: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer("Отменено")

    @dp.message(StateFilter(Editing.year), F.text)
    async def set_year(message: Message, state: FSMContext) -> None:
        try:
            year = parse_year(message.text)
        except ValueError as error:
            await message.answer(f"{error} Пришлите ещё раз или нажмите «Отмена».", reply_markup=cancel_menu)
            return
        save(replace(current(), year_min=year), message.from_user)
        await state.clear()
        await message.answer(f"Готово: берём лоты с {year} года.\n\n"
                             + settings_text(current(), settings.root), reply_markup=settings_menu)

    @dp.message(StateFilter(Editing.makes), F.text)
    async def set_makes(message: Message, state: FSMContext) -> None:
        try:
            makes = parse_makes(message.text)
        except ValueError as error:
            await message.answer(f"{error} Пришлите ещё раз или нажмите «Отмена».", reply_markup=cancel_menu)
            return
        before = current()
        save(replace(before, makes=frozenset(makes)), message.from_user)
        await state.clear()
        await message.answer(makes_diff(before.makes, makes) + "\n\n"
                             + settings_text(current(), settings.root), reply_markup=settings_menu)

    @dp.message(F.document)
    async def document(message: Message, state: FSMContext) -> None:
        await state.clear()  # a file ends any half-done settings input
        doc = message.document
        log.info("файл от %s: %s, %s байт", message.from_user.id, doc.file_name, doc.file_size)
        if runner.busy or starting.locked():
            log.info("отклонён: уже идёт загрузка")
            current = runner.current()
            await message.answer("Уже идёт загрузка" + (":\n" + describe_state(current) if current else ".")
                                 + f"\nДождитесь или нажмите «{STOP}».")
            return
        if doc.file_size and doc.file_size > MAX_FILE:
            log.info("отклонён: больше 20 МБ")
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
            job_cfg = current()  # the settings at the moment the file arrives
            job_plan = await asyncio.to_thread(jobs.plan, stored.table, settings.root, job_cfg)
        except FormatError as error:
            log.info("не прочитан: %s", error)
            await message.answer(f"Не получилось прочитать файл: {error}")
            return
        except TelegramAPIError as error:  # e.g. the size was unknown and turned out too big
            log.warning("Telegram не отдал файл: %s", error)
            await message.answer(f"Telegram не отдал файл: {error}")
            return
        except OSError as error:
            log.exception("не сохранил файл")
            await message.answer(f"Не получилось сохранить файл: {error}")
            return
        log.info("сохранён %s%s; к загрузке %s лотов%s", stored.path.name,
                 " (повтор)" if stored.duplicate else "", job_plan.count,
                 f"; {job_plan.warning}" if job_plan.warning else "")
        text = job_plan.describe(job_cfg.photo_quality)
        if stored.duplicate:
            text = "Этот файл уже присылали — докачаю то, чего не хватает.\n\n" + text
        await message.answer(text)
        if job_plan.warning or job_plan.count == 0:
            return

        progress_message = await message.answer("Начинаю загрузку…")
        job = jobs.Job(job_plan, settings.root, job_cfg, net.Http(delay=settings.delay), name)

        async def on_progress(state: jobs.State) -> None:
            try:
                await progress_message.edit_text("Загрузка: " + state.progress())
            except Exception as error:  # an edit can fail (same text, message gone) — not fatal
                log.debug("не обновил прогресс: %s", error)

        async def on_done(state: jobs.State) -> None:
            log.info("загрузка %s: %s, %s", state.file, state.status, state.progress())
            await message.answer(describe_state(state) + "\n\n" + (state.summary or ""),
                                 reply_markup=keyboard)

        log.info("загрузка началась: %s, %s лотов", name, job_plan.count)
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
