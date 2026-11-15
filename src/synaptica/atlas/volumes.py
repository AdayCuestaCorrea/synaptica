"""Operations on label volumes shared by every atlas of Neuro Atlas.

Copied from ``spikes/s3/build_assets.py`` (spike S3, Phase 0) for Neuro Atlas (Phase 2,
SCOPE v160). numpy and scipy only, except :func:`save_nifti` (nibabel), so the tests run on
tiny synthetic volumes without any atlas.

Each function works on one atlas at a time: nothing here combines two atlases (their licences
differ; CLAUDE.md, "Licencias").
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path

import numpy as np

from synaptica.atlas.coords import (
    WHS_ORIGIN_VOXEL,
    WHS_VOXEL_MM,
    flat_skull_angle,
    flat_to_whs,
    whs_to_flat,
)


def flat_skull(ras: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Turn the 39 µm Waxholm labels to flat skull (S3 step 7.5, option A), nearest neighbour.

    Input: RAS labels on the WHS v1.01 grid (voxel v is at 0.0390625 * (v - origin voxel) WHS
    mm). Output: labels on a grid of the same voxel size in mm from Bregma, flat skull
    (coords.py): voxel u is at grid_min + u * 0.0390625. Only the box around the brain is
    resampled.
    """
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
    # Output index u → input index: flat_to_whs(grid_min + u * v) / v + o - lo. Same voxel
    # size, so the linear part is the inverse turn.
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


def save_nifti(path: Path, data: np.ndarray, voxel_mm: float, origin: np.ndarray,
               dtype: type = np.uint16) -> int:  # fmt: skip
    """A gzipped NIfTI on a diagonal RAS grid; returns its size in bytes."""
    import nibabel as nib

    aff = np.diag([voxel_mm, voxel_mm, voxel_mm, 1.0])
    aff[:3, 3] = origin
    img = nib.Nifti1Image(data.astype(dtype), aff)
    img.header.set_xyzt_units("mm")
    img.header.set_qform(aff, code=1)
    img.header.set_sform(aff, code=1)
    nib.save(img, path)
    return path.stat().st_size


def write_json(path: Path, data: dict, *, indent: int | None = 2) -> None:
    """UTF-8 JSON with a final newline, the same bytes for the same data (idempotent)."""
    path.write_text(json.dumps(data, indent=indent, ensure_ascii=False) + "\n", encoding="utf-8")


def add_centroids(rows: list[dict], vol: np.ndarray, voxel_mm: float, origin: np.ndarray) -> None:
    """Voxel count and centroid (mm, the NIfTI's own RAS grid) of every row, in place.

    The viewer moves its slices and cut to the region picked in the other atlas. The centroid
    is computed on the same volume and affine the viewer loads, so it lands where Niivue draws
    the region. Rows of one atlas only; nothing crosses between atlases.
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
