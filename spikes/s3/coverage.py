"""Spike S3, Sofía's review (2026-11-12): what each brain has, by family of regions.

The human lacked the cerebellum, the brainstem and the spinal cord; Aday asked what else might
be missing. Both atlases already sort their regions into the same families (build_assets.py,
calm palette: cortex, hippocampus, basal ganglia, thalamus, hindbrain, white matter...), so the
comparison is by family, measured on the files the viewer loads (site/data), with no hand
mapping. Also the lowest labelled point of each brain (spinal cord) and the human structures
CerebrA had but left out because Julich-Brain already covers them.

    uv run --group spike-s3 python spikes/s3/coverage.py   # writes results/cobertura.json
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
DATA = HERE / "site" / "data"


def load(atlas: str) -> tuple[np.ndarray, list[dict], np.ndarray]:
    import nibabel as nib

    img = nib.load(DATA / atlas / "labels.nii.gz")
    rows = json.loads((DATA / atlas / "labels.json").read_text())["rows"]
    return np.asarray(img.dataobj), rows, img.affine


def by_family(vol: np.ndarray, rows: list[dict], voxel_mm3: float) -> dict[str, dict]:
    """Per family: regions (without side), volume in mm³ and share of the labelled volume."""
    counts = np.bincount(vol.ravel(), minlength=len(rows))
    out: dict[str, dict] = {}
    total = float(counts[1:].sum())
    for r in rows[1:]:
        f = out.setdefault(r["group"], {"regions": set(), "voxels": 0})
        f["regions"].add(r.get("area_id") or r["id"])
        f["voxels"] += int(counts[r["index"]])
    return {
        k: {
            "regions": len(v["regions"]),
            "mm3": round(v["voxels"] * voxel_mm3, 1),
            "share": round(v["voxels"] / total, 4) if total else 0.0,
        }
        for k, v in sorted(out.items())
    }


def lowest_z(vol: np.ndarray, affine: np.ndarray) -> float:
    """Lowest labelled point (mm, the file's own frame)."""
    z = np.nonzero(vol.any(axis=(0, 1)))[0]
    return round(float(affine[2, 3] + z.min() * affine[2, 2]), 1)


def main() -> None:
    wv, wr, wa = load("waxholm")
    jv, jr, ja = load("julich")
    cv, cr, ca = load("cerebra")
    rat_mm3 = float(abs(np.linalg.det(wa[:3, :3])))
    spinal = [r for r in wr[1:] if "spinal cord" in r["name"].lower()]
    families = sorted(
        {r["group"] for r in wr[1:]} | {r["group"] for r in jr[1:]} | {r["group"] for r in cr[1:]}
    )
    rat, jul, cer = by_family(wv, wr, rat_mm3), by_family(jv, jr, 1.0), by_family(cv, cr, 1.0)
    manifest = json.loads((DATA / "manifest.json").read_text())
    sel = manifest["cerebra"]["selection"]
    mni_dz = json.loads((DATA / "julich" / "coords.json").read_text())["offset"][2]
    out = {
        "families": {
            f: {"rat": rat.get(f), "human_julich": jul.get(f), "human_cerebra": cer.get(f)}
            for f in families
        },
        "rat_spinal_cord": [{"name": r["name"], "side": r["side"]} for r in spinal],
        "lowest_labelled_z_mm": {
            "rat_flat_frame": lowest_z(wv, wa),
            "human_julich_mni": round(lowest_z(jv, ja) + mni_dz, 1),
            "human_cerebra_mni": round(lowest_z(cv, ca) + mni_dz, 1),
            "human_grid_bottom_mni": round(float(ja[2, 3]) + mni_dz, 1),
        },
        "cerebra_left_out": {n: sel["structures"][n]["free_fraction"] for n in sel["left_out"]},
        "cerebra_min_free": sel["min_free"],
    }
    (HERE / "results" / "cobertura.json").write_text(
        json.dumps(out, indent=1, ensure_ascii=False) + "\n"
    )
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
