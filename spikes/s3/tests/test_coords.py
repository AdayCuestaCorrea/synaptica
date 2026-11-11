"""Step 7.5: mm from Bregma, flat skull (rat), and MNI mm (human), with the published values."""

import json
import math

import pytest
from coords import (
    WHS_LANDMARKS,
    WHS_VOXEL_MM,
    flat_skull_angle,
    flat_to_whs,
    human_mni_map,
    rat_flat_map,
    shown,
    whs_mm_to_voxel,
    whs_to_flat,
    whs_voxel_to_mm,
)

from conftest import FIXTURES

TABLE = json.loads((FIXTURES / "whs_coordinates_v1_01.json").read_text("utf-8"))["rows"]

# Like build_assets.py: flat grid of WHS voxels from grid_min, downsampled x3, centred affine.
FACTOR, VMM = 3, 3 * WHS_VOXEL_MM
GRID_MIN = (-10.0, -15.0, -12.0)
SHAPE = (171, 342, 171)
ORIGIN = tuple(-s * VMM / 2 for s in SHAPE)


def viewer_of_block(block):
    return tuple(o + i * VMM for o, i in zip(ORIGIN, block, strict=True))


def flat_of_block(block):
    """Flat mm of the centre of a downsampled block (full voxels 3I .. 3I + 2)."""
    return tuple(g + (3 * i + 1) * WHS_VOXEL_MM for g, i in zip(GRID_MIN, block, strict=True))


@pytest.mark.parametrize("name", ["origin", "bregma", "lambda"])
def test_published_table_matches_the_formula(name):
    row = TABLE[name]
    assert whs_voxel_to_mm(row["voxel"]) == pytest.approx(row["mm"], abs=1e-9)
    assert whs_mm_to_voxel(row["mm"]) == pytest.approx(row["voxel"], abs=1e-9)


def test_module_uses_the_published_values():
    for name in ("bregma", "lambda"):
        assert list(WHS_LANDMARKS[name]["voxel"]) == TABLE[name]["voxel"]
        assert list(WHS_LANDMARKS[name]["mm"]) == TABLE[name]["mm"]


def test_flat_skull_puts_lambda_at_bregma_height():
    bregma = whs_to_flat(TABLE["bregma"]["mm"])
    lam = whs_to_flat(TABLE["lambda"]["mm"])
    assert bregma == pytest.approx((0, 0, 0), abs=1e-12)
    assert lam[2] == pytest.approx(0, abs=1e-12)
    # A turn: the Bregma-Lambda distance is kept, now all of it along AP (plus the tiny ML).
    d = [a - b for a, b in zip(TABLE["lambda"]["mm"], TABLE["bregma"]["mm"], strict=True)]
    assert math.hypot(lam[1], lam[2]) == pytest.approx(math.hypot(d[1], d[2]), abs=1e-12)
    assert lam[1] == pytest.approx(-8.2953, abs=1e-4)
    assert lam[0] == pytest.approx(d[0], abs=1e-12)
    assert math.degrees(flat_skull_angle()) == pytest.approx(6.489, abs=1e-3)


def test_flat_and_back():
    for p in [(1.0, 2.0, 3.0), (-4.5, -9.0, 0.2), TABLE["origin"]["mm"]]:
        assert flat_to_whs(whs_to_flat(p)) == pytest.approx(p, abs=1e-12)


def test_viewer_to_shown_on_the_flat_grid():
    m = rat_flat_map(GRID_MIN, WHS_VOXEL_MM, FACTOR, ORIGIN)
    assert m["scale"] == 1.0
    for block in [(0, 0, 0), (10, 200, 85), (170, 341, 170)]:
        assert shown(m, viewer_of_block(block)) == pytest.approx(flat_of_block(block), abs=1e-6)


def test_landmarks_in_the_map():
    m = rat_flat_map(GRID_MIN, WHS_VOXEL_MM, FACTOR, ORIGIN)
    assert m["landmarks"]["bregma"]["shown_mm"] == pytest.approx([0, 0, 0], abs=1e-4)
    assert m["landmarks"]["lambda"]["shown_mm"] == pytest.approx([-0.0781, -8.2953, 0], abs=1e-4)
    for lm in m["landmarks"].values():
        assert shown(m, lm["viewer_mm"]) == pytest.approx(lm["shown_mm"], abs=1e-3)


def test_human_is_viewer_plus_centre():
    m = human_mni_map((0.5, -17.5, 18.0))
    assert shown(m, (0, 0, 0)) == pytest.approx((0.5, -17.5, 18.0))
    assert shown(m, (-10, 2, 3)) == pytest.approx((-9.5, -15.5, 21.0))
