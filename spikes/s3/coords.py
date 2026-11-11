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
Note BrainGlobe says 39.0 µm; the WHS voxel is 39.0625 µm, so the scale corrects a 0.16 % error.

Human (Julich-Brain MPM in MNI152 2009c nonlinear asymmetric): the viewer frame is MNI minus the
centre of the volume, so shown = viewer + centre.
"""

from __future__ import annotations

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


def rat_bregma_map(factor: int, viewer_voxel_mm: float, viewer_origin: tuple) -> dict:
    """Map from the viewer frame of the downsampled Waxholm volume to mm from Bregma.

    The volume is the 39 µm grid downsampled by `factor` (blocks factor**3, from index 0), with
    voxel `viewer_voxel_mm` and affine origin `viewer_origin`: block I covers full voxels
    factor*I .. factor*I + factor - 1, so its centre is full voxel f = factor*I + (factor - 1)/2
    and sits at viewer mm = origin + I * viewer_voxel_mm. Inverting and going through WHS mm:

        shown = WHS_VOXEL_MM * (f - f_bregma)
              = scale * viewer + offset
    """
    c = (factor - 1) / 2
    bregma = whs_mm_to_voxel(WHS_LANDMARKS["bregma"]["mm"])
    scale = factor * WHS_VOXEL_MM / viewer_voxel_mm
    offset = [
        -o * scale + WHS_VOXEL_MM * (c - b) for o, b in zip(viewer_origin, bregma, strict=True)
    ]
    landmarks = {}
    for name, lm in WHS_LANDMARKS.items():
        f = whs_mm_to_voxel(lm["mm"])
        viewer = [
            o + (v - c) / factor * viewer_voxel_mm for o, v in zip(viewer_origin, f, strict=True)
        ]
        shown = [WHS_VOXEL_MM * (v - b) for v, b in zip(f, bregma, strict=True)]
        landmarks[name] = {
            "whs_mm": list(lm["mm"]),
            "viewer_mm": [round(x, 4) for x in viewer],
            "shown_mm": [round(x, 4) for x in shown],
        }
    return {
        "frame": "bregma",
        "axes": {"x": "ML", "y": "AP", "z": "DV"},
        "scale": round(scale, 8),
        "offset": [round(x, 6) for x in offset],
        "landmarks": landmarks,
        "source": WHS_SOURCE,
        "note": (
            "Atlas coordinates of one animal (Waxholm): approximate for any other rat. The skull "
            "is not flat-skull: Lambda is 0.94 mm above Bregma."
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
