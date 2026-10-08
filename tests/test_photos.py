from pathlib import Path

from copart_archive import config, metadata, net, photos, salesdata

SALESDATA = Path(__file__).parent / "fixtures" / "salesdata_sample.xlsx"
PAYLOAD = {"lotImages": [
    {"sequence": 1, "link": [{"url": "https://cs/1_ful.jpg", "isThumbNail": False, "isHdImage": False}]},
    {"sequence": 3, "link": [{"url": "https://cs/3_ful.jpg", "isThumbNail": False, "isHdImage": False}]},
    {"sequence": 90, "link": [{"url": "https://cs/sound.mp3", "isEngineSound": True}]},
]}


class FakeHttp:
    def __init__(self, payload=PAYLOAD, fail=None):
        self.payload, self.fail = payload, fail
        self.downloaded = []

    def get_json(self, url):
        if isinstance(self.fail, Exception):
            raise self.fail
        return self.payload

    def download(self, url, target):
        self.downloaded.append(url)
        target.write_bytes(b"jpeg" + url.encode())
        return target.stat().st_size


def lot():
    return next(l for l in salesdata.read(SALESDATA) if l.lot == "51425816")


def test_sync_lot_numbers_files_and_skips_sound(tmp_path):
    http = FakeHttp()
    result = photos.sync_lot(tmp_path, lot(), config.load(), http)
    assert (result.status, result.saved, result.skipped) == (photos.OK, 2, 0)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["01.jpg", "02.jpg", "metadata.json"]
    saved = metadata.read(tmp_path)
    assert [p["sequence"] for p in saved["photos"]] == [1, 3]  # API numbering kept in metadata
    assert saved["photos_count"] == 2 and saved["photos_status"] == photos.OK
    assert saved["photos"][0]["sha256"] and saved["photos"][0]["bytes"]


def test_second_run_downloads_nothing(tmp_path):
    cfg = config.load()
    photos.sync_lot(tmp_path, lot(), cfg, FakeHttp())
    http = FakeHttp()
    again = photos.sync_lot(tmp_path, lot(), cfg, http)
    assert (again.saved, again.skipped, http.downloaded) == (0, 2, [])


def test_sold_lot_is_marked_gone(tmp_path):
    http = FakeHttp(fail=net.NotFound("https://x", 404))
    result = photos.sync_lot(tmp_path, lot(), config.load(), http)
    assert result.status == photos.GONE
    assert metadata.read(tmp_path)["photos_status"] == photos.GONE


def test_lot_without_photos(tmp_path):
    result = photos.sync_lot(tmp_path, lot(), config.load(), FakeHttp(payload={"lotImages": []}))
    assert result.status == photos.EMPTY


def test_network_error_is_reported_not_raised(tmp_path):
    http = FakeHttp(fail=net.HttpError("https://x", 503))
    result = photos.sync_lot(tmp_path, lot(), config.load(), http)
    assert result.status == photos.ERROR and "503" in result.error


def test_estimate_and_space_warning(tmp_path):
    assert photos.estimate_bytes(300, "full") == 300 * 12 * 150 * 1024
    assert photos.space_warning(tmp_path, 10, "full") is None
    huge = photos.space_warning(tmp_path, 100_000_000, "high_res")
    assert huge and "Не хватает места" in huge


def test_free_bytes_for_missing_root(tmp_path):
    assert photos.free_bytes(tmp_path / "nope" / "deeper") > 0


def test_report_counts_statuses():
    result = photos.Result(lots=[
        photos.LotResult("1", photos.OK, saved=3, bytes_saved=300),
        photos.LotResult("2", photos.GONE),
        photos.LotResult("3", photos.ERROR, error="503"),
    ])
    text = result.report()
    assert "Лотов обработано: 3" in text
    assert "проданы): 1" in text and "ошибка 3: 503" in text


def test_changed_photo_at_the_same_position_is_redownloaded(tmp_path):
    cfg = config.load()
    photos.sync_lot(tmp_path, lot(), cfg, FakeHttp())
    inserted = {"lotImages": [
        {"sequence": 1, "link": [{"url": "https://cs/1_ful.jpg", "isHdImage": False}]},
        {"sequence": 2, "link": [{"url": "https://cs/NEW_ful.jpg", "isHdImage": False}]},
        {"sequence": 3, "link": [{"url": "https://cs/3_ful.jpg", "isHdImage": False}]},
    ]}
    http = FakeHttp(payload=inserted)
    again = photos.sync_lot(tmp_path, lot(), cfg, http)
    # 02.jpg held photo 3 before, now it is the new one; 03.jpg appears
    assert http.downloaded == ["https://cs/NEW_ful.jpg", "https://cs/3_ful.jpg"]
    assert again.skipped == 1 and again.saved == 2
    urls = [p["url"] for p in metadata.read(tmp_path)["photos"]]
    assert urls == ["https://cs/1_ful.jpg", "https://cs/NEW_ful.jpg", "https://cs/3_ful.jpg"]


def test_missing_lot_dir_is_created(tmp_path):
    target = tmp_path / "deep" / "COPART_1"
    assert photos.sync_lot(target, lot(), config.load(), FakeHttp()).saved == 2
    assert (target / "01.jpg").exists()


def test_human_sizes():
    assert photos.human(3 * 1024**2) == "3 МБ"
    assert photos.human(2 * 1024**3) == "2.0 ГБ"
