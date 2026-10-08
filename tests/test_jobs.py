import threading
from pathlib import Path

from copart_archive import config, jobs, photos

SALESDATA = Path(__file__).parent / "fixtures" / "salesdata_sample.xlsx"
PAYLOAD = {"lotImages": [
    {"sequence": n, "link": [{"url": f"https://cs/{n}_ful.jpg", "isHdImage": False}]}
    for n in (1, 2)
]}


class FakeHttp:
    def __init__(self, fail=None, on_download=None):
        self.fail, self.on_download = fail, on_download

    def get_json(self, url):
        if self.fail:
            raise self.fail
        return PAYLOAD

    def download(self, url, target):
        if self.on_download:
            self.on_download()
        target.write_bytes(b"jpeg")
        return 4


def make_job(root, http, **plan_args):
    cfg = config.load()
    job_plan = jobs.plan(SALESDATA, root, cfg, **plan_args)
    return jobs.Job(job_plan, root, cfg, http, "salesdata_sample.xlsx")


def test_plan_writes_nothing(tmp_path):
    job_plan = jobs.plan(SALESDATA, tmp_path / "root", config.load())
    assert job_plan.count == 2  # filters on: BMW and Jeep pass
    assert "К загрузке 2 лотов" in job_plan.describe("full")
    assert not (tmp_path / "root").exists()


def test_job_downloads_and_records_state(tmp_path):
    seen = []
    state = make_job(tmp_path, FakeHttp()).run(on_progress=lambda s: seen.append(s.done))
    assert state.status == jobs.DONE
    assert (state.total, state.done, state.photos, state.bytes_saved) == (2, 2, 4, 16)
    assert seen == [1, 2]
    saved = jobs.last_state(tmp_path)
    assert saved.status == jobs.DONE and saved.finished_at
    assert "скачано фото: 4" in saved.summary


def test_stop_ends_after_the_current_lot(tmp_path):
    job = None
    def stop_on_first_download():
        job.stop()
    job = make_job(tmp_path, FakeHttp(on_download=stop_on_first_download))
    state = job.run()
    assert state.status == jobs.STOPPED
    assert state.done == 1  # the lot being downloaded is finished, the next one is not started
    assert jobs.last_state(tmp_path).status == jobs.STOPPED


def test_refused_when_disk_is_short(tmp_path, monkeypatch):
    monkeypatch.setattr(photos, "free_bytes", lambda root: 1024)
    state = make_job(tmp_path, FakeHttp()).run()
    assert state.status == jobs.REFUSED
    assert "Не хватает места" in state.summary
    assert not (tmp_path / "photos").exists()


def test_unexpected_error_is_recorded_not_raised(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("disk on fire")
    monkeypatch.setattr(jobs.tasks, "prepare_lots", boom)
    state = make_job(tmp_path, FakeHttp()).run()
    assert state.status == jobs.FAILED and "disk on fire" in state.error
    assert jobs.last_state(tmp_path).status == jobs.FAILED


def test_runs_in_a_thread(tmp_path):
    job = make_job(tmp_path, FakeHttp())
    thread = threading.Thread(target=job.run)
    thread.start()
    thread.join(timeout=10)
    assert not thread.is_alive() and job.state.status == jobs.DONE


def test_no_state_yet(tmp_path):
    assert jobs.last_state(tmp_path) is None


def test_a_job_left_running_is_marked_interrupted(tmp_path):
    jobs._save(tmp_path, jobs.State(file="x.xlsx", total=10, done=3))
    state = jobs.mark_interrupted(tmp_path)
    assert state.status == jobs.INTERRUPTED and state.done == 3
    assert jobs.last_state(tmp_path).status == jobs.INTERRUPTED
    assert jobs.mark_interrupted(tmp_path) is None  # nothing to do the second time
