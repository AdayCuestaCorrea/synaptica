"""``syn atlas build``: the data files the Neuro Atlas viewer loads, one folder per atlas.

Copied and adapted from ``spikes/s3/build_assets.py`` (spike S3, Phase 0) for Neuro Atlas
(Phase 2, SCOPE v160; ADR D3). What changed from the spike: paths are arguments, downloads go
through :mod:`synaptica.http` (identified, with retries), the measurements of other Waxholm
resolutions and mock-up B's test regions are gone, and the pairs come from ``pairs.toml``.

Run by hand when an atlas changes, never in the daily pipeline (decision of Aday, SCOPE v160).
Needs the optional group: ``uv sync --group atlas``. It reads the download cache and fetches
only what is missing there (BrainGlobe and siibra download their own files into it).

Writes into ``out`` (by default ``site/static/atlas/``, committed and copied by ``syn site``)::

    waxholm/  labels.nii.gz, labels.json, licence.json, coords.json
    julich/   labels.nii.gz, labels.json, licence.json, coords.json
    cerebra/, cit168/, icbm_wm/   labels.nii.gz, labels.json, licence.json  (human layers)
    bigbrain/ stain.nii.gz, licence.json     (real stain of the human, on request)
    nissl/    sNNN.webp, index.json, licence.json   (real Nissl of the rat, 2D only)
    pairs.json      rat ↔ human pairs: IDs and names only, grade pending Sofía
    manifest.json   sizes per atlas against the 3 MB budget of D3

Each atlas has its own folder and nothing derived combines two atlases (CC BY 4.0 and
CC BY-NC-SA 4.0, among others; CLAUDE.md, "Licencias"). The human layers are separate files
that the viewer shows one under the other; ``pairs.json`` holds no geometry.

Conventions shared by both brains, so the viewers look at them the same way:
- Coordinates in millimetres, RAS (x to the right, y to the front, z up), centred on the brain.
- Every voxel value points to one row of ``labels.json``: the atlas ID plus its side ("L" or
  "R"). Labels are compact indices (1..N, 0 = background), not the atlas IDs, so the colour
  table stays small and the side fits in the same value.

Idempotent: same cache in, same files out.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import tomllib
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from synaptica.atlas import layers as cb
from synaptica.atlas import nissl, palette
from synaptica.atlas.coords import WHS_VOXEL_MM, human_mni_map, rat_flat_map
from synaptica.atlas.licences import ICBM_WM_MIN, LICENCES
from synaptica.atlas.volumes import (
    add_centroids,
    flat_skull,
    majority_downsample,
    save_nifti,
    write_json,
)

PAIRS_FILE = Path(__file__).with_name("pairs.toml")
BUDGET_BYTES = 3_000_000  # per atlas, compressed (ADR D3)
ATLASES = ("waxholm", "julich", "bigbrain", "cerebra", "cit168", "icbm_wm", "nissl")
INITIAL_LOAD = {"rat": ("waxholm",), "human": ("julich", "cerebra", "cit168", "icbm_wm")}
ON_DEMAND = ("bigbrain", "nissl")

BG_ATLAS = "whs_sd_rat_39um"
BG_TERMINOLOGY = (
    "brainglobe/brainglobe-atlasapi/terminologies/whs_sd_rat-terminology/3_0/terminology.csv"
)
WAXHOLM_FACTOR = 3  # 39 µm x 3 = 117 µm: Aday's choice in S3 (2026-11-11), no region lost
WAXHOLM_KEEP_SMALL = True

# The human grid: Julich-Brain MPM, BigBrain, CerebrA, CIT168 and ICBM 2009c share it
# (193 x 229 x 193 voxels of 1 mm, origin -96, -132, -78). Checked on every file.
MPM_SHAPE = (193, 229, 193)
MPM_ORIGIN = np.array([-96.0, -132.0, -78.0])

BIGBRAIN_URL = "https://osf.io/download/6qmhj/"  # BigBrain-to-ICBM2009asym-nonlin-1mm.nii
BIGBRAIN_FILE = "bigbrain/BigBrain-to-ICBM2009asym-nonlin-1mm.nii"
CEREBRA_URL = "https://gin.g-node.org/doi/CerebrA/raw/master/"
CEREBRA_FILES = ("CerebrA.nii", "CerebrA_LabelDetails.csv")
CIT168_URLS = {
    "CIT168toMNI152-2009c_det.nii.gz": "https://osf.io/download/vak6p/",
    "labels.txt": "https://osf.io/download/6qrcb/",
}
ICBM_URL = "https://www.bic.mni.mcgill.ca/~vfonov/icbm/2009/mni_icbm152_nlin_asym_09c_nifti.zip"
ICBM_ZIP = "icbm2009c/mni_icbm152_nlin_asym_09c_nifti.zip"
ICBM_WM_NAME = "Cerebral white matter (not divided into tracts)"
NISSL_BUCKET = (
    "https://data-proxy.ebrains.eu/api/v1/buckets/img-40ac3c53-c645-11ec-abfd-00090faa0001/"
)
NISSL_SERIES = "H108c_Nissl_coronal.json"
NISSL_PER_SECOND = 20  # the S3 pause of 0.05 s between requests to the EBRAINS data proxy


@dataclass
class Build:
    """Where to read the downloads from and where to write the files."""

    out: Path
    cache: Path
    fetch: Callable[[str, dict | None], bytes] | None = None  # url, params → body

    def get(self, rel: str, url: str, params: dict | None = None) -> Path:
        """The cached file ``rel``; downloaded from ``url`` once if it is not there."""
        path = self.cache / rel
        if not path.exists():
            if self.fetch is None:
                raise FileNotFoundError(f"{path} is not cached and no download is allowed")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(self.fetch(url, params))
        return path

    def folder(self, name: str) -> Path:
        d = self.out / name
        d.mkdir(parents=True, exist_ok=True)
        return d


def http_fetch() -> Callable[[str, dict | None], bytes]:
    """Downloads through the project's polite client (User-Agent with a contact, retries)."""
    from synaptica.http import Throttle, get_response, make_client

    client = make_client()
    client.timeout = 600.0  # whole atlases: tens of MB from OSF and McGill
    throttle = Throttle(NISSL_PER_SECOND)

    def fetch(url: str, params: dict | None = None) -> bytes:
        throttle.wait()
        return get_response(client, url, params=params).content

    return fetch


def _check_grid(img, what: str, *, eye: bool = False) -> None:
    ok = img.shape == MPM_SHAPE and np.allclose(img.affine[:3, 3], MPM_ORIGIN)
    if eye:
        ok = ok and np.allclose(img.affine[:3, :3], np.eye(3))
    if not ok:
        raise RuntimeError(f"unexpected {what} grid: {img.shape}\n{img.affine}")


def _labels(out: Path, atlas: str, value: str, rows: list[dict], **extra) -> None:
    write_json(out / "labels.json", {"atlas": atlas, "value": value, "rows": rows, **extra},
               indent=None)  # fmt: skip


# ---------------------------------------------------------------- rat: Waxholm


def waxholm(b: Build) -> dict:
    from brainglobe_atlasapi import BrainGlobeAtlas
    from scipy import ndimage

    atlas = BrainGlobeAtlas(BG_ATLAS, brainglobe_dir=b.cache / "brainglobe", check_latest=False)
    ann = np.asarray(atlas.annotation)  # (AP, SI, RL): a→p, s→i, r→l
    hem = np.asarray(atlas.hemispheres)  # 1 left, 2 right
    with (b.cache / BG_TERMINOLOGY).open() as f:
        terms = {int(r["identifier"]): r for r in csv.DictReader(f)}
    tree = {
        i: {
            "acronym": r["abbreviation"],
            "name": r["name"],
            "path": json.loads(r["root_identifier_path"]),
        }
        for i, r in terms.items()
    }

    # Compact index per (id, side), over the ids that are actually in the volume.
    rows = [{"index": 0, "id": None, "side": None, "acronym": None, "name": "background"}]
    lut = np.zeros((int(ann.max()) + 1, 3), dtype=np.uint16)
    for i, box in enumerate(ndimage.find_objects(ann), start=1):
        if box is None:
            continue
        sides = set(np.unique(hem[box][ann[box] == i]).tolist())
        for side, hv in (("L", 1), ("R", 2)):
            if hv not in sides:
                continue
            t = terms[i]
            rows.append(
                {
                    "index": len(rows),
                    "id": i,
                    "side": side,
                    "acronym": t["abbreviation"],
                    "name": t["name"],
                    "color": t["color_hex_triplet"],
                    "path": tree[i]["path"],
                }
            )
            lut[i, hv] = rows[-1]["index"]
    compact = lut[ann, hem]  # hem is 1 or 2 everywhere, also outside the brain (ann = 0 → 0)

    # Full resolution → RAS (x right, y anterior, z superior), axes flipped as needed; then
    # flat skull on a 39.0625 µm grid in mm from Bregma (S3 step 7.5, option A).
    ras = np.ascontiguousarray(np.flip(np.transpose(compact, (2, 0, 1)), axis=(0, 1, 2)))
    ras, grid_min = flat_skull(ras)
    full = np.bincount(ras.ravel(), minlength=len(rows))
    ds = majority_downsample(ras, WAXHOLM_FACTOR, keep_small=WAXHOLM_KEEP_SMALL)
    kept = np.bincount(ds.ravel(), minlength=len(rows))
    vmm = WHS_VOXEL_MM * WAXHOLM_FACTOR
    origin = -np.array(ds.shape) * vmm / 2
    out = b.folder("waxholm")
    size = save_nifti(out / "labels.nii.gz", ds, vmm, origin)
    add_centroids(rows, ds, vmm, origin)
    write_json(
        out / "coords.json",
        rat_flat_map(tuple(grid_min), WHS_VOXEL_MM, WAXHOLM_FACTOR, tuple(origin.tolist())),
    )

    names = {
        i: [tree[a]["name"] for a in tree[i]["path"] if a in tree and a != i] + [tree[i]["name"]]
        for i in tree
    }
    calm = palette.colours(
        [(palette.family(names[i]), names[i], i) for i in {r["id"] for r in rows[1:]}]
    )
    for r in rows[1:]:
        r["group"], r["color_calm"] = calm[r["id"]]
    _labels(out, "waxholm", "voxel value points to rows[index]; id is the Waxholm/BrainGlobe id",
            rows, tree={str(k): v for k, v in tree.items()})  # fmt: skip
    write_json(out / "licence.json", LICENCES["waxholm"])
    return {
        "regions_with_side": len(rows) - 1,
        "voxel_um": round(vmm * 1000, 4),
        "labels_lost": [
            f"{r['acronym']} {r['side']}"
            for r in rows[1:]
            if full[r["index"]] and not kept[r["index"]]
        ],
        "bytes_nifti_gz": size,
    }


# ---------------------------------------------------------------- human: Julich-Brain


def julich(b: Build) -> dict:
    os.environ.setdefault("SIIBRA_CACHEDIR", str(b.cache / "siibra"))
    import siibra

    p = siibra.parcellations["julich 3.1"]
    labelled = p.get_map(space=siibra.spaces["mni152"], maptype="labelled")
    vol = labelled.volumes[0]
    halves = {}
    for side, frag in (("L", "left hemisphere"), ("R", "right hemisphere")):
        img = vol.fetch(fragment=frag, format="nii")  # one file per hemisphere (lh, rh)
        halves[side] = np.asarray(img.dataobj)
        affine = img.affine
    if np.any((halves["L"] > 0) & (halves["R"] > 0)):
        raise RuntimeError("left and right MPM overlap: the side would be ambiguous")

    def ancestors(region) -> list[str]:
        names = []
        while region is not None:
            names.append(region.name)
            region = region.parent
        return names[::-1]

    rows = [{"index": 0, "id": None, "side": None, "label": None, "name": "background"}]
    for name in labelled.regions:
        idx = labelled.get_index(name)
        side = {"left hemisphere": "L", "right hemisphere": "R"}[idx.fragment]
        r = p.get_region(name)
        rows.append(
            {
                "index": None,
                "id": r.id,
                "side": side,
                "label": idx.label,
                "name": r.parent.name,
                "area_id": r.parent.id,
                "color": "#{:02X}{:02X}{:02X}".format(*r.rgb) if r.rgb else None,
                "_ancestors": ancestors(r),
            }
        )
    rows[1:] = sorted(rows[1:], key=lambda r: (r["label"], r["side"]))
    lut = {}
    for n, r in enumerate(rows):
        r["index"] = n
        if n:
            lut[(r["label"], r["side"])] = n
    compact = np.zeros(halves["L"].shape, dtype=np.uint16)
    for (label, side), n in lut.items():
        compact[halves[side] == label] = n

    # The MPM is already RAS with a diagonal 1 mm affine: keep its grid, centre it.
    if not np.allclose(affine[:3, :3], np.eye(3)) or not np.allclose(affine[:3, 3], MPM_ORIGIN):
        raise RuntimeError(f"unexpected MPM affine:\n{affine}")
    out = b.folder("julich")
    centre = affine[:3, 3] + (np.array(compact.shape) - 1) / 2
    size = save_nifti(out / "labels.nii.gz", compact, 1.0, affine[:3, 3] - centre)
    add_centroids(rows, compact, 1.0, affine[:3, 3] - centre)
    write_json(out / "coords.json", human_mni_map(tuple(centre.tolist())))

    lic = dict(LICENCES["julich"])
    lic["citation"] = (
        f"{', '.join(dict.fromkeys(p.authors))}. Julich-Brain Atlas, cytoarchitectonic maps "
        "(v3.1). EBRAINS. https://doi.org/10.25493/KNSN-XB4"
    )
    calm = palette.colours(
        list(
            {
                r["area_id"]: (palette.family(r["_ancestors"]), r["_ancestors"], r["area_id"])
                for r in rows[1:]
            }.values()
        )
    )
    for r in rows[1:]:
        del r["_ancestors"]
        r["group"], r["color_calm"] = calm[r["area_id"]]
    value = (
        "voxel value points to rows[index]; id is the siibra region id of the area on that "
        "side, label the MPM value (the same on both sides)"
    )
    _labels(out, "julich", value, rows)
    write_json(out / "licence.json", lic)
    return {"regions_with_side": len(rows) - 1, "bytes_nifti_gz": size}


def bigbrain(b: Build) -> dict:
    """BigBrain in ICBM152 2009 asymmetric, 1 mm, as an 8-bit volume (S3 step 7.8).

    Its own folder and licence (CC BY 4.0); nothing from Julich-Brain goes into it. It shares
    the MPM grid, so the viewer can show it under the human labels without resampling.
    """
    import nibabel as nib

    img = nib.load(b.get(BIGBRAIN_FILE, BIGBRAIN_URL))
    _check_grid(img, "BigBrain")
    d = np.rint(np.asarray(img.dataobj, dtype=np.float32) / 257)
    # 255 is the bare slide, 0 has no data: both transparent. Tissue goes to 1..254.
    u8 = np.where((d >= 255) | (d <= 0), 0, np.clip(d, 1, 254)).astype(np.uint8)
    centre = MPM_ORIGIN + (np.array(u8.shape) - 1) / 2
    out = b.folder("bigbrain")
    size = save_nifti(out / "stain.nii.gz", u8, 1.0, MPM_ORIGIN - centre, dtype=np.uint8)
    write_json(out / "licence.json", LICENCES["bigbrain"])
    return {"tissue_fraction": round(float((u8 > 0).mean()), 4), "bytes_nifti_gz": size}


def _layer(b: Build, name: str, compact: np.ndarray, rows: list[dict], origin: np.ndarray,
           report: dict) -> dict:  # fmt: skip
    """One human layer in its own folder: labels.nii.gz, labels.json and licence.json."""
    out = b.folder(name)
    size = save_nifti(out / "labels.nii.gz", compact, 1.0, origin)
    add_centroids(rows, compact, 1.0, origin)
    calm = palette.colours(list({r["area_id"]: (r["family"], [r["name"]], r["area_id"])
                                 for r in rows[1:]}.values()))  # fmt: skip
    for r in rows[1:]:
        r["color"] = None  # these layers ship no colours of their own
        r["group"], r["color_calm"] = calm[r["area_id"]]
        del r["family"]
    value = ("voxel value points to rows[index]; id and label are the CerebrA label value "
             "(one per side), area_id the structure on both sides") if name == "cerebra" else (
             "voxel value points to rows[index]; id and label are the source label value "
             "(one per side), area_id the structure on both sides")  # fmt: skip
    _labels(out, name, value, rows)
    write_json(out / "licence.json", LICENCES[name])
    return {"regions_with_side": len(rows) - 1, "bytes_nifti_gz": size, "selection": report}


def _taken_by(b: Build, *names: str) -> tuple[np.ndarray, np.ndarray]:
    """Voxels with a label in any of these human layers, and the centred origin of the grid."""
    import nibabel as nib

    imgs = [nib.load(b.out / n / "labels.nii.gz") for n in names]
    taken = np.zeros(imgs[0].shape, dtype=bool)
    for img in imgs:
        taken |= np.asarray(img.dataobj) > 0
    return taken, imgs[0].affine[:3, 3]


def _mni_x(shape: tuple[int, ...]) -> np.ndarray:
    """MNI x (mm) of every voxel of the MPM grid."""
    return MPM_ORIGIN[0] + np.indices(shape)[0]


def cerebra(b: Build) -> dict:
    """CerebrA where Julich-Brain has nothing (layers.py), in its own folder.

    Reads the Julich-Brain label volume written by julich() to know which voxels are free.
    """
    import nibabel as nib

    for name in CEREBRA_FILES:
        b.get(f"cerebra/{name}", CEREBRA_URL + name)
    img = nib.load(b.cache / "cerebra" / "CerebrA.nii")
    _check_grid(img, "CerebrA", eye=True)
    cv = np.rint(np.asarray(img.dataobj)).astype(np.int64)
    taken, origin = _taken_by(b, "julich")
    details = cb.read_details(b.cache / "cerebra" / "CerebrA_LabelDetails.csv")
    # select() takes the Julich-Brain volume itself; only "> 0" matters.
    compact, rows, report = cb.select(cv, taken.astype(np.uint16), details)
    return _layer(b, "cerebra", compact, rows, origin, report)


def cit168(b: Build) -> dict:
    """CIT168 where Julich-Brain and CerebrA leave nothing (hypothalamus and neighbours)."""
    import nibabel as nib

    for name, url in CIT168_URLS.items():
        b.get(f"cit168/{name}", url)
    img = nib.load(b.cache / "cit168" / "CIT168toMNI152-2009c_det.nii.gz")
    _check_grid(img, "CIT168")
    vol = cb.by_side(np.rint(np.asarray(img.dataobj)).astype(np.int64), _mni_x(img.shape))
    details = cb.cit168_details((b.cache / "cit168" / "labels.txt").read_text())
    taken, origin = _taken_by(b, "julich", "cerebra")
    compact, rows, report = cb.select(vol, taken, details, family=cb.CIT168_FAMILY,
                                      prefix="CIT168_")  # fmt: skip
    return _layer(b, "cit168", compact, rows, origin, report)


def icbm_wm(b: Build) -> dict:
    """White matter of the ICBM 2009c template where no other human layer has a label."""
    import nibabel as nib

    z = zipfile.ZipFile(b.get(ICBM_ZIP, ICBM_URL))

    def tissue(t: str):
        return nib.Nifti1Image.from_bytes(
            z.read(f"mni_icbm152_nlin_asym_09c/mni_icbm152_{t}_tal_nlin_asym_09c.nii")
        )

    wm_img = tissue("wm")
    _check_grid(wm_img, "ICBM")
    wm, gm, csf = (np.asarray(x.dataobj) for x in (wm_img, tissue("gm"), tissue("csf")))
    mask = (wm >= ICBM_WM_MIN) & (wm >= gm) & (wm >= csf)
    vol = cb.by_side(mask.astype(np.int64), _mni_x(wm.shape))
    details = [{"value": 2, "name": ICBM_WM_NAME, "side": "L", "abbr": "WM"},
               {"value": 3, "name": ICBM_WM_NAME, "side": "R", "abbr": "WM"}]  # fmt: skip
    taken, origin = _taken_by(b, "julich", "cerebra", "cit168")
    compact, rows, report = cb.select(vol, taken, details, family={"WM": "white_matter"},
                                      prefix="ICBM_")  # fmt: skip
    return _layer(b, "icbm_wm", compact, rows, origin, report)


# ---------------------------------------------------------------- rat: real Nissl, 2D only


def _nissl_file(b: Build, path: str) -> bytes:
    return b.get(f"nissl/{path}", NISSL_BUCKET + path, {"redirect": "true"}).read_bytes()


def _nissl_image(b: Build, name: str) -> np.ndarray:
    """A section at about 900 px from its Deep Zoom pyramid (tiles stitched), 8-bit RGB."""
    from PIL import Image

    stem = name.rsplit(".", 1)[0]
    dzi = _nissl_file(b, f"{stem}.tif/{stem}.dzi").decode()
    tile = int(re.search(r'TileSize="(\d+)"', dzi).group(1))
    lap = int(re.search(r'Overlap="(\d+)"', dzi).group(1))
    fmt = re.search(r'Format="(\w+)"', dzi).group(1)
    width = int(re.search(r'Width="(\d+)"', dzi).group(1))
    height = int(re.search(r'Height="(\d+)"', dzi).group(1))
    level, w, h = nissl.pyramid_level(width, height)
    out = np.full((h, w, 3), nissl.BACKGROUND, dtype=np.uint8)
    for col in range(-(-w // tile)):
        for row in range(-(-h // tile)):
            raw = _nissl_file(b, f"{stem}.tif/{stem}_files/{level}/{col}_{row}.{fmt}")
            t = np.asarray(Image.open(io.BytesIO(raw)).convert("RGB"))
            x, y = col * tile - (lap if col else 0), row * tile - (lap if row else 0)
            out[y : y + t.shape[0], x : x + t.shape[1]] = t[: h - y, : w - x]
    return out


def rat_nissl(b: Build) -> dict:
    """The rat's real stain for the 2D slice, one WebP per section (nissl.py)."""
    from PIL import Image

    series = json.loads(_nissl_file(b, NISSL_SERIES))
    out = b.folder("nissl")
    index = []
    for sl in series["slices"]:
        res = nissl.crop(nissl.resample(_nissl_image(b, sl["filename"]), sl))
        name = f"s{sl['nr']:03d}.webp"
        Image.fromarray(nissl.finish(res["image"]), "RGBA").save(out / name, "WEBP", quality=70,
                                                                  method=6)  # fmt: skip
        index.append({"nr": sl["nr"], "file": name, "ap_mm": res["ap_mm"],
                      "ap_range_mm": res["ap_range_mm"], "extent_mm": res["extent_mm"],
                      "px": [res["image"].shape[1], res["image"].shape[0]]})  # fmt: skip
    index.sort(key=lambda r: r["ap_mm"])
    write_json(out / "index.json", {
        "frame": "flat skull, mm from Bregma (the rat viewer's shown frame)",
        "pixel_mm": nissl.PIXEL_MM,
        "extent": "[x_left, x_right, z_bottom, z_top] of the image, mm",
        "sections": index,
    })  # fmt: skip
    write_json(out / "licence.json", LICENCES["nissl"])
    return {"sections": len(index)}


# ---------------------------------------------------------------- pairs and manifest


def load_pairs(path: Path = PAIRS_FILE) -> list[dict]:
    """The proposed pairs of pairs.toml, checked for shape."""
    pairs = tomllib.loads(path.read_text("utf-8"))["pair"]
    for p in pairs:
        if set(p) != {"kind", "waxholm", "atlas", "human"} or not p["human"]:
            raise ValueError(f"malformed pair in {path.name}: {p}")
    return pairs


def pairs(out: Path, terms: dict[int, dict], proposed: list[dict]) -> dict:
    """Rat ↔ human pairs with IDs and names only (no geometry); the grade is Sofía's.

    ``terms``: Waxholm id → {"abbreviation", "name"}. Reads the human ``labels.json`` already
    written in ``out``. A name missing from its layer is an error, not a silent drop: the seed
    must match the atlas data.
    """
    areas: dict[tuple[str, str], dict] = {}
    for layer in ("julich", "cerebra", "cit168", "icbm_wm"):
        rows = json.loads((out / layer / "labels.json").read_text("utf-8"))["rows"][1:]
        areas |= {(layer, r["name"]): r for r in rows}
    result = []
    for p in proposed:
        missing = [n for n in p["human"] if (p["atlas"], n) not in areas]
        if missing or p["waxholm"] not in terms:
            what = missing or p["waxholm"]
            raise ValueError(f"pair {p['kind']!r}: not in the atlas data: {what}")
        t = terms[p["waxholm"]]
        result.append(
            {
                "kind": p["kind"],
                "waxholm": {"id": p["waxholm"], "acronym": t["abbreviation"], "name": t["name"]},
                "human": [
                    {
                        "atlas": p["atlas"],
                        "area_id": areas[p["atlas"], n]["area_id"],
                        "label": areas[p["atlas"], n]["label"],
                        "name": n,
                    }
                    for n in p["human"]
                ],
                "same_side": True,
                "grade": None,
                "note": None,
            }
        )
    return {
        "note": "Rat ↔ human pairs of Neuro Atlas: IDs and names only, no geometry of either "
        "atlas. Proposals from spike S3; grade and note are Sofía's and still pending.",
        "grade_values": ["clear", "partial", "disputed"],
        "pairs": result,
    }


def manifest(out: Path, report: dict) -> dict:
    """Sizes per folder, and the initial load of each brain against the budget of D3.

    The budget (about 3 MB compressed per brain) is for what the viewer loads on entering:
    the rat's labels, and the human's four layers together. BigBrain and the Nissl sections
    are downloaded only when asked for (one section at a time), so they are reported apart.
    """
    files = {
        str(p.relative_to(out)): p.stat().st_size
        for p in sorted(out.rglob("*"))
        if p.is_file() and p.name != "manifest.json"
    }

    def size(*folders: str) -> int:
        return sum(v for k, v in files.items() if k.split("/", 1)[0] in folders)

    for atlas in ATLASES:
        if atlas in report:
            report[atlas]["bytes_total"] = size(atlas)
    report["initial_load"] = {
        brain: {"bytes": size(*folders), "within_budget": size(*folders) <= BUDGET_BYTES}
        for brain, folders in INITIAL_LOAD.items()
    }
    report["on_demand"] = {f: size(f) for f in ON_DEMAND if f in report}
    report["files_bytes"] = files
    return report


def build(out: Path, cache: Path, *, nissl_sections: bool = True,
          fetch: Callable[[str, dict | None], bytes] | None = None) -> dict:  # fmt: skip
    """Every atlas, in order (each human layer fills what the ones before leave)."""
    b = Build(out=out, cache=cache, fetch=fetch)
    out.mkdir(parents=True, exist_ok=True)
    report = {
        "waxholm": waxholm(b),
        "julich": julich(b),
        "bigbrain": bigbrain(b),
        "cerebra": cerebra(b),
        "cit168": cit168(b),
        "icbm_wm": icbm_wm(b),
    }
    if nissl_sections:
        report["nissl"] = rat_nissl(b)
    with (cache / BG_TERMINOLOGY).open() as f:
        terms = {int(r["identifier"]): r for r in csv.DictReader(f)}
    write_json(out / "pairs.json", pairs(out, terms, load_pairs()))
    report = manifest(out, report)
    write_json(out / "manifest.json", report)
    return report
