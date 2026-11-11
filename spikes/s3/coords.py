"""Spike S3, step 7.5 (Sofía's P7): mm from Bregma for the rat, MNI mm for the human.

Throwaway code, not part of the package. Pure functions, no numpy, so the tests need nothing from
the spike-s3 group.

The viewer (mock-up C) works in its own frame: RAS millimetres centred on each volume
(build_assets.py). What it shows is a linear map of that frame, the same on every axis:

    shown = scale * viewer + offset

Rat (Waxholm). Bregma and Lambda are not in the atlas files. They come from a published table:
E. A. Papp and J. G. Bjaalie, "Waxholm Space atlas of the Sprague Dawley rat brain. Coordinates v1
vs v1.01", Neural Systems Laboratory, 16 July 2014, on NITRC (whs-sd-atlas project). In v1.01, high
resolution (39 µm), voxel coordinates are 0-based and WHS millimetres are

    whs_mm = 0.0390625 * (voxel - (244, 623, 248))

with the WHS origin at the decussation of the anterior commissure. The table gives Bregma and
Lambda in voxels and in WHS mm. BrainGlobe's whs_sd_rat_39um (v4.01 delineations) keeps the same
512 x 1024 x 512 grid: the origin voxel falls on the anterior commissure (checked in step 7.5).
BrainGlobe says 39.0 µm; the WHS voxel is 39.0625 µm, and the flat grid uses the WHS one.

The atlas head is not flat skull (Lambda 0.94 mm above Bregma): build_assets.py turns the labels
about x, pivoting on Bregma, so that they are (see flat_skull_angle).

Human (Julich-Brain MPM in MNI152 2009c nonlinear asymmetric): the viewer frame is MNI minus the
centre of the volume, so shown = viewer + centre.
"""

from __future__ import annotations

import math

WHS_VOXEL_MM = 0.0390625
WHS_ORIGIN_VOXEL = (244, 623, 248)  # v1.01, 39 µm, 0-based (x, y, z), RAS

# Papp and Bjaalie 2014, table "Coordinates v1 vs v1.01", columns WHS SDr v1.01, 39 µm.
WHS_LANDMARKS = {
    "bregma": {"voxel": (246, 653, 440), "mm": (0.0781250, 1.1718750, 7.5000000)},
    "lambda": {"voxel": (244, 442, 464), "mm": (0.0000000, -7.0703125, 8.4375000)},
}
WHS_SOURCE = {
    "citation": (
        "Papp EA, Bjaalie JG. Waxholm Space atlas of the Sprague Dawley rat brain. Coordinates "
        "v1 vs v1.01. Neural Systems Laboratory, University of Oslo, 16 July 2014"
    ),
    "url": "https://www.nitrc.org/docman/view.php/1081/2095/Coordinates_v1-v1.01.pdf",
    "table": "WHS SDr v1.01, high resolution (39 µm): voxels and WHS mm",
}


def whs_voxel_to_mm(voxel: tuple[float, float, float]) -> tuple[float, float, float]:
    """0-based WHS voxel (39 µm) → WHS millimetres."""
    return tuple(WHS_VOXEL_MM * (v - o) for v, o in zip(voxel, WHS_ORIGIN_VOXEL, strict=True))


def whs_mm_to_voxel(mm: tuple[float, float, float]) -> tuple[float, float, float]:
    return tuple(m / WHS_VOXEL_MM + o for m, o in zip(mm, WHS_ORIGIN_VOXEL, strict=True))


# ------------------------------------------------------------------ flat skull (step 7.5, A)
# Flat skull means Bregma and Lambda at the same height (Paxinos and Watson). In the atlas animal
# Lambda is 0.94 mm above Bregma, so the head is turned about the left-right axis (x), pivoting on
# Bregma, by the angle that brings Lambda down to Bregma's height. Both points are the published
# ones: nothing else is assumed. A turn about x keeps sagittal planes sagittal.


def flat_skull_angle() -> float:
    """Radians to turn the (y, z) plane so that Lambda ends at Bregma's height (about 6.5°)."""
    b, lam = WHS_LANDMARKS["bregma"]["mm"], WHS_LANDMARKS["lambda"]["mm"]
    dy, dz = lam[1] - b[1], lam[2] - b[2]
    return math.atan2(dz, -dy)


def whs_to_flat(p: tuple) -> tuple:
    """WHS mm → mm from Bregma, flat skull (x ML, y AP, z DV)."""
    a = flat_skull_angle()
    b = WHS_LANDMARKS["bregma"]["mm"]
    x, y, z = (p[0] - b[0], p[1] - b[1], p[2] - b[2])
    return (x, y * math.cos(a) - z * math.sin(a), y * math.sin(a) + z * math.cos(a))


def flat_to_whs(q: tuple) -> tuple:
    a = flat_skull_angle()
    b = WHS_LANDMARKS["bregma"]["mm"]
    x, y, z = q
    yy, zz = y * math.cos(a) + z * math.sin(a), -y * math.sin(a) + z * math.cos(a)
    return (x + b[0], yy + b[1], zz + b[2])


def rat_flat_map(grid_min: tuple, grid_voxel_mm: float, factor: int, viewer_origin: tuple) -> dict:
    """Map from C's viewer frame to mm from Bregma, flat skull.

    build_assets.py resamples the labels onto a grid that is already flat and in mm from Bregma:
    full voxel u sits at grid_min + u * grid_voxel_mm. Downsampled by `factor`, block I has its
    centre at u = factor * I + (factor - 1) / 2 and is drawn at viewer_origin + I * factor *
    grid_voxel_mm. So shown = viewer + offset, with scale 1.
    """
    half = (factor - 1) / 2 * grid_voxel_mm
    offset = [g + half - o for g, o in zip(grid_min, viewer_origin, strict=True)]
    landmarks = {}
    for name, lm in WHS_LANDMARKS.items():
        flat = whs_to_flat(lm["mm"])
        landmarks[name] = {
            "whs_mm": list(lm["mm"]),
            "viewer_mm": [round(f - o, 4) for f, o in zip(flat, offset, strict=True)],
            "shown_mm": [round(f, 4) for f in flat],
        }
    return {
        "frame": "bregma",
        "flat_skull": True,
        "flat_skull_deg": round(math.degrees(flat_skull_angle()), 3),
        "axes": {"x": "ML", "y": "AP", "z": "DV"},
        "scale": 1.0,
        "offset": [round(x, 6) for x in offset],
        "landmarks": landmarks,
        "source": WHS_SOURCE,
        "note": (
            "Atlas coordinates of one animal (Waxholm), turned to flat skull (Bregma and Lambda "
            "at the same height): approximate for any other rat."
        ),
    }


def human_mni_map(centre: tuple) -> dict:
    return {
        "frame": "mni",
        "axes": {"x": "x", "y": "y", "z": "z"},
        "scale": 1.0,
        "offset": [round(float(x), 6) for x in centre],
        "landmarks": {},
        "source": {
            "citation": "MNI ICBM 152 2009c nonlinear asymmetric (space of the Julich-Brain MPM)",
            "url": "https://www.bic.mni.mcgill.ca/ServicesAtlases/ICBM152NLin2009",
        },
        "note": None,
    }


def shown(m: dict, viewer: tuple) -> tuple:
    return tuple(m["scale"] * v + o for v, o in zip(viewer, m["offset"], strict=True))
