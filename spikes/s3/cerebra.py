"""Spike S3, Sofía's review of the viewer (2026-11-12): CerebrA fills what Julich-Brain lacks.

Julich-Brain v3.1 maps the cortex and some deep structures. It has no cerebellar cortex, no
pons or medulla, and barely any caudate, putamen or pallidum (results/cobertura.md). CerebrA
(Manera et al. 2020; Mindboggle-101 labels registered to MNI-ICBM2009c and corrected by hand)
has them, on the very same 1 mm grid as the Julich-Brain MPM and BigBrain (193 x 229 x 193,
origin -96, -132, -78; build_assets.py checks it).

Rule, measured and not chosen by hand: a CerebrA structure is kept when at least MIN_FREE of its
voxels have no Julich-Brain label; and only those voxels, so Julich-Brain wins wherever both
have something and a voxel never belongs to two regions. The result is its own file, with its
own licence; the viewer lays it under Julich-Brain's labels on screen, nothing joins the files.

Pure numpy, no I/O besides the label CSV, so the tests run without the atlases.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

import numpy as np

MIN_FREE = 0.5
# CerebrA structure -> calm family of build_assets.py (the same families as Waxholm and
# Julich-Brain, so the cerebellum of both brains reads alike: Waxholm puts it under the
# metencephalon, "hindbrain"). Structures not listed fall into "other".
FAMILY = {
    "Brainstem": "hindbrain",
    "Cerebellum Gray Matter": "hindbrain",
    "Vermal lobules I-V": "hindbrain",
    "Vermal lobules VI-VII": "hindbrain",
    "Vermal lobules VIII-X": "hindbrain",
    "Cerebellum White Matter": "white_matter",
    "Optic Chiasm": "white_matter",
    "Caudate": "basal_ganglia",
    "Putamen": "basal_ganglia",
    "Pallidum": "basal_ganglia",
    "Accumbens Area": "basal_ganglia",
    "Basal Forebrain": "basal_ganglia",
    "Lateral Ventricle": "ventricles",
    "Inferior Lateral Ventricle": "ventricles",
    "Third Ventricle": "ventricles",
    "Fourth Ventricle": "ventricles",
    "Thalamus": "thalamus",
    "Ventral Diencephalon": "thalamus",
    "Hippocampus": "hippocampus",
    "Amygdala": "amygdala",
}


def read_details(path: Path) -> list[dict]:
    """CerebrA_LabelDetails.csv: one row per structure, with its right and left label values."""
    with path.open(encoding="utf-8") as f:
        rows = list(csv.reader(f))[2:]  # two header lines
    out = []
    for r in rows:
        if not r or not r[1].strip():
            continue
        name = r[1].strip()
        for value, side in ((r[2], "R"), (r[3], "L")):
            out.append({"value": int(value), "name": name, "side": side, "mindboggle": int(r[0])})
    return out


def area_id(name: str) -> str:
    return "CEREBRA_" + re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_")


def free_fractions(cv: np.ndarray, jv: np.ndarray, details: list[dict]) -> dict[str, dict]:
    """Per structure (both sides): voxels in CerebrA and the share without a Julich-Brain label."""
    counts = np.bincount(cv.ravel(), minlength=max(d["value"] for d in details) + 1)
    free = np.bincount(cv[jv == 0].ravel(), minlength=len(counts))
    out: dict[str, dict] = {}
    for d in details:
        a = out.setdefault(d["name"], {"voxels": 0, "free": 0})
        a["voxels"] += int(counts[d["value"]])
        a["free"] += int(free[d["value"]])
    for a in out.values():
        a["free_fraction"] = round(a["free"] / a["voxels"], 3) if a["voxels"] else 0.0
    return out


def select(
    cv: np.ndarray, jv: np.ndarray, details: list[dict], min_free: float = MIN_FREE
) -> tuple[np.ndarray, list[dict], dict]:
    """Compact label volume (1..N, 0 = nothing) of the kept structures, where Julich has none.

    Rows follow build_assets.py's convention: index, id (CerebrA label value), side, name,
    area_id (both sides), label (the CerebrA value) and family.
    """
    if cv.shape != jv.shape:
        raise ValueError(f"grids differ: {cv.shape} vs {jv.shape}")
    fr = free_fractions(cv, jv, details)
    kept = {n for n, a in fr.items() if a["voxels"] and a["free_fraction"] >= min_free}
    rows = [{"index": 0, "id": None, "side": None, "label": None, "name": "background"}]
    # A side with no free voxel would be a row with nothing to show: left out.
    free_per_value = np.bincount(
        cv[jv == 0].ravel(), minlength=max(d["value"] for d in details) + 1
    )
    chosen = sorted(
        (d for d in details if d["name"] in kept and free_per_value[d["value"]]),
        key=lambda d: (d["name"], d["side"]),
    )
    lut = np.zeros(max(d["value"] for d in details) + 1, dtype=np.uint16)
    for n, d in enumerate(chosen, start=1):
        lut[d["value"]] = n
        rows.append(
            {
                "index": n,
                "id": d["value"],
                "side": d["side"],
                "label": d["value"],
                "name": d["name"],
                "area_id": area_id(d["name"]),
                "family": FAMILY.get(d["name"], "other"),
            }
        )
    compact = np.where(jv == 0, lut[cv], 0).astype(np.uint16)
    report = {
        "min_free": min_free,
        "kept": sorted(kept),
        "left_out": sorted(set(fr) - kept),
        "structures": dict(sorted(fr.items(), key=lambda kv: -kv[1]["free_fraction"])),
    }
    return compact, rows, report
