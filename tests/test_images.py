import pytest

from copart_archive import images

PAYLOAD = {
    "imgCount": 2,
    "lotImages": [
        {"sequence": 2, "link": [
            {"url": "https://cs.copart.com/a_ful.jpg ", "isThumbNail": False, "isHdImage": False},
            {"url": "https://cs.copart.com/a_hrs.jpg", "isThumbNail": False, "isHdImage": True},
            {"url": "https://cs.copart.com/a_thb.jpg", "isThumbNail": True, "isHdImage": False},
        ]},
        {"sequence": 1, "link": [
            {"url": "https://cs.copart.com/b_ful.jpg", "isThumbNail": False, "isHdImage": False},
        ]},
        {"sequence": 90, "link": [
            {"url": "https://cs.copart.com/sound.mp3", "isEngineSound": True},
        ]},
    ],
}


def test_full_quality_sorted_by_sequence():
    photos = images.parse(PAYLOAD, "full")
    assert [(p.sequence, p.url) for p in photos] == [
        (1, "https://cs.copart.com/b_ful.jpg"),
        (2, "https://cs.copart.com/a_ful.jpg"),  # trailing space in the API is stripped
    ]


def test_engine_sound_is_not_a_photo():
    assert all("sound" not in p.url for p in images.parse(PAYLOAD, "high_res"))


def test_high_res_falls_back_to_full():
    photos = {p.sequence: p.url for p in images.parse(PAYLOAD, "high_res")}
    assert photos[2].endswith("_hrs.jpg")
    assert photos[1].endswith("_ful.jpg")  # that photo has no HD variant


def test_thumbnail_quality():
    assert [p.url for p in images.parse(PAYLOAD, "thumbnail")] == ["https://cs.copart.com/a_thb.jpg"]


def test_unknown_quality():
    with pytest.raises(ValueError):
        images.parse(PAYLOAD, "huge")


def test_empty_payload():
    assert images.parse({}, "full") == []


@pytest.mark.parametrize("given,expected", [
    (None, "https://inventoryv2.copart.io/v1/lotImages/123"),
    ("http://inventoryv2.copart.io/v1/lotImages/123?country=us", 
     "https://inventoryv2.copart.io/v1/lotImages/123?country=us"),  # http from the file -> https
    (" http://host/v1/lotImages/123 ", "https://host/v1/lotImages/123"),
])
def test_api_url(given, expected):
    assert images.api_url("123", given) == expected


def test_fetch_uses_injected_http():
    class FakeHttp:
        def get_json(self, url):
            self.url = url
            return PAYLOAD
    http = FakeHttp()
    photos = images.fetch("123", "full", http)
    assert http.url == "https://inventoryv2.copart.io/v1/lotImages/123"
    assert len(photos) == 2
