"""Plain HTTP with pacing, retries and atomic downloads."""

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

USER_AGENT = "copart-archive/0.1"
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})


class HttpError(OSError):
    def __init__(self, url: str, status: int | None, message: str = ""):
        super().__init__(f"{status or 'нет ответа'} {url} {message}".strip())
        self.url = url
        self.status = status


class NotFound(HttpError):
    """404 — Copart removes a lot from inventory soon after it is sold."""


class Http:
    def __init__(self, delay: float = 0.5, retries: int = 3, timeout: float = 30.0,
                 user_agent: str = USER_AGENT):
        self.delay = delay
        self.retries = retries
        self.timeout = timeout
        self.user_agent = user_agent
        self._last_request = 0.0

    def _wait(self) -> None:
        pause = self.delay - (time.monotonic() - self._last_request)
        if pause > 0:
            time.sleep(pause)
        self._last_request = time.monotonic()

    def get(self, url: str) -> bytes:
        request = urllib.request.Request(url, headers={"User-Agent": self.user_agent,
                                                      "Accept": "*/*"})
        for attempt in range(1, self.retries + 1):
            self._wait()
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return response.read()
            except urllib.error.HTTPError as error:
                if error.code == 404:
                    raise NotFound(url, 404) from error
                if error.code not in RETRY_STATUS or attempt == self.retries:
                    raise HttpError(url, error.code) from error
            except OSError as error:  # timeouts, dns, reset
                if attempt == self.retries:
                    raise HttpError(url, None, str(error)) from error
            time.sleep(self.delay * 2 ** attempt)  # back off before trying again
        raise HttpError(url, None, "повторы закончились")

    def get_json(self, url: str) -> dict:
        body = self.get(url)
        try:
            return json.loads(body)
        except ValueError as error:
            raise HttpError(url, None, "ответ не JSON") from error

    def download(self, url: str, target: Path) -> int:
        """Writes next to the target first, so an interrupted run leaves no half file."""
        body = self.get(url)
        if not body:
            raise HttpError(url, None, "пустой файл")
        tmp = target.with_name(target.name + ".part")
        tmp.write_bytes(body)
        os.replace(tmp, target)
        return len(body)
