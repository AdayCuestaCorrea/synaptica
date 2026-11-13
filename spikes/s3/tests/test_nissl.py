"""Sofía's review: the rat's real Nissl sections on the viewer's coronal plane (nissl.py).
Synthetic registrations and images, no network."""

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("scipy")

import nissl  # noqa: E402
from coords import WHS_ORIGIN_VOXEL, WHS_VOXEL_MM, flat_to_whs  # noqa: E402


def test_pyramid_level_first_at_or_above_target():
    # 14400 x 15433: top level 14; level 10 is 900 x 965, level 9 is 450 x 483.
    assert nissl.pyramid_level(14400, 15433) == (10, 900, 965)
    assert nissl.pyramid_level(300, 200) == (9, 300, 200)  # smaller than the target: full size


def test_warp_without_markers_is_identity_and_moves_with_one():
    src, dst = nissl.corners_and_markers(100, 50, [])
    pts = np.array([[10.0, 10.0], [90.0, 40.0]])
    assert np.allclose(nissl.warp(src, dst, pts), pts)
    src, dst = nissl.corners_and_markers(100, 50, [[50, 25, 60, 25]])
    assert np.allclose(nissl.warp(src, dst, np.array([[50.0, 25.0]])), [[60.0, 25.0]])


def anchoring_for(ap_flat: float, width_mm: float, height_mm: float) -> list:
    """A QuickNII anchoring whose image is a coronal plane (flat skull) at ap_flat mm from
    Bregma, centred on x = 0 and from z = 0 down, image x to the right and y downwards."""
    org = np.array(WHS_ORIGIN_VOXEL, dtype=float)

    def vox(q):
        return np.array(flat_to_whs(q)) / WHS_VOXEL_MM + org

    o = vox((-width_mm / 2, ap_flat, 0.0))
    u = vox((width_mm / 2, ap_flat, 0.0)) - o
    v = vox((-width_mm / 2, ap_flat, -height_mm)) - o
    return [*o, *u, *v]


def test_anchoring_to_flat_round_trip():
    a, u, v = nissl.anchoring_to_flat(anchoring_for(-3.0, 10.0, 8.0))
    assert np.allclose(a, [-5.0, -3.0, 0.0], atol=1e-9)
    assert np.allclose(u, [10.0, 0.0, 0.0], atol=1e-9)
    assert np.allclose(v, [0.0, 0.0, -8.0], atol=1e-9)


def test_resample_puts_the_image_on_the_plane():
    # 100 x 80 px image, white with a dark square in its left half, top: 10 x 8 mm.
    img = np.full((80, 100), 255, dtype=np.uint8)
    img[20:40, 10:30] = 40
    sl = {"width": 100, "height": 80, "anchoring": anchoring_for(-3.0, 10.0, 8.0), "markers": []}
    res = nissl.resample(img, sl)
    assert res["ap_mm"] == pytest.approx(-3.0, abs=1e-6)
    x0, _, _, z1 = res["extent_mm"]
    assert x0 == pytest.approx(-5.0, abs=1e-3) and z1 == pytest.approx(0.0, abs=1e-3)
    out = res["image"]
    # The square is at x = -4..-2 mm, z = -2..-4 mm: dark there, white at the opposite corner.
    col = int((-3.0 - x0) / nissl.PIXEL_MM)
    row = int((z1 - -3.0) / nissl.PIXEL_MM)
    assert out[row, col] < 80
    assert out[row, out.shape[1] - col] == 255
    cropped = nissl.crop(res, margin_px=0)
    cx0, cx1, cz0, cz1 = cropped["extent_mm"]
    assert cx0 == pytest.approx(-4.0, abs=0.06) and cx1 == pytest.approx(-2.0, abs=0.06)
    assert cz1 == pytest.approx(-2.0, abs=0.06) and cz0 == pytest.approx(-4.0, abs=0.06)
