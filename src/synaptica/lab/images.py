"""The illustration of each Neuro Lab technique's protocol (v252; Sofía's sheet, row 15:
«una especie de protocolo, con imágenes ilustrativas»).

One Wikimedia Commons file per technique, named in its table row (``image``), chosen as a
diagram of how the technique is done (never a result shown as if it were the method).
``syn lab images`` (by hand, never in the pipeline; no LLM) reads its licence, author and
page from Commons, accepts it only under a free licence (:data:`FREE`), downloads the
rendering Commons makes (a PNG for an SVG) and writes it as WebP into
``site/static/img/lab/``, as the study figures are (the site loads nothing from another
domain). ``images.json`` keeps its credit, which the page shows next to it.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import httpx

from synaptica.http import Throttle, get_bytes, get_json
from synaptica.store import utc_today
from synaptica.wiki import read_json, write_json

COMMONS = "https://commons.wikimedia.org/w/api.php"
IMAGES = Path(__file__).with_name("images.json")
STATIC = Path(__file__).resolve().parents[3] / "site" / "static" / "img" / "lab"
WIDTH = 1000  # the rendering asked for; encoded to fit FULL (figures.py)
FREE = re.compile(r"^(CC0|CC BY(-SA)? \d(\.\d)?|Public domain)$", re.I)


def _plain(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html or "")).strip()


def info(client: httpx.Client, filename: str, throttle: Throttle) -> dict[str, Any] | None:
    """Licence, author, page and rendering URL of a Commons file; None if it is not there."""
    throttle.wait()
    body = get_json(client, COMMONS, params={
        "action": "query", "titles": f"File:{filename}", "prop": "imageinfo",
        "iiprop": "url|extmetadata|size", "iiurlwidth": WIDTH, "format": "json",
        "formatversion": "2",
    })  # fmt: skip
    page = ((body.get("query") or {}).get("pages") or [{}])[0]
    if page.get("missing") or not page.get("imageinfo"):
        return None
    ii = page["imageinfo"][0]
    meta = ii.get("extmetadata") or {}

    def value(key: str) -> str:
        return _plain((meta.get(key) or {}).get("value", ""))

    return {"file": filename, "licence": value("LicenseShortName"),
            "licence_url": value("LicenseUrl") or None, "author": value("Artist"),
            "source_url": ii.get("descriptionurl"),
            "render_url": ii.get("thumburl") or ii.get("url")}  # fmt: skip


def update(client: httpx.Client, techniques: list[dict[str, Any]], *,
           path: Path | None = None, static: Path | None = None,
           throttle: Throttle | None = None) -> tuple[list[str], list[str]]:  # fmt: skip
    """Fetch the image of every technique that names one (kept when its file and licence
    did not change). Returns (stored, refused or failed)."""
    from synaptica.figures import NoFigure, encode

    path, static = path or IMAGES, static or STATIC
    throttle = throttle or Throttle(2)
    old = read_json(path, "techniques")
    out: dict[str, Any] = {}
    stored, failed = [], []
    for tech in techniques:
        tid, filename = tech["id"], tech.get("image")
        if not filename:
            continue
        if (prev := old.get(tid)) and prev["file"] == filename and (static / prev["webp"]).exists():
            out[tid] = prev
            continue
        got = info(client, filename, throttle)
        if got is None:
            failed.append(f"{tid}: {filename} is not on Commons")
            continue
        if not FREE.match(got["licence"]) or not got["author"]:
            failed.append(f"{tid}: {filename}: licence «{got['licence']}» or author missing")
            continue
        throttle.wait()
        raw = get_bytes(client, got.pop("render_url"))
        webp = f"{tid}.webp"
        thumb = static / f"{tid}-thumb.webp"  # encode() writes one; the page does not use it
        try:
            width, height = encode(raw, static / webp, thumb)
        except NoFigure as exc:
            failed.append(f"{tid}: {filename}: {exc}")
            continue
        finally:
            thumb.unlink(missing_ok=True)
        out[tid] = got | {"webp": webp, "width": width, "height": height,
                          "retrieved": utc_today().isoformat()}  # fmt: skip
        stored.append(tid)
    write_json(path, {
        "note": "The illustration of each Neuro Lab protocol: a Wikimedia Commons file under "
        "a free licence, as WebP in site/static/img/lab/. Written by `syn lab images`; do not "
        "edit by hand.",
        "techniques": out,
    })  # fmt: skip
    return stored, failed


def load(path: Path | None = None) -> dict[str, dict[str, Any]]:
    return read_json(path or IMAGES, "techniques")
