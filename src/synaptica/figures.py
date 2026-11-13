"""Study figures from PMC's open-access bucket (plan, step 23b; Aday, v121 option B).

Adapted from ``spikes/web/images.py`` (same repository). Rules (CLAUDE.md, "Licencias"):

- Only articles in PMC's open-access subset, read from NLM's open-data bucket on AWS
  (``pmc-oa-opendata``), whose per-article JSON carries the licence: only Creative Commons
  licences pass. Without one, no figure (4 of 979 measured in the spike).
- The article's Figure 1 (the first ``<fig>`` of its XML, not the first file of the
  bucket: in PMC13733655 that one is Figure 2), resized and re-encoded to WebP and **never
  cropped**, so it is also fine under ND licences. A large size and a thumbnail.
- Only for the studies the website shows in «Latest» (:func:`synaptica.site.news.latest`,
  at most 200), so never Nature, Science or Cell (metadata and links only) and never the
  media (their images have no clear licence).

What goes where (decision D10, private cache):

- ``derived/figures/figures.json`` (data branch, public): one row per study with the
  figure chosen, its bucket key, the licence, the authors' credit and the citation. No
  caption: it is a paragraph of the article, and those are not published. Studies without
  a figure keep a row with the reason, so they are not asked again every day.
- ``cache/figures/<pmcid>.webp`` and ``<pmcid>-t.webp`` (Actions cache): if they are gone,
  they are asked again from the bucket with the stored key. The downloaded original is not
  kept. Files of studies no longer shown are removed, so the cache stays small.

Idempotent: a study whose PMCID and files are up to date is skipped. One request at a
time, identified (``synaptica.http``).
"""

from __future__ import annotations

import datetime as dt
import io
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import httpx
from PIL import Image, ImageOps

from synaptica.config import get_paths
from synaptica.http import HttpError, Throttle, get_bytes, get_text
from synaptica.store import utc_today

log = logging.getLogger(__name__)

BUCKET = "https://pmc-oa-opendata.s3.amazonaws.com"
ARTICLE_URL = "https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"
FULL, THUMB = 760, 240  # longest side, in pixels (the spike's sizes)
QUALITY = 78
MIN_WIDTH = 300  # narrower than this is an icon or an inline formula, not a figure
MAX_BYTES = 20_000_000  # a figure file larger than this is not downloaded
MAX_PIXELS = 60_000_000  # Pillow refuses images above this ("decompression bombs")
MAX_FIGS = 3  # <fig> elements tried, in order, before giving up
# Reasons that may change: PMC adds an article to the bucket some days after PubMed.
RETRY_REASONS = {"not_in_bucket"}
IMAGE_EXT = re.compile(r"\.(jpe?g|png|gif|webp|tiff?)$", re.I)


@dataclass
class Result:
    shown: int = 0  # studies of «Latest» with a PMCID
    up_to_date: int = 0
    found: int = 0
    without: int = 0  # asked, and no figure that can be shown (reason in the row)
    refetched: int = 0  # metadata known, WebP gone from the cache
    failed: int = 0  # network or image errors: asked again next run
    removed: int = 0  # cached files of studies no longer shown


class NoFigure(Exception):
    """The article has no figure we can show; ``reason`` goes to its row."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# -- paths --------------------------------------------------------------------------------


def figures_path(derived_root: Path | None = None) -> Path:
    root = derived_root if derived_root is not None else get_paths().derived
    return root / "figures" / "figures.json"


def cache_dir(cache_root: Path | None = None) -> Path:
    root = cache_root if cache_root is not None else get_paths().cache
    return root / "figures"


def file_names(pmcid: str) -> tuple[str, str]:
    stem = pmcid.lower()
    return f"{stem}.webp", f"{stem}-t.webp"


def load_rows(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    return {row["study_id"]: row for row in json.loads(path.read_text(encoding="utf-8"))}


def save_rows(path: Path, rows: dict[str, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps([rows[k] for k in sorted(rows)], ensure_ascii=False, indent=1) + "\n"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


# -- which studies ------------------------------------------------------------------------


def studies_to_show(warehouse: Path) -> list[dict[str, Any]]:
    """The studies of «Latest» that have a PMCID, as the website selects them."""
    from synaptica.site import news  # the site's own selection, so both never disagree

    with duckdb.connect(str(warehouse), read_only=True) as con:
        con.execute("set TimeZone = 'UTC'")
        (as_of,) = con.execute("select max(entered_on) from main.dim_study").fetchone()
        if as_of is None:
            return []
        rows = news.latest(con, as_of)
    return [r for r in rows if r.get("pmcid")]


# -- the article: licence, authors, Figure 1 ----------------------------------------------


def _text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", value)).strip()


def licence(meta: dict[str, Any], xml: str) -> tuple[str, str | None]:
    """Name (``CC BY 4.0``) and URL of the article's licence; NoFigure if not CC.

    The bucket's JSON says which licence (``license_code``) but not its version; the URL
    in the article's XML gives it, and is used only when both name the same licence."""
    if not meta.get("is_pmc_openaccess"):
        raise NoFigure("not_open_access")
    code = " ".join((meta.get("license_code") or "").upper().split())
    if not code.startswith("CC"):
        raise NoFigure("no_cc_licence")
    for m in re.finditer(r"https?://creativecommons\.org/(licenses|publicdomain)/([a-z-]+)/"
                         r"(\d\.\d)/?", xml):  # fmt: skip
        name = "CC0" if m[2] == "zero" else "CC " + m[2].upper()
        if name == code:
            return f"{name} {m[3]}", m[0]
    return code, None


def credit(xml: str, fallback: list[str] | None = None) -> str:
    """Authors as credited under the figure: «Smith», «Smith, Jones» or «Smith et al.».
    From the article's XML; the study's own author list when the XML has none."""
    names = []
    for block in re.findall(r'<contrib [^>]*contrib-type="author".*?</contrib>', xml, re.S):
        m = re.search(r"<surname>(.*?)</surname>|<collab[^>]*>(.*?)</collab>", block, re.S)
        if m:
            names.append(_text(m[1] or m[2]))
    names = [n for n in names if n] or [a for a in fallback or [] if a]
    if not names:
        raise NoFigure("no_author")
    if len(names) == 1:
        return names[0]
    return f"{names[0]}, {names[1]}" if len(names) == 2 else f"{names[0]} et al."


def figure_candidates(xml: str) -> list[tuple[str | None, str]]:
    """(label, file stem) of the first figures, in the article's order. Supplementary
    figures and graphical abstracts are not Figure 1."""
    out = []
    for block in re.findall(r"<fig[ >].*?</fig>", xml, re.S):
        label = re.search(r"<label>(.*?)</label>", block, re.S)
        label_text = _text(label[1]) if label else None
        if label_text and re.search(r"\bS\d", label_text):
            continue
        # Only the figure's own <graphic>: its caption can hold links or inline images.
        caption_free = re.sub(r"<caption>.*?</caption>", "", block, flags=re.S)
        if m := re.search(r'<graphic\b[^>]*xlink:href="([^"]+)"', caption_free):
            out.append((label_text, Path(m[1]).stem))
        if len(out) == MAX_FIGS:
            break
    return out


# -- images -------------------------------------------------------------------------------


def encode(raw: bytes, full: Path, thumb: Path) -> tuple[int, int]:
    """Write both WebP sizes; (width, height) of the large one. Never cropped: the image
    is scaled to fit in a square of the given side, keeping its proportions."""
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        with Image.open(io.BytesIO(raw)) as im:
            if im.width < MIN_WIDTH:
                raise NoFigure("too_small")
            im = ImageOps.exif_transpose(im)
            alpha = im.mode in ("RGBA", "LA") or "transparency" in im.info
            im = im.convert("RGBA" if alpha else "RGB")
            size = (0, 0)
            for side, dst in ((FULL, full), (THUMB, thumb)):
                copy = im.copy()
                copy.thumbnail((side, side), Image.Resampling.LANCZOS)
                dst.parent.mkdir(parents=True, exist_ok=True)
                copy.save(dst, "WEBP", quality=QUALITY, method=6)
                if side == FULL:
                    size = copy.size
    except Image.DecompressionBombError as exc:
        raise NoFigure("too_large") from exc
    except (Image.UnidentifiedImageError, OSError) as exc:  # NoFigure is neither
        raise NoFigure("unreadable_image") from exc
    return size


# -- the bucket ---------------------------------------------------------------------------


class Bucket:
    def __init__(self, client: httpx.Client, throttle: Throttle | None = None) -> None:
        self.client = client
        self.throttle = throttle or Throttle(5)

    def _get(self, url: str, **params: Any) -> bytes:
        self.throttle.wait()
        return get_bytes(self.client, url, params=params or None)

    def listing(self, pmcid: str) -> dict[str, int]:
        """Key -> size of the article's files (every version)."""
        self.throttle.wait()
        xml = get_text(self.client, BUCKET + "/",
                       params={"list-type": "2", "prefix": f"{pmcid}."})  # fmt: skip
        return {k: int(s) for k, s in
                re.findall(r"<Key>([^<]+)</Key>.*?<Size>(\d+)</Size>", xml, re.S)}  # fmt: skip

    def get(self, key: str) -> bytes:
        return self._get(f"{BUCKET}/{key}")


def _latest_version(keys: dict[str, int], pmcid: str) -> str | None:
    """Folder of the newest version (``PMC1.2``): numeric order, so .10 comes after .9."""
    versions = [k.split("/", 1)[0] for k in keys if k.endswith(".json")]
    if not versions:
        return None
    return max(versions, key=lambda v: int(v.removeprefix(f"{pmcid}.") or 0))


def fetch(bucket: Bucket, study: dict[str, Any], out_dir: Path, today: dt.date) -> dict:
    """The row of one study, writing its two WebP files when there is a figure."""
    pmcid = study["pmcid"]
    row: dict[str, Any] = {"study_id": study["study_id"], "pmcid": pmcid,
                           "checked_on": today.isoformat()}  # fmt: skip
    try:
        keys = bucket.listing(pmcid)
        version = _latest_version(keys, pmcid)
        if version is None:
            raise NoFigure("not_in_bucket")
        meta = json.loads(bucket.get(f"{version}/{version}.json"))
        xml = bucket.get(f"{version}/{version}.xml").decode("utf-8", "replace")
        name, url = licence(meta, xml)
        who = credit(xml, study.get("authors"))
        media = {Path(k).stem: k for k in keys
                 if k.startswith(version + "/") and IMAGE_EXT.search(k)}  # fmt: skip
        full_name, thumb_name = file_names(pmcid)
        for label, stem in figure_candidates(xml):
            key = media.get(stem)
            if key is None or keys[key] > MAX_BYTES:
                continue
            try:
                w, h = encode(bucket.get(key), out_dir / full_name, out_dir / thumb_name)
            except NoFigure as exc:
                if exc.reason == "too_small":
                    continue
                raise
            return row | {
                "status": "ok", "label": label, "source_key": key, "file": full_name,
                "thumb": thumb_name, "width": w, "height": h, "license": name,
                "license_url": url, "credit": who, "citation": meta.get("citation"),
                "source_url": ARTICLE_URL.format(pmcid=pmcid),
            }  # fmt: skip
        raise NoFigure("no_figure")
    except NoFigure as exc:
        return row | {"status": "none", "reason": exc.reason}


def refetch(bucket: Bucket, row: dict[str, Any], out_dir: Path) -> None:
    """The WebP files of a known figure, gone from the cache (Actions drops a cache that
    is not used for 7 days): asked again with the stored key, same sizes."""
    w, h = encode(bucket.get(row["source_key"]), out_dir / row["file"], out_dir / row["thumb"])
    if (w, h) != (row["width"], row["height"]):
        log.warning("Figure of %s changed size: %sx%s", row["study_id"], w, h)
        row.update(width=w, height=h)


def run(
    client: httpx.Client,
    studies: list[dict[str, Any]],
    *,
    derived_root: Path | None = None,
    cache_root: Path | None = None,
    today: dt.date | None = None,
    throttle: Throttle | None = None,
) -> Result:
    today = today or utc_today()
    path, out_dir = figures_path(derived_root), cache_dir(cache_root)
    rows = load_rows(path)
    bucket = Bucket(client, throttle)
    result = Result(shown=len(studies))
    keep: set[str] = set()
    for study in studies:
        sid, old = study["study_id"], rows.get(study["study_id"])
        try:
            if old and old["pmcid"] == study["pmcid"]:
                if old["status"] == "ok":
                    keep |= {old["file"], old["thumb"]}
                    if (out_dir / old["file"]).exists() and (out_dir / old["thumb"]).exists():
                        result.up_to_date += 1
                    else:
                        refetch(bucket, old, out_dir)
                        result.refetched += 1
                    continue
                if old["reason"] not in RETRY_REASONS or old["checked_on"] >= today.isoformat():
                    result.up_to_date += 1
                    continue
            row = fetch(bucket, study, out_dir, today)
        except (HttpError, httpx.HTTPError, NoFigure) as exc:
            log.warning("Figure of %s not fetched: %s", sid, exc)
            result.failed += 1
            continue
        rows[sid] = row
        if row["status"] == "ok":
            keep |= {row["file"], row["thumb"]}
            result.found += 1
        else:
            result.without += 1
    save_rows(path, rows)
    if out_dir.exists():
        for f in out_dir.glob("*.webp"):
            if f.name not in keep:
                f.unlink()
                result.removed += 1
    return result
