"""Spike S3, Sofía's review of the viewer (2026-11-12): the human brain in layers.

Julich-Brain first; then each further atlas fills only what the ones before it leave empty:
CerebrA, then CIT168 (hypothalamus, mammillary nuclei, habenula) and last the white matter of
the ICBM 2009c template. All four share one grid. The CerebrA notes below were the first layer;
the rule is the same for every layer.

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


def area_id(name: str, prefix: str = "CEREBRA_") -> str:
    return prefix + re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_")


# CIT168 (Pauli, Nili and Tyszka 2018, Scientific Data 5:180063): its labels.txt gives the
# abbreviations; the full names are the ones of that paper. Value in the deterministic map =
# position in labels.txt + 1. The atlas has no sides: they are split at the midline (x = 0).
CIT168_NAMES = {
    "Pu": "Putamen", "Ca": "Caudate nucleus", "NAC": "Nucleus accumbens",
    "EXA": "Extended amygdala", "GPe": "Globus pallidus, external segment",
    "GPi": "Globus pallidus, internal segment", "SNc": "Substantia nigra, pars compacta",
    "RN": "Red nucleus", "SNr": "Substantia nigra, pars reticulata",
    "PBP": "Parabrachial pigmented nucleus", "VTA": "Ventral tegmental area",
    "VeP": "Ventral pallidum", "HN": "Habenular nuclei", "HTH": "Hypothalamus",
    "MN": "Mammillary nucleus", "STH": "Subthalamic nucleus",
}  # fmt: skip
CIT168_FAMILY = {"HTH": "hypothalamus", "MN": "hypothalamus", "HN": "thalamus",
                 "EXA": "amygdala", "VeP": "basal_ganglia", "NAC": "basal_ganglia",
                 "Pu": "basal_ganglia", "Ca": "basal_ganglia", "GPe": "basal_ganglia",
                 "GPi": "basal_ganglia", "SNc": "midbrain", "SNr": "midbrain", "RN": "midbrain",
                 "PBP": "midbrain", "VTA": "midbrain", "STH": "thalamus"}  # fmt: skip


def cit168_details(labels_txt: str) -> list[dict]:
    """Details of CIT168 with sides: value 2k is structure k on the left, 2k + 1 on the right
    (see by_side)."""
    out = []
    for line in labels_txt.splitlines():
        if not line.strip():
            continue
        idx, abbr = line.split()[:2]
        k = int(idx) + 1
        name = f"{CIT168_NAMES[abbr]} ({abbr})"
        out.append({"value": 2 * k, "name": name, "side": "L", "abbr": abbr})
        out.append({"value": 2 * k + 1, "name": name, "side": "R", "abbr": abbr})
    return out


def by_side(vol: np.ndarray, x_mm: np.ndarray) -> np.ndarray:
    """A label volume without sides -> value 2k (left, x < 0) or 2k + 1 (right), 0 stays 0."""
    right = (x_mm >= 0).astype(np.int64)
    return np.where(vol > 0, 2 * vol + right, 0)


def free_fractions(cv: np.ndarray, jv: np.ndarray, details: list[dict]) -> dict[str, dict]:
    """Per structure (both sides): voxels in this layer and the share left empty by the layers
    before it (jv: any non-zero voxel is taken)."""
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
    cv: np.ndarray,
    jv: np.ndarray,
    details: list[dict],
    min_free: float = MIN_FREE,
    family: dict[str, str] | None = None,
    prefix: str = "CEREBRA_",
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
                "area_id": area_id(d["name"], prefix),
                "family": (FAMILY if family is None else family).get(
                    d.get("abbr", d["name"]), "other"
                ),
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
