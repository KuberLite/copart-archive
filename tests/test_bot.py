import asyncio
import datetime
from pathlib import Path

import pytest

pytest.importorskip("aiogram")

from aiogram.client.session.base import BaseSession
from aiogram.methods import SendMessage
from aiogram.types import Chat, Message, Update, User

from copart_archive import bot, config, jobs


# --- pure parts ---------------------------------------------------------------

def test_settings_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("BOT_TOKEN", "123:abc")
    monkeypatch.setenv("BOT_ALLOWED_IDS", "11, 22 33")
    monkeypatch.setenv("COPART_ARCHIVE_ROOT", str(tmp_path))
    settings = bot.Settings.from_env()
    assert settings.allowed == {11, 22, 33} and settings.root == tmp_path


def test_settings_need_a_token(monkeypatch):
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    with pytest.raises(SystemExit):
        bot.Settings.from_env()


def test_empty_allowed_list_lets_nobody_in(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123:abc")
    monkeypatch.setenv("BOT_ALLOWED_IDS", "")
    assert bot.Settings.from_env().allowed == frozenset()


def test_texts():
    assert "777" in bot.access_denied_text(777)
    assert "zip" in bot.too_big_text(25 * 1024**2) and "25.0 МБ" in bot.too_big_text(25 * 1024**2)


def test_status_before_and_after_a_job(tmp_path):
    assert "Загрузок ещё не было" in bot.status_text(None, tmp_path)
    jobs._save(tmp_path, jobs.State(file="Copart.xlsx", status=jobs.DONE, total=3, done=3, photos=36))
    text = bot.status_text(None, tmp_path)
    assert "Copart.xlsx: завершена" in text and "3/3 лотов, 36 фото" in text
    running = jobs.State(file="new.xlsx", total=10, done=4)
    assert "Сейчас загрузка" in bot.status_text(running, tmp_path)


# --- the runner ----------------------------------------------------------------

class FakeJob:
    def __init__(self):
        self.state = jobs.State(file="f.xlsx", total=2)
        self.stopped = False

    def stop(self):
        self.stopped = True

    def run(self, progress):
        for _ in range(2):
            self.state.done += 1
            progress(self.state)
        self.state.status = jobs.DONE
        return self.state


def test_runner_reports_progress_and_finish():
    async def scenario():
        runner, seen, done = bot.Runner(), [], asyncio.Event()

        async def on_progress(state):
            seen.append(state.done)

        async def on_done(state):
            done.set()

        runner.start(FakeJob(), asyncio.get_running_loop(), on_progress, on_done)
        await asyncio.wait_for(done.wait(), 5)
        return runner, seen

    runner, seen = asyncio.run(scenario())
    assert seen[-1] == 2  # the last lot is always reported
    assert not runner.busy and runner.current() is None


def test_stop_when_idle():
    assert bot.Runner().stop() is False


# --- access control through the real dispatcher -------------------------------

class FakeSession(BaseSession):
    """Answers Bot API calls without the network and remembers them."""

    def __init__(self):
        super().__init__()
        self.sent: list[str] = []

    async def make_request(self, bot_, method, timeout=None):
        if isinstance(method, SendMessage):
            self.sent.append(method.text)
            return Message(message_id=len(self.sent), date=datetime.datetime.now(),
                           chat=Chat(id=method.chat_id, type="private"), text=method.text)
        return True

    async def stream_content(self, *args, **kwargs):
        yield b""

    async def close(self):
        pass


def message_update(user_id: int, text: str) -> Update:
    user = User(id=user_id, is_bot=False, first_name="U")
    return Update(update_id=1, message=Message(
        message_id=1, date=datetime.datetime.now(), chat=Chat(id=user_id, type="private"),
        from_user=user, text=text))


def run_dispatch(tmp_path, user_id, text):
    settings = bot.Settings(token="123:abc", allowed=frozenset({100}), root=tmp_path)
    telegram, dp = bot.build(settings, config.load())
    telegram.session = FakeSession()
    asyncio.run(dp.feed_update(telegram, message_update(user_id, text)))
    return telegram.session.sent


def test_stranger_gets_only_their_id(tmp_path):
    sent = run_dispatch(tmp_path, 999, bot.STATUS)
    assert sent == [bot.access_denied_text(999)]


def test_allowed_user_gets_status(tmp_path):
    [reply] = run_dispatch(tmp_path, 100, bot.STATUS)
    assert "Загрузок ещё не было" in reply


def test_stop_with_nothing_running(tmp_path):
    [reply] = run_dispatch(tmp_path, 100, bot.STOP)
    assert "ничего не качается" in reply


# --- the whole path: a file in the chat -> photos in the archive -------------

SALESDATA = Path(__file__).parent / "fixtures" / "salesdata_sample.xlsx"


class FakeHttp:
    def __init__(self, *args, **kwargs):
        pass

    def get_json(self, url):
        return {"lotImages": [{"sequence": 1, "link": [{"url": "https://cs/1_ful.jpg", "isHdImage": False}]}]}

    def download(self, url, target):
        target.write_bytes(b"jpeg")
        return 4


def document_update(user_id: int, name: str, size: int) -> Update:
    from aiogram.types import Document
    user = User(id=user_id, is_bot=False, first_name="U")
    return Update(update_id=2, message=Message(
        message_id=2, date=datetime.datetime.now(), chat=Chat(id=user_id, type="private"),
        from_user=user, document=Document(file_id="f", file_unique_id="u", file_name=name, file_size=size)))


def send_file(tmp_path, monkeypatch, name="Copart_50000_rows.xlsx", size=None, user_id=100):
    monkeypatch.setattr(bot.net, "Http", FakeHttp)
    settings = bot.Settings(token="123:abc", allowed=frozenset({100}), root=tmp_path / "archive")
    telegram, dp = bot.build(settings, config.load())
    telegram.session = FakeSession()

    async def fake_download(file, destination=None, **kwargs):
        Path(destination).write_bytes(SALESDATA.read_bytes())
    monkeypatch.setattr(telegram, "download", fake_download)

    async def scenario():
        await dp.feed_update(telegram, document_update(user_id, name, size or SALESDATA.stat().st_size))
        runner = dp["runner"]
        for _ in range(500):
            if not runner.busy:
                break
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.05)  # let on_done reach the loop

    asyncio.run(scenario())
    return telegram.session.sent, settings.root


def test_file_starts_a_download(tmp_path, monkeypatch):
    sent, root = send_file(tmp_path, monkeypatch)
    assert any("К загрузке 2 лотов" in text for text in sent)
    assert any("завершена" in text for text in sent)
    assert len(list(root.rglob("01.jpg"))) == 2
    [stored] = list((root / "cases").rglob("Upload_*.xlsx"))  # the raw file is kept
    assert jobs.last_state(root).status == jobs.DONE


def test_file_too_big_for_telegram(tmp_path, monkeypatch):
    sent, root = send_file(tmp_path, monkeypatch, size=25 * 1024**2)
    assert sent == [bot.too_big_text(25 * 1024**2)]
    assert not root.exists()


def test_unreadable_file(tmp_path, monkeypatch):
    sent, _ = send_file(tmp_path, monkeypatch, name="notes.pdf")
    assert sent and "Не получилось прочитать файл" in sent[0]


def test_stranger_cannot_start_a_download(tmp_path, monkeypatch):
    sent, root = send_file(tmp_path, monkeypatch, user_id=999)
    assert sent == [bot.access_denied_text(999)]
    assert not root.exists()


def test_two_files_at_once_start_one_download(tmp_path, monkeypatch):
    monkeypatch.setattr(bot.net, "Http", FakeHttp)
    settings = bot.Settings(token="123:abc", allowed=frozenset({100}), root=tmp_path / "archive")
    telegram, dp = bot.build(settings, config.load())
    telegram.session = FakeSession()

    async def slow_download(file, destination=None, **kwargs):
        await asyncio.sleep(0.2)  # the second file arrives while the first is being fetched
        Path(destination).write_bytes(SALESDATA.read_bytes())
    monkeypatch.setattr(telegram, "download", slow_download)

    async def scenario():
        await asyncio.gather(
            dp.feed_update(telegram, document_update(100, "a.xlsx", 1000)),
            dp.feed_update(telegram, document_update(100, "b.xlsx", 1000)))
        runner = dp["runner"]
        for _ in range(500):
            if not runner.busy:
                break
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.05)

    asyncio.run(scenario())
    sent = telegram.session.sent
    assert sum("Уже идёт загрузка" in t for t in sent) == 1
    assert sum("К загрузке" in t for t in sent) == 1


def test_telegram_refusing_the_file(tmp_path, monkeypatch):
    from aiogram.exceptions import TelegramBadRequest
    from aiogram.methods import GetFile
    settings = bot.Settings(token="123:abc", allowed=frozenset({100}), root=tmp_path / "archive")
    telegram, dp = bot.build(settings, config.load())
    telegram.session = FakeSession()

    async def refuse(file, destination=None, **kwargs):
        raise TelegramBadRequest(method=GetFile(file_id="f"), message="file is too big")
    monkeypatch.setattr(telegram, "download", refuse)
    asyncio.run(dp.feed_update(telegram, document_update(100, "big.xlsx", 0)))
    assert any("Telegram не отдал файл" in t for t in telegram.session.sent)


def test_rules_follow_the_config():
    from dataclasses import replace
    cfg = config.load()
    text = bot.rules_text(cfg)
    assert "2015 и новее" in text
    assert "Марка (21)" in text and "MERCEDES-BENZ" in text
    assert "Flood — WATER/FLOOD" in text
    assert "не фильтруется" in text and "обычное" in text
    changed = bot.rules_text(replace(cfg, year_min=2018, vehicle_types=frozenset({"V"}),
                                     photo_quality="high_res"))
    assert "2018 и новее" in changed and "Тип ТС: V" in changed and "HD" in changed


def test_rules_button(tmp_path):
    [reply] = run_dispatch(tmp_path, 100, bot.RULES)
    assert "Год выпуска" in reply


def test_stranger_does_not_see_the_rules(tmp_path):
    assert run_dispatch(tmp_path, 999, bot.RULES) == [bot.access_denied_text(999)]


# --- settings -----------------------------------------------------------------

from datetime import date as _date


def test_parse_year():
    today = _date(2026, 10, 9)
    assert bot.parse_year(" 2018 ", today) == 2018
    assert bot.parse_year("2028", today) == 2028
    for bad in ("18", "две тысячи", "2029", "1800", ""):
        with pytest.raises(ValueError):
            bot.parse_year(bad, today)


def test_parse_makes():
    assert bot.parse_makes("bmw, Audi\nAUDI;  land   rover ") == ["BMW", "AUDI", "LAND ROVER"]
    with pytest.raises(ValueError):
        bot.parse_makes(" ,\n; ")


def test_makes_diff():
    text = bot.makes_diff(frozenset({"BMW", "KIA"}), ["BMW", "CHEVROLET"])
    assert "Добавлены: CHEVROLET" in text and "Убраны: KIA" in text
    assert "не изменился" in bot.makes_diff(frozenset({"BMW"}), ["BMW"])


def test_settings_text_shows_who_changed(tmp_path):
    from dataclasses import replace
    base = config.load()
    assert "стандартные" in bot.settings_text(base, tmp_path)
    config.save_overrides(tmp_path, replace(base, year_min=2018), "Денис (377233264)")
    text = bot.settings_text(config.load_for(tmp_path), tmp_path)
    assert "с 2018" in text and "Денис (377233264)" in text and "7 из 17" in text


class ChatSession(FakeSession):
    def __init__(self):
        super().__init__()
        self.alerts: list[tuple[str, bool]] = []

    async def make_request(self, bot_, method, timeout=None):
        from aiogram.methods import AnswerCallbackQuery
        if isinstance(method, AnswerCallbackQuery):
            self.alerts.append((method.text or "", bool(method.show_alert)))
            return True
        return await super().make_request(bot_, method, timeout)


class Conversation:
    """One chat with the bot through the real dispatcher, no network."""

    def __init__(self, root, allowed=frozenset({100})):
        self.settings = bot.Settings(token="123:abc", allowed=allowed, root=root)
        self.telegram, self.dp = bot.build(self.settings, config.load())
        self.telegram.session = ChatSession()
        self.update_id = 100

    @property
    def sent(self):
        return self.telegram.session.sent

    @property
    def alerts(self):
        return self.telegram.session.alerts

    def _next(self):
        self.update_id += 1
        return self.update_id

    def say(self, text, user_id=100):
        user = User(id=user_id, is_bot=False, first_name="Денис")
        update = Update(update_id=self._next(), message=Message(
            message_id=self.update_id, date=datetime.datetime.now(),
            chat=Chat(id=user_id, type="private"), from_user=user, text=text))
        asyncio.run(self.dp.feed_update(self.telegram, update))

    def press(self, data, user_id=100):
        from aiogram.types import CallbackQuery
        user = User(id=user_id, is_bot=False, first_name="Денис")
        message = Message(message_id=1, date=datetime.datetime.now(),
                          chat=Chat(id=user_id, type="private"), text="меню")
        update = Update(update_id=self._next(), callback_query=CallbackQuery(
            id=str(self.update_id), from_user=user, chat_instance="c", message=message, data=data))
        asyncio.run(self.dp.feed_update(self.telegram, update))

    def cfg(self):
        return config.load_for(self.settings.root)


def test_settings_button(tmp_path):
    talk = Conversation(tmp_path)
    talk.say(bot.SETTINGS)
    assert "Настройки отбора" in talk.sent[-1] and "с 2015" in talk.sent[-1]


def test_change_year(tmp_path):
    talk = Conversation(tmp_path)
    talk.press("cfg:year")
    talk.say("двадцатый")
    assert "четырьмя цифрами" in talk.sent[-1]
    assert talk.cfg().year_min == 2015  # nothing saved, still waiting
    talk.say("2018")
    assert talk.cfg().year_min == 2018
    assert "с 2018 года" in talk.sent[-1]
    assert "Денис (100)" in config.read_overrides(tmp_path)["changed_by"]


def test_keyboard_button_cancels_the_input(tmp_path):
    talk = Conversation(tmp_path)
    talk.press("cfg:year")
    talk.say(bot.STATUS)  # not a year: the status is shown and the input dropped
    assert "Загрузок ещё не было" in talk.sent[-1]
    talk.say("2020")
    assert talk.cfg().year_min == 2015


def test_change_makes(tmp_path):
    talk = Conversation(tmp_path)
    talk.press("cfg:makes")
    assert "MERCEDES-BENZ" in talk.sent[-1]  # the current list to copy
    talk.say("bmw, Audi\nchevrolet")
    assert talk.cfg().makes == {"BMW", "AUDI", "CHEVROLET"}
    assert "Добавлены: CHEVROLET" in talk.sent[-1]


def test_toggle_damage_groups(tmp_path):
    talk = Conversation(tmp_path)
    talk.press("cfg:damage")
    assert "Fire — BURN, BURN - ENGINE, BURN - INTERIOR" in talk.sent[-1]
    talk.press("dmg:Hail")
    assert "Hail" in talk.cfg().damage_groups
    assert talk.alerts[-1] == ("Hail: включено", False)
    talk.press("dmg:Hail")
    assert "Hail" not in talk.cfg().damage_groups


def test_last_damage_group_cannot_be_switched_off(tmp_path):
    talk = Conversation(tmp_path)
    for group in ["Front_End", "Rear_End", "Side", "Flood", "Rollover", "All_Over"]:
        talk.press(f"dmg:{group}")
    assert list(talk.cfg().damage_groups) == ["Undercarriage"]
    talk.press("dmg:Undercarriage")
    assert list(talk.cfg().damage_groups) == ["Undercarriage"]
    assert talk.alerts[-1] == ("Хотя бы одна группа должна остаться", True)


def test_reset(tmp_path):
    talk = Conversation(tmp_path)
    talk.press("cfg:year")
    talk.say("2020")
    talk.press("cfg:reset")
    assert talk.cfg() == config.load()
    assert "Вернул стандартные" in talk.sent[-1]


def test_stranger_cannot_press_settings(tmp_path):
    talk = Conversation(tmp_path)
    talk.press("dmg:Hail", user_id=999)
    talk.press("cfg:reset", user_id=999)
    assert talk.alerts == [("Доступа нет", True), ("Доступа нет", True)]
    assert talk.cfg() == config.load()


def test_rules_show_the_changed_settings(tmp_path):
    talk = Conversation(tmp_path)
    talk.press("cfg:year")
    talk.say("2019")
    talk.say(bot.RULES)
    assert "2019 и новее" in talk.sent[-1]


def test_new_settings_apply_to_the_next_file(tmp_path, monkeypatch):
    from dataclasses import replace
    root = tmp_path / "archive"
    config.save_overrides(root, replace(config.load(), year_min=2030))
    sent, _ = send_file(tmp_path, monkeypatch)
    assert any("К загрузке 0 лотов" in t for t in sent)


def test_file_drops_a_pending_settings_input(tmp_path):
    talk = Conversation(tmp_path)
    talk.press("cfg:year")
    talk.telegram.download = None  # the file is not read here; only the state matters
    from aiogram.types import Document
    user = User(id=100, is_bot=False, first_name="Денис")
    update = Update(update_id=999, message=Message(
        message_id=999, date=datetime.datetime.now(), chat=Chat(id=100, type="private"),
        from_user=user, document=Document(file_id="f", file_unique_id="u",
                                          file_name="big.xlsx", file_size=25 * 1024**2)))
    asyncio.run(talk.dp.feed_update(talk.telegram, update))
    talk.say("2020")  # no longer read as a year
    assert talk.cfg().year_min == 2015
