"""Copart's own image API, the address of which comes in the Sales Data file.

"Image URL" in the subscription points at
https://inventoryv2.copart.io/v1/lotImages/<lot> and returns every photo of the
lot in three sizes. The engine sound recording comes in the same list and is
marked with its own flag.
"""

from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from .config import PHOTO_QUALITIES
from .net import Http

API = "https://inventoryv2.copart.io/v1/lotImages/{lot}"


@dataclass(frozen=True)
class Photo:
    sequence: int
    url: str
    quality: str


def api_url(lot: str, given: str | None = None) -> str:
    """The address from the subscription if there is one, forced to https."""
    if not given:
        return API.format(lot=lot)
    parts = urlsplit(given.strip())
    return urlunsplit(("https", parts.netloc, parts.path, parts.query, ""))


def _pick(links: list[dict], quality: str) -> dict | None:
    """One link of a photo. Falls back to a smaller size when HD is missing."""
    usable = [l for l in links if not l.get("isEngineSound") and (l.get("url") or "").strip()]
    if quality == "high_res":
        return next((l for l in usable if l.get("isHdImage")), None) or _pick(usable, "full")
    if quality == "thumbnail":
        return next((l for l in usable if l.get("isThumbNail")), None)
    return next((l for l in usable if not l.get("isHdImage") and not l.get("isThumbNail")), None)


def parse(payload: dict, quality: str) -> list[Photo]:
    if quality not in PHOTO_QUALITIES:
        raise ValueError(f"качество {quality!r}, ожидается одно из {PHOTO_QUALITIES}")
    photos = []
    for item in payload.get("lotImages") or []:
        links = item.get("link") or []
        if any(l.get("isEngineSound") for l in links):
            continue  # звук двигателя, не фотография
        link = _pick(links, quality)
        if link:
            photos.append(Photo(sequence=int(item.get("sequence") or len(photos) + 1),
                                url=link["url"].strip(), quality=quality))
    return sorted(photos, key=lambda p: p.sequence)


def fetch(lot: str, quality: str, http: Http, given_url: str | None = None) -> list[Photo]:
    """Photos of a lot. Raises net.NotFound when the lot has left the inventory."""
    return parse(http.get_json(api_url(lot, given_url)), quality)
