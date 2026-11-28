"""The illustration of each Neuro Lab protocol (src/synaptica/lab/images.py, v252): a free
Wikimedia Commons file, self-hosted as WebP with its credit. No network: Commons answers
through ``httpx.MockTransport`` and the image is drawn for the test."""

from __future__ import annotations

import io
import json
from pathlib import Path

import httpx
from PIL import Image

from synaptica.http import Throttle
from synaptica.lab import images

LICENCES = {"Perfusion_Diagram.jpg": "CC BY-SA 4.0", "Logo.png": "Fair use"}


def png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (900, 600), "white").save(buf, "PNG")
    return buf.getvalue()


def commons(asked: list[str]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(request.url.host)
        if request.url.host == "upload.wikimedia.org":
            return httpx.Response(200, content=png())
        name = request.url.params["titles"].removeprefix("File:")
        if name not in LICENCES:
            return httpx.Response(200, json={"query": {"pages": [{"missing": True}]}})
        meta = {
            "LicenseShortName": {"value": LICENCES[name]},
            "Artist": {"value": '<a href="//x">J dotter</a>'},
            "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0"},
        }
        return httpx.Response(200, json={"query": {"pages": [{"imageinfo": [{
            "extmetadata": meta, "descriptionurl": f"https://commons.wikimedia.org/wiki/{name}",
            "thumburl": f"https://upload.wikimedia.org/x/{name}.png"}]}]}})  # fmt: skip

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_only_a_free_image_is_kept_as_webp_with_its_credit(tmp_path: Path) -> None:
    techs = [{"id": "perfusion", "image": "Perfusion_Diagram.jpg"},
             {"id": "western-blot", "image": "Logo.png"},
             {"id": "eeg", "image": "Gone.png"}, {"id": "fmri"}]  # fmt: skip
    path, static, asked = tmp_path / "images.json", tmp_path / "img", []
    stored, failed = images.update(commons(asked), techs, path=path, static=static,
                                   throttle=Throttle(1000))  # fmt: skip
    assert stored == ["perfusion"]
    assert failed == ["western-blot: Logo.png: licence «Fair use» or author missing",
                      "eeg: Gone.png is not on Commons"]  # fmt: skip
    got = json.loads(path.read_text())["techniques"]
    assert set(got) == {"perfusion"} and got["perfusion"]["author"] == "J dotter"
    assert got["perfusion"]["licence"] == "CC BY-SA 4.0" and got["perfusion"]["width"] == 760
    assert sorted(p.name for p in static.iterdir()) == ["perfusion.webp"]  # no thumbnail
    again: list[str] = []
    assert images.update(commons(again), techs[:1], path=path, static=static,
                         throttle=Throttle(1000)) == ([], [])  # fmt: skip
    assert again == []  # the same file, already stored: not asked again


def test_the_technique_page_has_her_three_parts_and_credits_the_image(tmp_path, monkeypatch):
    from synaptica.site.build import SiteBuilder
    from synaptica.site.check import check_site

    path = tmp_path / "images.json"
    path.write_text(json.dumps({"techniques": {"perfusion": {
        "file": "Perfusion_Diagram.jpg", "licence": "CC BY-SA 4.0",
        "licence_url": "https://creativecommons.org/licenses/by-sa/4.0", "author": "J dotter",
        "source_url": "https://commons.wikimedia.org/wiki/File:Perfusion_Diagram.jpg",
        "webp": "perfusion.webp", "width": 760, "height": 567}}}))  # fmt: skip
    monkeypatch.setattr(images, "IMAGES", path)
    out = tmp_path / "site"
    SiteBuilder(out, images={"hero": {"files": [], "author": "Sofía",
                                      "licence": "CC BY-SA 4.0"}}).build()  # fmt: skip
    page = (out / "es" / "lab" / "perfusion.html").read_text()
    heads = [page.index(h) for h in ("Descripción general", "<h2>Protocolo", "Estudios recientes")]
    assert heads == sorted(heads)
    assert 'data-figure-credit="J dotter"' in page and "CC BY-SA 4.0" in page
    assert "gap-lab_protocol" in page  # its steps: a gap until they exist
    assert "img/lab/" not in (out / "es" / "lab" / "eeg.html").read_text()  # no image: none
    assert check_site(out).passed
