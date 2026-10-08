import urllib.error
from pathlib import Path

import pytest

from copart_archive import net


class FakeResponse:
    def __init__(self, body): self.body = body
    def read(self): return self.body
    def __enter__(self): return self
    def __exit__(self, *exc): return False


def test_retries_then_succeeds(monkeypatch):
    calls = []
    def urlopen(request, timeout):
        calls.append(request.full_url)
        if len(calls) < 3:
            raise urllib.error.HTTPError(request.full_url, 503, "busy", {}, None)
        return FakeResponse(b"ok")
    monkeypatch.setattr(net.urllib.request, "urlopen", urlopen)
    http = net.Http(delay=0, retries=3)
    assert http.get("https://x/y") == b"ok"
    assert len(calls) == 3


def test_404_is_not_retried(monkeypatch):
    calls = []
    def urlopen(request, timeout):
        calls.append(1)
        raise urllib.error.HTTPError(request.full_url, 404, "gone", {}, None)
    monkeypatch.setattr(net.urllib.request, "urlopen", urlopen)
    with pytest.raises(net.NotFound):
        net.Http(delay=0).get("https://x/y")
    assert len(calls) == 1


def test_gives_up_after_retries(monkeypatch):
    def urlopen(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 503, "busy", {}, None)
    monkeypatch.setattr(net.urllib.request, "urlopen", urlopen)
    with pytest.raises(net.HttpError):
        net.Http(delay=0, retries=2).get("https://x/y")


def test_download_is_atomic(monkeypatch, tmp_path):
    monkeypatch.setattr(net.Http, "get", lambda self, url: b"jpegdata")
    target = tmp_path / "01.jpg"
    assert net.Http(delay=0).download("https://x/01.jpg", target) == 8
    assert target.read_bytes() == b"jpegdata"
    assert list(tmp_path.iterdir()) == [target]  # no .part left behind


def test_empty_file_is_an_error(monkeypatch, tmp_path):
    monkeypatch.setattr(net.Http, "get", lambda self, url: b"")
    with pytest.raises(net.HttpError):
        net.Http(delay=0).download("https://x/01.jpg", tmp_path / "01.jpg")


def test_bad_json(monkeypatch):
    monkeypatch.setattr(net.Http, "get", lambda self, url: b"<html>")
    with pytest.raises(net.HttpError):
        net.Http(delay=0).get_json("https://x/y")
