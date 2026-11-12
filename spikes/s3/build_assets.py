"""Spike S3, step 3: the data served by mock-up C (Niivue). Mock-up B (three.js meshes) was
removed on 2026-11-11 after Sofía chose C; its numbers stay in results/maqueta-b.md.

Throwaway code, not part of the package. Run from the repo root:

    SIIBRA_CACHEDIR=data/cache/s3/siibra uv run --group spike-s3 python spikes/s3/build_assets.py

Reads data/cache/s3/ (step 1) and downloads only what is missing there: the Waxholm annotation
and hemisphere volumes (BrainGlobe fetches them lazily, from its public S3 bucket).
Writes spikes/s3/site/data/:

    waxholm/  labels.nii.gz, labels.json, licence.json, coords.json
    julich/   labels.nii.gz, labels.json, licence.json, coords.json
    bigbrain/ stain.nii.gz, licence.json   (step 7.8: real stain for the human, BigBrain)
    cerebra/  labels.nii.gz, labels.json, licence.json   (Sofía's review: what Julich-Brain
              lacks, from CerebrA: cerebellum, brainstem, striatum, ventricles; cerebra.py)
    equivalencias.json  test pairs between the two atlases, grade "pendiente de Sofía"
    manifest.json       sizes and the Waxholm resolution measurements

Each atlas has its own folder and nothing derived combines the two (CC BY 4.0 and
CC BY-NC-SA 4.0). equivalencias.json holds only IDs and names, no geometry.

Conventions shared by both atlases, so the two viewers look at the brains the same way:
- Coordinates in millimetres, RAS (x to the right, y to the front, z up), centred on the brain.
- Every voxel value points to one row of labels.json: the atlas ID
  plus its side ("L" or "R"). Both atlases give the left and right area the same ID; the side
  comes from BrainGlobe's hemispheres volume (Waxholm, 1 = left, 2 = right) and from the
  fragment of siibra's map (Julich-Brain: one NIfTI per hemisphere, lh and rh).
- Labels are compact indices (1..N, 0 = background), not the atlas IDs, so the colour table
  of the viewer stays small and the side fits in the same value.

Idempotent: same cache in, same files out.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import cerebra as cb
import numpy as np
import requests
import requests.utils
from coords import (
    WHS_ORIGIN_VOXEL,
    WHS_VOXEL_MM,
    flat_skull_angle,
    flat_to_whs,
    human_mni_map,
    rat_flat_map,
    whs_to_flat,
)

USER_AGENT = "synaptica-spike/0.1"
requests.utils.default_user_agent = lambda *_: USER_AGENT

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "cache" / "s3"
OUT = ROOT / "spikes" / "s3" / "site" / "data"
BG_ATLAS = "whs_sd_rat_39um"
BG_TERMINOLOGY = (
    CACHE
    / "brainglobe/brainglobe-atlasapi/terminologies/whs_sd_rat-terminology/3_0/terminology.csv"
)
WAXHOLM_UM = 39.0
# Downsampling factors measured for C (39 µm x f). The chosen one is written to labels.nii.gz.
WAXHOLM_FACTORS = (2, 3, 4)
WAXHOLM_FACTOR = 3  # 117 µm: Aday's choice, 2026-11-11 (no region lost with keep_small)
WAXHOLM_KEEP_SMALL = True
BUDGET_BYTES = 3_000_000  # per atlas, compressed (PLAN.md, step 6)

# Test regions (PLAN.md). Waxholm: BrainGlobe ids; Julich-Brain: area names in siibra.
WAXHOLM_TEST = {"surface": [408], "internal": [1021], "third": [501]}  # M1, HF, Am-u
JULICH_TEST = {
    "surface": ["Area 4a (PreCG)", "Area 4p (PreCG)"],
    "internal": [
        "CA1 (Hippocampus)",
        "CA2 (Hippocampus)",
        "CA3 (Hippocampus)",
        "DG (Hippocampus)",
        "Subc (Hippocampus, Subicular complex)",
    ],
    "third": [
        "CM (Amygdala)",
        "LB (Amygdala)",
        "SF (Amygdala)",
        "Astr (Amygdala)",
        "VTM (Amygdala)",
        "IF (Amygdala)",
        "MF (Amygdala)",
    ],
}
# Test pairs for equivalencias.json: which regions are compared in the spike (PLAN.md). The
# grade is not ours to give: Sofía sets it.
PAIRS = [
    ("surface", 408, ["Area 4a (PreCG)", "Area 4p (PreCG)"]),
    ("internal", 1021, JULICH_TEST["internal"]),
    ("third", 501, JULICH_TEST["third"]),
]
PENDING = "pendiente de Sofía"

# Step 7.8: real stain for the human. BigBrain (Merker silver stain of cell bodies) registered to
# ICBM152 2009 nonlinear asymmetric by Xiao et al. 2019, 1 mm. Its grid is the one of the
# Julich-Brain MPM (193 x 229 x 193, origin -96, -132, -78). Downloaded once to the cache.
BIGBRAIN_URL = "https://osf.io/download/6qmhj/"  # BigBrain-to-ICBM2009asym-nonlin-1mm.nii
BIGBRAIN_FILE = CACHE / "bigbrain" / "BigBrain-to-ICBM2009asym-nonlin-1mm.nii"
MPM_ORIGIN = np.array([-96.0, -132.0, -78.0])  # checked against the MPM in julich()

# Sofía's review (2026-11-12): CerebrA for the parts Julich-Brain lacks (cerebra.py). G-Node GIN,
# DOI 10.12751/g-node.be5e62; same grid as the MPM. Downloaded once to the cache.
CEREBRA_URL = "https://gin.g-node.org/doi/CerebrA/raw/master/"
CEREBRA_DIR = CACHE / "cerebra"
CEREBRA_FILES = ("CerebrA.nii", "CerebrA_LabelDetails.csv")
# Proposed pairs for what CerebrA adds: Waxholm id <-> CerebrA structures. Proposals only; the
# grade (and whether they are pairs at all) is Sofía's.
CEREBRA_PAIRS = [
    ("cerebellum", 1047, ["Cerebellum Gray Matter", "Cerebellum White Matter",
                          "Vermal lobules I-V", "Vermal lobules VI-VII", "Vermal lobules VIII-X"]),
    ("brainstem", 47, ["Brainstem"]),
    ("striatum", 197, ["Caudate", "Putamen"]),
    ("pallidum", 1028, ["Pallidum"]),
    ("ventricles", 1048, ["Lateral Ventricle", "Third Ventricle", "Fourth Ventricle"]),
    ("optic chiasm", 42, ["Optic Chiasm"]),
]  # fmt: skip

LICENCES = {
    "bigbrain": {
        "atlas": "BigBrain, Merker-stained histology, in ICBM152 2009 nonlinear asymmetric space",
        "short": "BigBrain (1 mm, ICBM152 2009)",
        "version": "BigBrain 2015 release, registration by Xiao et al. 2019",
        "licence": "CC BY 4.0",
        "licence_url": "https://creativecommons.org/licenses/by/4.0/",
        "licence_note": (
            "The down-sampled BigBrain volumes of this OSF dataset are CC BY 4.0 with the consent "
            "of the MNI and Forschungszentrum Jülich; BigBrain itself remains CC BY-NC-SA 4.0 "
            "(README of the dataset)."
        ),
        "source": "OSF project xkqb3, file BigBrain-to-ICBM2009asym-nonlin-1mm.nii",
        "source_url": "https://osf.io/xkqb3/",
        "citation": (
            "Amunts K. et al. 2013, BigBrain: an ultrahigh-resolution 3D human brain model, "
            "Science 340:1472-1475, https://doi.org/10.1126/science.1235381; Xiao Y. et al. 2019, "
            "An accurate registration of the BigBrain dataset with the MNI PD25 and ICBM152 "
            "atlases, Scientific Data 6:210, https://doi.org/10.1038/s41597-019-0217-0"
        ),
        "derived": (
            "Converted to 8 bits; slide (white) and voxels without data set to 0 so that they "
            "are transparent; centred like the Julich-Brain label volume (same grid). Changes "
            "made by SYNAPTICA. Not combined with any atlas file."
        ),
    },
    "cerebra": {
        "atlas": "CerebrA, Mindboggle-101 labels registered to MNI-ICBM2009c and corrected by hand",
        "short": "CerebrA",
        "version": "G-Node GIN release, DOI 10.12751/g-node.be5e62",
        "licence": "CC0 1.0 (labels from Mindboggle-101, CC BY-NC-SA 3.0)",
        "licence_url": "https://creativecommons.org/publicdomain/zero/1.0/",
        "licence_note": (
            "The CerebrA repository is CC0 1.0 (datacite.yml and LICENSE). Its labels derive from "
            "Mindboggle-101, which NITRC lists as CC BY-NC-SA 3.0; SYNAPTICA follows the stricter "
            "of the two, which it allows (NC licences are accepted)."
        ),
        "source": "G-Node GIN, CerebrA.nii and CerebrA_LabelDetails.csv",
        "source_url": "https://doi.org/10.12751/g-node.be5e62",
        "citation": (
            "Manera A. L., Dadar M., Fonov V., Collins D. L. 2020, CerebrA, registration and "
            "manual label correction of Mindboggle-101 atlas for MNI-ICBM152 template, "
            "Scientific Data 7:237, https://doi.org/10.1038/s41597-020-0557-9; Klein A., "
            "Tourville J. 2012, 101 labeled brain images and a consistent human cortical "
            "labeling protocol, Frontiers in Neuroscience 6:171, "
            "https://doi.org/10.3389/fnins.2012.00171"
        ),
        "derived": (
            "Only the structures with at least half of their voxels outside Julich-Brain, and only "
            "those voxels (cerebra.py); compact indices per structure and side; centred like the "
            "Julich-Brain label volume (same grid). Changes made by SYNAPTICA. Not combined with "
            "any Julich-Brain file: the viewer only shows one under the other."
        ),
    },
    "waxholm": {
        "atlas": "Waxholm Space atlas of the Sprague Dawley rat brain",
        "short": "Waxholm v4.01",
        "version": "v4.01",
        "licence": "CC BY 4.0",
        "licence_url": "https://creativecommons.org/licenses/by/4.0/",
        "source": "EBRAINS Knowledge Graph, dataset version 2cf40e61-fae1-4ab3-b7de-cb8fdfa19b70",
        "source_url": "https://search.kg.ebrains.eu/instances/2cf40e61-fae1-4ab3-b7de-cb8fdfa19b70",
        "via": "BrainGlobe atlas whs_sd_rat_39um (packaging 3.0)",
        "citation": "Kleven et al. 2023, Nature Methods, https://doi.org/10.1038/s41592-023-02034-3",
        "citation_source": "BrainGlobe metadata of whs_sd_rat_39um",
        "derived": (
            "Meshes simplified and Draco-compressed; label volume downsampled by majority vote "
            "and relabelled with compact indices per region and side. Changes made by SYNAPTICA."
        ),
    },
    "julich": {
        "atlas": "Julich-Brain Cytoarchitectonic Atlas",
        "short": "Julich-Brain v3.1",
        "version": "v3.1",
        "licence": "CC BY-NC-SA 4.0",
        "licence_url": "https://creativecommons.org/licenses/by-nc-sa/4.0/",
        "source": "Julich-Brain Atlas, cytoarchitectonic maps (v3.1), maximum probability map "
        "in MNI152 2009c nonlinear asymmetric",
        "source_url": "https://doi.org/10.25493/KNSN-XB4",
        "via": "siibra-python",
        "citation": None,  # filled from siibra: authors of the dataset + DOI
        "citation_source": "siibra (EBRAINS KG record of the dataset)",
        "derived": (
            "Left and right maximum probability maps joined into one label volume with compact "
            "indices per area and side; meshes by marching cubes, smoothed, simplified and "
            "Draco-compressed. Changes made by SYNAPTICA. Shared under the same licence."
        ),
    },
}


# ---------------------------------------------------------------- calm palette (step 7.2)
#
# Sofía asked for a palette that is not visually noisy (results/peticiones-sofia.md, P5). The
# official colours give hundreds of unrelated hues side by side. Here every region takes the
# soft hue of its family (cortex, hippocampus, thalamus...), with a small change of lightness
# between neighbours so that borders still show. Same family, same hue in both atlases, so the
# rat and the human read alike; each atlas is coloured from its own hierarchy only. The
# official colour stays in "color"; this one goes in "color_calm". Both sides share a colour.

# Family: (hue in degrees, saturation, lightness), all low-saturation pastels.
CALM_FAMILIES = {
    "cortex": (15, 0.45, 0.80),
    "cortex_gap": (15, 0.12, 0.86),  # Julich-Brain GapMaps: cortex not mapped yet
    "hippocampus": (265, 0.30, 0.77),
    "olfactory": (40, 0.45, 0.78),
    "amygdala": (340, 0.33, 0.76),
    "basal_ganglia": (200, 0.35, 0.77),
    "thalamus": (50, 0.55, 0.77),
    "hypothalamus": (90, 0.30, 0.75),
    "midbrain": (170, 0.28, 0.73),
    "hindbrain": (125, 0.20, 0.72),
    "white_matter": (35, 0.12, 0.90),
    "ventricles": (205, 0.50, 0.85),
    "other": (0, 0.0, 0.80),
}
# First match wins, over the ancestor names (lower case) from the root down to the region.
CALM_RULES = [
    ("cortex_gap", ("gapmap",)),
    ("hippocampus", ("hippocampal formation",)),
    ("olfactory", ("olfactory bulb",)),
    ("amygdala", ("amygdala", "non-laminated pallium")),
    ("basal_ganglia", ("basal ganglia", "basal forebrain", "subpallium")),
    ("hypothalamus", ("hypothalamus",)),
    ("thalamus", ("thalamus", "subthalamus", "diencephalon")),
    ("midbrain", ("mesencephalon",)),
    ("hindbrain", ("rhombencephalon", "metencephalon")),
    ("white_matter", ("white matter",)),
    ("ventricles", ("ventricular system",)),
    ("cortex", ("cerebral cortex",)),
]
# Human cortex: a slight hue shift per lobe, inside the cortex family.
CALM_LOBE_SHIFT = {
    "frontal lobe": -6,
    "parietal lobe": 8,
    "temporal lobe": -12,
    "occipital lobe": 16,
    "insula": 2,
    "limbic lobe": -18,
}
CALM_STEPS = (0.0, 0.05, -0.05, 0.025, -0.025)  # lightness steps between neighbours


def calm_family(ancestors: list[str]) -> str:
    names = [a.strip().lower() for a in ancestors]
    for family, keys in CALM_RULES:
        if any(k in n for n in names for k in keys):
            return family
    return "other"


def calm_colours(members: list[tuple[str, list[str], object]]) -> dict[object, tuple[str, str]]:
    """members: (family, ancestors, key) per region. Returns key → (family, "#RRGGBB").

    Within a family, regions are taken in key order and step through CALM_STEPS, so the
    result depends only on the atlas data (idempotent).
    """
    import colorsys

    out = {}
    seen: dict[str, int] = {}
    for family, ancestors, key in sorted(members, key=lambda m: (m[0], str(m[2]))):
        h, s, li = CALM_FAMILIES[family]
        if family == "cortex":
            lower = [a.strip().lower() for a in ancestors]
            h += next((v for k, v in CALM_LOBE_SHIFT.items() if k in lower), 0)
        n = seen.get(family, 0)
        seen[family] = n + 1
        li = min(0.95, max(0.5, li + CALM_STEPS[n % len(CALM_STEPS)]))
        r, g, b = colorsys.hls_to_rgb((h % 360) / 360, li, s)
        out[key] = (family, "#{:02X}{:02X}{:02X}".format(*(round(c * 255) for c in (r, g, b))))
    return out


def flat_skull(ras: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Turn the 39 µm Waxholm labels to flat skull (step 7.5, option A), nearest neighbour.

    Input: RAS labels on the WHS v1.01 grid (voxel v is at 0.0390625 * (v - origin voxel) WHS mm).
    Output: labels on a grid of the same voxel size in mm from Bregma, flat skull (coords.py):
    voxel u is at grid_min + u * 0.0390625. Only the box around the brain is resampled.
    """
    import itertools

    from scipy import ndimage

    (box,) = ndimage.find_objects((ras > 0).astype(np.uint8))
    lo = np.array([b.start for b in box])
    hi = np.array([b.stop - 1 for b in box])
    o = np.array(WHS_ORIGIN_VOXEL)
    corners = np.array(
        [
            whs_to_flat(tuple(WHS_VOXEL_MM * (np.array(c) - o)))
            for c in itertools.product(*zip(lo, hi, strict=True))
        ]
    )
    v = WHS_VOXEL_MM
    grid_min = np.floor(corners.min(axis=0) / v) * v - v
    grid_max = np.ceil(corners.max(axis=0) / v) * v + v
    shape = tuple(int(n) for n in np.rint((grid_max - grid_min) / v) + 1)
    a = flat_skull_angle()
    # Output index u → input index: flat_to_whs(grid_min + u * v) / v + o - lo. Same voxel size,
    # so the linear part is the inverse turn.
    turn = np.array([[1, 0, 0], [0, np.cos(a), np.sin(a)], [0, -np.sin(a), np.cos(a)]])
    offset = np.array(flat_to_whs(tuple(grid_min))) / v + o - lo
    flat = ndimage.affine_transform(
        ras[box], turn, offset=offset, output_shape=shape, order=0, mode="constant", cval=0
    )
    return flat, grid_min


def majority_downsample(vol: np.ndarray, f: int, keep_small: bool = False) -> np.ndarray:
    """Each block of fxfxf voxels takes the value most voxels in it have (ties: lowest).

    Label by label within its bounding box, so it never builds an f³ copy of the whole volume.
    keep_small: a label that wins no block still gets the block where it has most voxels, as
    long as that does not make the label that held it disappear.
    """
    from scipy import ndimage

    shape = tuple(-(-s // f) for s in vol.shape)
    best = np.zeros(shape, dtype=vol.dtype)
    best_n = np.zeros(shape, dtype=np.int32)
    boxes = [tuple(slice(0, s) for s in vol.shape), *ndimage.find_objects(vol)]
    peak = {}  # label → (block index in best, voxels of the label there)
    for lab, box in enumerate(boxes):
        if box is None:
            continue
        lo = [b.start // f * f for b in box]
        hi = [b.stop for b in box]
        sub = vol[lo[0] : hi[0], lo[1] : hi[1], lo[2] : hi[2]] == lab
        sub = np.pad(sub, [(0, -s % f) for s in sub.shape])
        a, b, c = (s // f for s in sub.shape)
        cnt = sub.reshape(a, f, b, f, c, f).sum(axis=(1, 3, 5), dtype=np.int32)
        sl = tuple(slice(x // f, x // f + n) for x, n in zip(lo, (a, b, c), strict=True))
        win = cnt > best_n[sl]
        best[sl][win] = lab
        best_n[sl][win] = cnt[win]
        k = np.unravel_index(int(np.argmax(cnt)), cnt.shape)
        peak[lab] = (tuple(int(o.start) + int(x) for o, x in zip(sl, k, strict=True)), cnt[k])
    if keep_small:
        present = np.bincount(best.ravel(), minlength=len(boxes))
        for lab, (at, _) in sorted(peak.items(), key=lambda kv: -kv[1][1]):
            if lab and present[lab] == 0 and present[best[at]] > 1:
                present[best[at]] -= 1
                best[at] = lab
                present[lab] = 1
    return best


def save_nifti(path: Path, data: np.ndarray, voxel_mm: float, origin: np.ndarray) -> int:
    import nibabel as nib

    aff = np.diag([voxel_mm, voxel_mm, voxel_mm, 1.0])
    aff[:3, 3] = origin
    img = nib.Nifti1Image(data.astype(np.uint16), aff)
    img.header.set_xyzt_units("mm")
    img.header.set_qform(aff, code=1)
    img.header.set_sform(aff, code=1)
    nib.save(img, path)
    return path.stat().st_size


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def add_centroids(rows: list[dict], vol: np.ndarray, voxel_mm: float, origin: np.ndarray) -> None:
    """Voxel count and centroid (mm, the NIfTI's own RAS grid) of every row, in place.

    Step 7.4: the viewer moves its slices and cut to the region picked in the other atlas. The
    centroid is computed on the same volume and affine that C loads, so it lands where Niivue
    draws the region. Rows of one atlas only; nothing crosses between atlases.
    """
    n = len(rows)
    flat = vol.ravel()
    counts = np.bincount(flat, minlength=n)
    idx = np.indices(vol.shape).reshape(3, -1)
    sums = [np.bincount(flat, weights=idx[a], minlength=n) for a in range(3)]
    for r in rows[1:]:
        c = int(counts[r["index"]])
        r["voxels"] = c
        r["centroid_mm"] = (
            [round(float(origin[a] + sums[a][r["index"]] / c * voxel_mm), 2) for a in range(3)]
            if c
            else None
        )


# ---------------------------------------------------------------- Waxholm


def waxholm() -> dict:
    from brainglobe_atlasapi import BrainGlobeAtlas

    atlas = BrainGlobeAtlas(BG_ATLAS, brainglobe_dir=CACHE / "brainglobe", check_latest=False)
    ann = np.asarray(atlas.annotation)  # (AP, SI, RL): a→p, s→i, r→l
    hem = np.asarray(atlas.hemispheres)  # 1 left, 2 right
    with BG_TERMINOLOGY.open() as f:
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
    from scipy import ndimage

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

    # Full resolution → RAS (x right, y anterior, z superior), axes flipped as needed.
    ras = np.ascontiguousarray(np.flip(np.transpose(compact, (2, 0, 1)), axis=(0, 1, 2)))
    before = np.bincount(ras.ravel(), minlength=len(rows))
    # Step 7.5, option A (Aday): flat skull, on a 39.0625 µm grid in mm from Bregma.
    ras, grid_min = flat_skull(ras)
    full = np.bincount(ras.ravel(), minlength=len(rows))
    flat_report = {
        "angle_deg": round(float(np.degrees(flat_skull_angle())), 3),
        "shape": list(ras.shape),
        "grid_min_mm": [round(float(x), 6) for x in grid_min],
        "labels_lost": [f"{r['acronym']} {r['side']}" for r in rows[1:] if not full[r["index"]]],
        "voxels_ratio_min": round(float(np.min(full[1:] / np.maximum(before[1:], 1))), 3),
        "voxels_ratio_max": round(float(np.max(full[1:] / np.maximum(before[1:], 1))), 3),
    }
    measured = {}
    out = OUT / "waxholm"
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / "_measure.nii.gz"
    for f in WAXHOLM_FACTORS:
        for keep in (False, True):
            ds = majority_downsample(ras, f, keep_small=keep)
            cnt = np.bincount(ds.ravel(), minlength=len(rows))
            lost = [r for r in rows[1:] if cnt[r["index"]] == 0]
            vmm = WHS_VOXEL_MM * f
            origin = -np.array(ds.shape) * vmm / 2
            chosen = f == WAXHOLM_FACTOR and keep == WAXHOLM_KEEP_SMALL
            size = save_nifti(out / "labels.nii.gz" if chosen else tmp, ds, vmm, origin)
            if chosen:
                add_centroids(rows, ds, vmm, origin)
                # Step 7.5 (P7): mm from Bregma, flat skull, from the published WHS table.
                write_json(
                    out / "coords.json",
                    rat_flat_map(tuple(grid_min), WHS_VOXEL_MM, f, tuple(origin.tolist())),
                )
            smallest = sorted(rows[1:], key=lambda r: full[r["index"]])[:5]
            measured[f"{round(WAXHOLM_UM * f)}um" + ("_keep_small" if keep else "")] = {
                "factor": f,
                "keep_small": keep,
                "shape": list(ds.shape),
                "bytes_nifti_gz": size,
                "labels_lost": [f"{r['acronym']} {r['side']}" for r in lost],
                "smallest_full_vs_down": {
                    f"{r['acronym']} {r['side']}": [int(full[r["index"]]), int(cnt[r["index"]])]
                    for r in smallest
                },
                "test_regions_voxels": {
                    f"{tree[t]['acronym']} {s}": int(
                        sum(cnt[r["index"]] for r in rows[1:] if t in r["path"] and r["side"] == s)
                    )
                    for k in WAXHOLM_TEST.values()
                    for t in k
                    for s in ("L", "R")
                },
            }
    tmp.unlink(missing_ok=True)

    names = {
        i: [tree[a]["name"] for a in tree[i]["path"] if a in tree and a != i] + [tree[i]["name"]]
        for i in tree
    }
    calm = calm_colours([(calm_family(names[i]), names[i], i) for i in {r["id"] for r in rows[1:]}])
    for r in rows[1:]:
        r["group"], r["color_calm"] = calm[r["id"]]

    labels = {
        "atlas": "waxholm",
        "value": "voxel value points to rows[index]; id is the Waxholm/BrainGlobe id",
        "rows": rows,
        "tree": {str(k): v for k, v in tree.items()},
    }
    (out / "labels.json").write_text(json.dumps(labels, ensure_ascii=False) + "\n")
    (out / "licence.json").write_text(
        json.dumps(LICENCES["waxholm"], indent=2, ensure_ascii=False) + "\n"
    )
    return {
        "regions_with_side": len(rows) - 1,
        "flat_skull": flat_report,
        "resolutions": measured,
        "chosen": f"{round(WAXHOLM_UM * WAXHOLM_FACTOR)}um"
        + ("_keep_small" if WAXHOLM_KEEP_SMALL else ""),
    }


# ---------------------------------------------------------------- Julich-Brain


def julich() -> dict:
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
        raise SystemExit("left and right MPM overlap: the side would be ambiguous")

    def ancestors(region) -> list[str]:
        names = []
        while region is not None:
            names.append(region.name)
            region = region.parent
        return names[::-1]

    rows = [{"index": 0, "id": None, "side": None, "label": None, "name": "background"}]
    lut = {}
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
    for n, r in enumerate(rows):
        r["index"] = n
        if n:
            lut[(r["label"], r["side"])] = n
    compact = np.zeros(halves["L"].shape, dtype=np.uint16)
    for (label, side), n in lut.items():
        compact[halves[side] == label] = n

    out = OUT / "julich"
    out.mkdir(parents=True, exist_ok=True)
    # The MPM is already RAS with a diagonal 1 mm affine: keep its grid, centre it.
    if not np.allclose(affine[:3, :3], np.eye(3)):
        raise SystemExit(f"unexpected MPM affine:\n{affine}")
    if not np.allclose(affine[:3, 3], MPM_ORIGIN):  # BigBrain (step 7.8) relies on this grid
        raise SystemExit(f"unexpected MPM origin: {affine[:3, 3]}")
    centre = affine[:3, 3] + (np.array(compact.shape) - 1) / 2
    size = save_nifti(out / "labels.nii.gz", compact, 1.0, affine[:3, 3] - centre)
    add_centroids(rows, compact, 1.0, affine[:3, 3] - centre)
    write_json(out / "coords.json", human_mni_map(tuple(centre.tolist())))  # step 7.5: MNI mm

    authors = list(dict.fromkeys(p.authors))
    lic = dict(LICENCES["julich"])
    lic["citation"] = (
        f"{', '.join(authors)}. Julich-Brain Atlas, cytoarchitectonic maps (v3.1). "
        "EBRAINS. https://doi.org/10.25493/KNSN-XB4"
    )
    calm = calm_colours(
        list(
            {
                r["area_id"]: (calm_family(r["_ancestors"]), r["_ancestors"], r["area_id"])
                for r in rows[1:]
            }.values()
        )
    )
    for r in rows[1:]:
        del r["_ancestors"]
        r["group"], r["color_calm"] = calm[r["area_id"]]

    labels = {
        "atlas": "julich",
        "value": "voxel value points to rows[index]; id is the siibra region id of "
        "the area on that side, label the MPM value (the same on both sides)",
        "rows": rows,
    }
    (out / "labels.json").write_text(json.dumps(labels, ensure_ascii=False) + "\n")
    (out / "licence.json").write_text(json.dumps(lic, indent=2, ensure_ascii=False) + "\n")
    return {
        "regions_with_side": len(rows) - 1,
        "bytes_nifti_gz": size,
    }


def bigbrain() -> dict:
    """Step 7.8: BigBrain in ICBM152 2009 asymmetric, 1 mm, as an 8-bit volume for the viewer.

    Its own folder and licence (CC BY 4.0); nothing from Julich-Brain goes into it. It shares the
    MPM grid, so the viewer can show it under the human labels without resampling.
    """
    import nibabel as nib

    if not BIGBRAIN_FILE.exists():
        BIGBRAIN_FILE.parent.mkdir(parents=True, exist_ok=True)
        r = requests.get(BIGBRAIN_URL, timeout=300)
        r.raise_for_status()
        BIGBRAIN_FILE.write_bytes(r.content)
    img = nib.load(BIGBRAIN_FILE)
    if img.shape != (193, 229, 193) or not np.allclose(img.affine[:3, 3], MPM_ORIGIN):
        raise SystemExit(f"unexpected BigBrain grid: {img.shape}\n{img.affine}")
    d = np.rint(np.asarray(img.dataobj, dtype=np.float32) / 257)
    # 255 is the bare slide, 0 has no data: both transparent. Tissue goes to 1..254.
    u8 = np.where((d >= 255) | (d <= 0), 0, np.clip(d, 1, 254)).astype(np.uint8)
    centre = MPM_ORIGIN + (np.array(u8.shape) - 1) / 2
    out = OUT / "bigbrain"
    out.mkdir(parents=True, exist_ok=True)
    origin = MPM_ORIGIN - centre
    aff = np.diag([1.0, 1.0, 1.0, 1.0])
    aff[:3, 3] = origin
    nimg = nib.Nifti1Image(u8, aff)
    nimg.header.set_xyzt_units("mm")
    nimg.header.set_qform(aff, code=1)
    nimg.header.set_sform(aff, code=1)
    nib.save(nimg, out / "stain.nii.gz")
    write_json(out / "licence.json", LICENCES["bigbrain"])
    return {
        "shape": list(u8.shape),
        "tissue_fraction": round(float((u8 > 0).mean()), 4),
        "bytes_nifti_gz": (out / "stain.nii.gz").stat().st_size,
    }


def cerebra() -> dict:
    """Sofía's review: CerebrA where Julich-Brain has nothing (cerebra.py), in its own folder.

    Reads the Julich-Brain label volume written by julich() (same grid, centred) to know which
    voxels are free. The CerebrA symmetric template and the asymmetric one of Julich-Brain are
    the same space but not the same average brain: along the seam they can disagree by a voxel
    or two.
    """
    import nibabel as nib

    for name in CEREBRA_FILES:
        path = CEREBRA_DIR / name
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            r = requests.get(CEREBRA_URL + name, timeout=300, headers={"User-Agent": USER_AGENT})
            r.raise_for_status()
            path.write_bytes(r.content)
    img = nib.load(CEREBRA_DIR / "CerebrA.nii")
    if img.shape != (193, 229, 193) or not np.allclose(img.affine[:3, :3], np.eye(3)) \
            or not np.allclose(img.affine[:3, 3], MPM_ORIGIN):  # fmt: skip
        raise SystemExit(f"unexpected CerebrA grid: {img.shape}\n{img.affine}")
    cv = np.rint(np.asarray(img.dataobj)).astype(np.int64)
    jimg = nib.load(OUT / "julich" / "labels.nii.gz")
    jv = np.asarray(jimg.dataobj)
    details = cb.read_details(CEREBRA_DIR / "CerebrA_LabelDetails.csv")
    compact, rows, report = cb.select(cv, jv, details)

    out = OUT / "cerebra"
    out.mkdir(parents=True, exist_ok=True)
    origin = jimg.affine[:3, 3]  # the centred origin of the Julich-Brain volume
    size = save_nifti(out / "labels.nii.gz", compact, 1.0, origin)
    add_centroids(rows, compact, 1.0, origin)
    calm = calm_colours(list({r["area_id"]: (r["family"], [r["name"]], r["area_id"])
                              for r in rows[1:]}.values()))  # fmt: skip
    for r in rows[1:]:
        r["color"] = None  # CerebrA ships no colours of its own
        r["group"], r["color_calm"] = calm[r["area_id"]]
        del r["family"]
    labels = {
        "atlas": "cerebra",
        "value": "voxel value points to rows[index]; id and label are the CerebrA label value "
        "(one per side), area_id the structure on both sides",
        "rows": rows,
    }
    (out / "labels.json").write_text(json.dumps(labels, ensure_ascii=False) + "\n")
    write_json(out / "licence.json", LICENCES["cerebra"])
    return {"regions_with_side": len(rows) - 1, "bytes_nifti_gz": size, "selection": report}


def equivalences() -> dict:
    """Test pairs between the atlases: IDs and names only. The grade is Sofía's to give.

    The human side of a pair ("human") lists Julich-Brain areas or CerebrA structures, each with
    its atlas; CerebrA's are proposals for what it adds (CEREBRA_PAIRS)."""
    with BG_TERMINOLOGY.open() as f:
        terms = {int(r["identifier"]): r for r in csv.DictReader(f)}
    jl = json.loads((OUT / "julich" / "labels.json").read_text())["rows"][1:]
    cl = json.loads((OUT / "cerebra" / "labels.json").read_text())["rows"][1:]
    areas = {("julich", r["name"]): r for r in jl} | {("cerebra", r["name"]): r for r in cl}
    pairs = []
    todo = [(k, w, "julich", n) for k, w, n in PAIRS] + [
        (k, w, "cerebra", n) for k, w, n in CEREBRA_PAIRS
    ]
    for kind, wid, atlas, names in todo:
        human = [
            {"atlas": atlas, "area_id": areas[atlas, n]["area_id"],
             "label": areas[atlas, n]["label"], "name": n}
            for n in names
            if (atlas, n) in areas  # a CerebrA structure left out by the rule has no pair
        ]  # fmt: skip
        if not human:
            continue
        pairs.append(
            {
                "kind": kind,
                "waxholm": {
                    "id": wid,
                    "acronym": terms[wid]["abbreviation"],
                    "name": terms[wid]["name"],
                },
                "human": human,
                "same_side": True,
                "grade": PENDING,
            }
        )
    return {
        "note": "Test data for spike S3 (PLAN.md): which regions the mock-ups pair. Only IDs and "
        "names, no geometry. The grade of equivalence is pending Sofía's review; the pairs "
        "with CerebrA structures are proposals too.",
        "grade_values": None,
        "pairs": pairs,
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    report = {
        "waxholm": waxholm(),
        "julich": julich(),
        "bigbrain": bigbrain(),
        "cerebra": cerebra(),  # after julich(): it reads the Julich-Brain labels
    }
    eq = equivalences()
    (OUT / "equivalencias.json").write_text(json.dumps(eq, indent=2, ensure_ascii=False) + "\n")
    files = {
        str(p.relative_to(OUT)): p.stat().st_size
        for p in sorted(OUT.rglob("*"))
        if p.is_file() and p.name != "manifest.json"
    }
    report["files_bytes"] = files
    for atlas in ("waxholm", "julich", "bigbrain", "cerebra"):
        total = sum(v for k, v in files.items() if k.startswith(atlas + "/"))
        report[atlas]["bytes_total"] = total
        report[atlas]["within_budget"] = total <= BUDGET_BYTES
    (OUT / "manifest.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
