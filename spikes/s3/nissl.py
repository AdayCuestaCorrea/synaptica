"""Spike S3, Sofía's review (2026-11-12): a real stain for the rat, in the 2D slice only.

There is no licensed 3D histology of the rat brain (results/tincion.md), but there are sections
registered to Waxholm one by one. The coronal Nissl (thionine) series of the Timm-Nissl atlas
(Blixhavn et al. 2023, EBRAINS, CC BY 4.0; animal H108c, a Wistar rat) has 146 sections, each
with its QuickNII anchoring (affine) and its VisuAlign markers (non-linear), and a Deep Zoom
image pyramid. For every section this module:

1. takes one pyramid level (about 900 px wide; the full TIFFs are GB), never the full image;
2. resamples it onto the viewer's coronal plane, flat skull, in mm from Bregma, at 39 µm: for
   each output point (x, z), the section plane gives the anchoring coordinates (exact 2 x 2
   solve), VisuAlign's piecewise-affine warp gives the image point, which is sampled;
3. keeps the thionine colour, stretches the contrast (one linear map for the three channels, so
   the hue stays) and makes the bare slide around the tissue transparent (finish);
4. writes it as a WebP, with its AP position and the AP range the (slightly oblique) section
   spans.

The viewer shows the section nearest to its coronal slice, says how far it is, and that it is
another rat. Pure numpy/scipy here; the network and the files are in build_assets.py.

QuickNII (Puchades et al. 2019): a point (x, y) of the registered image, in pixels of the
image size given in the series JSON, is at atlas voxel o + (x / W) u + (y / H) v, with
anchoring = o + u + v (WHS 39 µm grid, x left to right, y posterior to anterior, z inferior to
superior). VisuAlign markers are [x, y, nx, ny]: the atlas point at (x, y) belongs at (nx, ny)
of the image; the image corners, 10 % outside, stay where they are (as in PyNutil).
"""

from __future__ import annotations

import numpy as np
from coords import WHS_ORIGIN_VOXEL, WHS_VOXEL_MM, flat_skull_angle, whs_to_flat

PIXEL_MM = WHS_VOXEL_MM  # output pixel: one WHS voxel, 39 µm
BACKGROUND = 255  # the bare slide (white): outside the image too


def pyramid_level(width: int, height: int, target: int = 900) -> tuple[int, int, int]:
    """Deep Zoom level whose larger side is the first at or above target px: (level, w, h)."""
    top = int(np.ceil(np.log2(max(width, height))))
    for level in range(top + 1):
        k = 2 ** (top - level)
        w, h = -(-width // k), -(-height // k)
        if max(w, h) >= target:
            return level, w, h
    return top, width, height


def corners_and_markers(w: float, h: float, markers: list) -> tuple[np.ndarray, np.ndarray]:
    """VisuAlign control points: (x, y) atlas positions and (nx, ny) image positions."""
    corners = [(-0.1 * w, -0.1 * h), (1.1 * w, -0.1 * h), (-0.1 * w, 1.1 * h), (1.1 * w, 1.1 * h)]
    src = [c for c in corners] + [(m[0], m[1]) for m in markers]
    dst = [c for c in corners] + [(m[2], m[3]) for m in markers]
    return np.array(src, dtype=float), np.array(dst, dtype=float)


def warp(src: np.ndarray, dst: np.ndarray, pts: np.ndarray) -> np.ndarray:
    """Piecewise-affine map of pts from src positions to dst positions (Delaunay on src).

    Points outside every triangle (only beyond the 10 % margin) keep their position."""
    from scipy.spatial import Delaunay

    tri = Delaunay(src)
    simplex = tri.find_simplex(pts)
    out = pts.copy()
    ok = simplex >= 0
    if ok.any():
        t = tri.transform[simplex[ok]]
        b = np.einsum("nij,nj->ni", t[:, :2], pts[ok] - t[:, 2])
        bary = np.c_[b, 1 - b.sum(axis=1)]
        out[ok] = np.einsum("ni,nij->nj", bary, dst[tri.simplices[simplex[ok]]])
    return out


def anchoring_to_flat(anchoring: list) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Section plane in flat-skull mm from Bregma: point(s, t) = A + s U + t V, s, t in 0..1."""
    o, u, v = (np.array(anchoring[i : i + 3], dtype=float) for i in (0, 3, 6))
    org = np.array(WHS_ORIGIN_VOXEL, dtype=float)

    def to_flat(vox: np.ndarray) -> np.ndarray:
        return np.array(whs_to_flat(tuple(WHS_VOXEL_MM * (vox - org))))

    a = to_flat(o)
    # whs_to_flat is affine (shift + rotation about x): vectors turn without the shift.
    rot = flat_skull_angle()
    c, s_ = np.cos(rot), np.sin(rot)

    def turn(vec: np.ndarray) -> np.ndarray:
        x, y, z = WHS_VOXEL_MM * vec
        return np.array([x, y * c - z * s_, y * s_ + z * c])

    return a, turn(u), turn(v)


def grey(img: np.ndarray) -> np.ndarray:
    """Luminance of an 8-bit RGB (or grey) image."""
    if img.ndim == 2:
        return img.astype(np.float32)
    return img[..., :3].astype(np.float32) @ np.array([0.299, 0.587, 0.114], dtype=np.float32)


def resample(img: np.ndarray, sl: dict) -> dict:
    """One section on the viewer's coronal plane. img: 8-bit RGB or grey, any pyramid level.

    Returns the output image (rows: z from top to bottom, columns: x from left to right), its
    extent in flat mm from Bregma and the AP position (mean, min, max over the tissue)."""
    wj, hj = float(sl["width"]), float(sl["height"])
    a, u, v = anchoring_to_flat(sl["anchoring"])
    # The image corners on the coronal (x, z) plane give the output extent.
    st = np.array([[0, 0], [1, 0], [0, 1], [1, 1]], dtype=float)
    corners = a + st[:, :1] * u + st[:, 1:] * v
    x0, x1 = corners[:, 0].min(), corners[:, 0].max()
    z0, z1 = corners[:, 2].min(), corners[:, 2].max()
    nx = int(np.ceil((x1 - x0) / PIXEL_MM))
    nz = int(np.ceil((z1 - z0) / PIXEL_MM))
    xs = x0 + (np.arange(nx) + 0.5) * PIXEL_MM
    zs = z1 - (np.arange(nz) + 0.5) * PIXEL_MM  # top row is the highest z (dorsal)
    gx, gz = np.meshgrid(xs, zs)
    # (x, z) = A_xz + s U_xz + t V_xz  ->  (s, t)
    m = np.array([[u[0], v[0]], [u[2], v[2]]])
    rhs = np.stack([gx.ravel() - a[0], gz.ravel() - a[2]])
    s, t = np.linalg.solve(m, rhs)
    y = a[1] + s * u[1] + t * v[1]
    src, dst = corners_and_markers(wj, hj, sl.get("markers") or [])
    p = warp(src, dst, np.c_[s * wj, t * hj])
    h, w = img.shape[:2]
    col = p[:, 0] / wj * w - 0.5
    row = p[:, 1] / hj * h - 0.5
    from scipy.ndimage import map_coordinates

    chans = [img] if img.ndim == 2 else [img[..., c] for c in range(3)]
    planes = [
        np.clip(np.rint(map_coordinates(c.astype(np.float32), [row, col], order=1,
                                        cval=BACKGROUND)), 0, 255).astype(np.uint8)
        .reshape(nz, nx)
        for c in chans
    ]  # fmt: skip
    out = planes[0] if img.ndim == 2 else np.stack(planes, axis=-1)
    inside = ((s >= 0) & (s <= 1) & (t >= 0) & (t <= 1)).reshape(nz, nx)
    out[~inside] = BACKGROUND
    tissue = inside & (grey(out) < 200)
    ys = y.reshape(nz, nx)[tissue] if tissue.any() else y
    return {
        "image": out,
        "extent_mm": [
            round(float(x0), 4),
            round(float(x0 + nx * PIXEL_MM), 4),
            round(float(z1 - nz * PIXEL_MM), 4),
            round(float(z1), 4),
        ],
        "ap_mm": round(float(np.median(ys)), 3),
        "ap_range_mm": [round(float(ys.min()), 3), round(float(ys.max()), 3)],
        "tissue_fraction": round(float(tissue.mean()), 4),
    }


def crop(res: dict, margin_px: int = 8) -> dict:
    """Crop the output to the tissue (dark pixels) plus a margin, adjusting the extent."""
    img = res["image"]
    dark = grey(img) < 200
    rows = np.where(dark.any(axis=1))[0]
    cols = np.where(dark.any(axis=0))[0]
    if not len(rows):
        return res
    r0, r1 = max(rows[0] - margin_px, 0), min(rows[-1] + margin_px + 1, img.shape[0])
    c0, c1 = max(cols[0] - margin_px, 0), min(cols[-1] + margin_px + 1, img.shape[1])
    x0, _, _, z1 = res["extent_mm"]
    out = dict(res)
    out["image"] = img[r0:r1, c0:c1]
    out["extent_mm"] = [round(x0 + c0 * PIXEL_MM, 4), round(x0 + c1 * PIXEL_MM, 4),
                        round(z1 - r1 * PIXEL_MM, 4), round(z1 - r0 * PIXEL_MM, 4)]  # fmt: skip
    return out


SLIDE = 236  # luminance at or above which a pixel is bare slide (measured: tissue 150-230)


def finish(img: np.ndarray) -> np.ndarray:
    """RGBA for the viewer: tissue silhouette opaque, slide around it transparent; contrast
    stretched from the 1st percentile of the tissue to the slide level, the same linear map on
    every channel (a display change only: no pixel is invented, relative values are kept)."""
    from scipy import ndimage

    rgb = np.repeat(img[..., None], 3, axis=-1) if img.ndim == 2 else img[..., :3]
    lum = grey(rgb)
    tissue = ndimage.binary_fill_holes(ndimage.binary_closing(lum < SLIDE, iterations=2))
    tissue = ndimage.binary_opening(tissue, iterations=1)
    lo = float(np.percentile(lum[tissue], 1)) if tissue.any() else 0.0
    scale = 255.0 / max(SLIDE - lo, 1.0)
    out = np.clip((rgb.astype(np.float32) - lo) * scale, 0, 255).astype(np.uint8)
    alpha = np.where(tissue, 255, 0).astype(np.uint8)
    return np.dstack([out, alpha])
