"""Images for the second round of mock-ups (v2), self-hosted so the site loads nothing from
other domains at run time. Writes ``data/images.json`` (who made each image and its licence)
and the WebP files in ``v2/img/``.

- Cajal's drawings: Wikimedia Commons (API ``imageinfo``), public domain or Wellcome CC BY 4.0;
  author and licence are read from Commons, never typed by hand. Cleaned to greys so the
  page can print them as ink (light) or as light on dark (``filter: invert``).
- Study figures: only articles in PMC's open-access subset, from NLM's open-data bucket on
  AWS (``pmc-oa-opendata``), whose per-article JSON carries the licence. Figure 1, resized
  and re-encoded, never cropped (also fine for ND licences). Not for Nature, Science or Cell
  (metadata and links only) and not for media news (their images have no clear licence).
- Atlas: captured from our own S3 viewer (``spikes/s3/site/c``) with headless Brave; each
  atlas in its own image, because Waxholm (CC BY 4.0) and Julich-Brain (CC BY-NC-SA 4.0)
  never share a derived file. Done once by hand; see README.

    uv run python spikes/web/images.py   # network: Commons API and the PMC bucket, cached
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from synaptica.http import make_client

HERE = Path(__file__).parent
OUT = HERE / "v2/img"
CACHE = HERE / "data/sources/images"
COMMONS = "https://commons.wikimedia.org/w/api.php"
BUCKET = "https://pmc-oa-opendata.s3.amazonaws.com"
CAJAL = {
    "purkinje": "File:Purkinje cell by Cajal.png",
    "cortex": "File:Cajal actx inter.jpg",
    "hippocampus": "File:CajalHippocampus.jpeg",
    "cerebellum": "File:CajalCerebellum.jpg",
    "tectum": "File:SparrowTectum.jpg",
}
S3_DATA = HERE.parent / "s3/site/data"
# Captures of our viewer: the attribution is the one S3 recorded for each atlas.
ATLAS = {"rat": ("atlas-rata-waxholm.webp", "waxholm"),
         "human": ("atlas-humano-julich.webp", "julich")}  # fmt: skip


def strip_html(value: str | None) -> str | None:
    if not value:
        return None
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", value)).strip() or None


def cached(client: Any, url: str, name: str, **params: Any) -> bytes:
    path = CACHE / name
    if not path.exists():
        r = client.get(url, params=params or None)
        r.raise_for_status()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(r.content)
    return path.read_bytes()


def webp(src: Path, dst: Path, width: int, *extra: str) -> tuple[int, int]:
    subprocess.run(["magick", str(src), *extra, "-resize", f"{width}x{width}>", "-strip",
                    "-quality", "78", str(dst)], check=True)  # fmt: skip
    w, h = subprocess.run(["magick", "identify", "-format", "%w %h", str(dst)], check=True,
                          capture_output=True, text=True).stdout.split()  # fmt: skip
    return int(w), int(h)


def cajal(client: Any) -> dict[str, Any]:
    out = {}
    for key, title in CAJAL.items():
        body = json.loads(cached(client, COMMONS, f"commons-{key}.json", action="query",
                                 titles=title, prop="imageinfo", format="json",
                                 iiprop="url|extmetadata", iiurlwidth=1100))  # fmt: skip
        info = next(iter(body["query"]["pages"].values()))["imageinfo"][0]
        meta = info["extmetadata"]
        raw = CACHE / f"cajal-{key}{Path(info['thumburl']).suffix}"
        if not raw.exists():
            raw.write_bytes(cached(client, info["thumburl"], raw.name))
        # Greys, paper to white and ink to black: the page decides how to print it.
        w, h = webp(raw, OUT / f"cajal-{key}.webp", 640, "-colorspace", "gray",
                    "-level", "18%,82%")  # fmt: skip
        out[key] = {
            "file": f"cajal-{key}.webp", "width": w, "height": h,
            "title": strip_html(meta.get("ObjectName", {}).get("value")) or title[5:],
            # Chosen from Commons' «Scientific works by Santiago Ramón y Cajal»; its Artist
            # field is sometimes empty or names the uploader, so it is kept apart.
            "author": "Santiago Ramón y Cajal",
            "commons_artist": strip_html(meta.get("Artist", {}).get("value")),
            "date": strip_html(meta.get("DateTimeOriginal", {}).get("value")),
            "license": meta.get("LicenseShortName", {}).get("value"),
            "credit": strip_html(meta.get("Credit", {}).get("value")),
            "source_url": info["descriptionurl"],
        }  # fmt: skip
    return out


def fig_label(xml: str, stem: str) -> str | None:
    """The figure's own label in the article («Figure 1»), or «graphical abstract»."""
    for block in re.findall(r"<fig[ >].*?</fig>", xml, re.S):
        if re.search(rf'href="{re.escape(stem)}(\.\w+)?"', block):
            label = re.search(r"<label>(.*?)</label>", block, re.S)
            return strip_html(label.group(1)) if label else None
    if re.search(r'abstract-type="graphical"', xml) and stem.startswith("ga"):
        return "graphical abstract"
    return None


def figures(client: Any, studies: list[dict[str, Any]]) -> dict[str, Any]:
    out = {}
    for s in studies:
        pmcid = s.get("pmcid")
        if not pmcid:
            continue
        listing = cached(client, BUCKET + "/", f"pmc-{pmcid}-list.xml", **{
            "list-type": "2", "prefix": f"{pmcid}."}).decode()  # fmt: skip
        keys = re.findall(r"<Key>([^<]+\.json)</Key>", listing)
        if not keys:
            continue  # not in the open-access subset
        meta = json.loads(cached(client, f"{BUCKET}/{keys[-1]}", f"pmc-{pmcid}.json"))
        lic = meta.get("license_code") or ""
        if not meta.get("is_pmc_openaccess") or not lic.upper().startswith("CC"):
            continue
        media = [u.split("?")[0].removeprefix("s3://pmc-oa-opendata/")
                 for u in meta.get("media_urls") or []
                 if re.search(r"\.(jpe?g|png|gif|webp)\?", u, re.I)]  # fmt: skip
        # A graphical abstract first (made to be shown alone), then the figures in order.
        media.sort(key=lambda k: not re.match(r"ga\d", Path(k).name))
        xml = cached(client, f"{BUCKET}/{keys[-1][:-5]}.xml", f"pmc-{pmcid}.xml").decode()
        for key in media:
            raw = CACHE / f"pmc-{pmcid}-{Path(key).name}"
            if not raw.exists():
                raw.write_bytes(cached(client, f"{BUCKET}/{key}", raw.name))
            name = f"fig-{pmcid.lower()}.webp"
            w, h = webp(raw, OUT / name, 760)
            if w >= 300:  # icons and inline formulas are not figures
                webp(raw, OUT / name.replace(".webp", "-t.webp"), 240)  # list thumbnail
                break
        else:
            (OUT / name).unlink(missing_ok=True)
            (OUT / name.replace(".webp", "-t.webp")).unlink(missing_ok=True)
            continue
        out[s["study_id"]] = {
            "file": name, "thumb": name.replace(".webp", "-t.webp"), "width": w, "height": h,
            "label": fig_label(xml, Path(key).stem),
            "license": lic, "pmcid": pmcid, "citation": meta.get("citation"),
            "source_url": f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/",
        }  # fmt: skip
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    data = json.loads((HERE / "data/mockup.json").read_text(encoding="utf-8"))
    studies = data["latest"] + data["s5"]  # never data["nsc"]: Nature, Science, Cell
    with make_client() as client:
        result = {"cajal": cajal(client), "figures": figures(client, studies)}
    result["atlas"] = {
        k: {"file": f, **json.loads((S3_DATA / d / "licence.json").read_text(encoding="utf-8"))}
        for k, (f, d) in ATLAS.items()
    }
    (HERE / "data/images.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(f"cajal {len(result['cajal'])}, figures {len(result['figures'])}")


if __name__ == "__main__":
    main()
