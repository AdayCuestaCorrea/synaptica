"""Step 7.5: viewer mm → mm from Bregma (rat) and MNI mm (human), with the published values."""

import json

import pytest
from coords import (
    WHS_LANDMARKS,
    human_mni_map,
    rat_bregma_map,
    shown,
    whs_mm_to_voxel,
    whs_voxel_to_mm,
)

from conftest import FIXTURES

TABLE = json.loads((FIXTURES / "whs_coordinates_v1_01.json").read_text("utf-8"))["rows"]

# The volume C loads (build_assets.py): 39 µm x 3, majority blocks, centred affine.
FACTOR, VMM = 3, 0.117
SHAPE = (171, 342, 171)  # ceil(512 / 3), ceil(1024 / 3), ceil(512 / 3)
ORIGIN = tuple(-s * VMM / 2 for s in SHAPE)


def viewer_mm(full_voxel):
    """Where C draws a full-resolution voxel (centre of its block, in the centred frame)."""
    return tuple(
        o + (v - (FACTOR - 1) / 2) / FACTOR * VMM for o, v in zip(ORIGIN, full_voxel, strict=True)
    )


@pytest.mark.parametrize("name", ["origin", "bregma", "lambda"])
def test_published_table_matches_the_formula(name):
    row = TABLE[name]
    assert whs_voxel_to_mm(row["voxel"]) == pytest.approx(row["mm"], abs=1e-9)
    assert whs_mm_to_voxel(row["mm"]) == pytest.approx(row["voxel"], abs=1e-9)


def test_module_uses_the_published_values():
    for name in ("bregma", "lambda"):
        assert list(WHS_LANDMARKS[name]["voxel"]) == TABLE[name]["voxel"]
        assert list(WHS_LANDMARKS[name]["mm"]) == TABLE[name]["mm"]


def test_bregma_is_zero_and_lambda_is_relative_to_it():
    m = rat_bregma_map(FACTOR, VMM, ORIGIN)
    assert shown(m, viewer_mm(TABLE["bregma"]["voxel"])) == pytest.approx((0, 0, 0), abs=1e-6)
    lam = shown(m, viewer_mm(TABLE["lambda"]["voxel"]))
    expected = [a - b for a, b in zip(TABLE["lambda"]["mm"], TABLE["bregma"]["mm"], strict=True)]
    assert lam == pytest.approx(expected, abs=1e-6)  # (-0.078, -8.242, +0.9375)
    assert m["landmarks"]["lambda"]["shown_mm"] == pytest.approx(expected, abs=1e-4)
    assert m["landmarks"]["bregma"]["viewer_mm"] == pytest.approx(
        viewer_mm(TABLE["bregma"]["voxel"]), abs=1e-4
    )


def test_whs_origin_is_minus_bregma():
    m = rat_bregma_map(FACTOR, VMM, ORIGIN)
    o = shown(m, viewer_mm(TABLE["origin"]["voxel"]))
    assert o == pytest.approx([-x for x in TABLE["bregma"]["mm"]], abs=1e-6)


def test_scale_is_whs_voxel_not_brainglobe_voxel():
    # BrainGlobe says 39.0 µm; one WHS voxel step must still be 0.0390625 mm.
    m = rat_bregma_map(FACTOR, VMM, ORIGIN)
    a = shown(m, viewer_mm((0, 0, 0)))
    b = shown(m, viewer_mm((3, 0, 0)))
    assert b[0] - a[0] == pytest.approx(3 * 0.0390625, abs=1e-9)


def test_human_is_viewer_plus_centre():
    m = human_mni_map((0.5, -17.5, 18.0))
    assert shown(m, (0, 0, 0)) == pytest.approx((0.5, -17.5, 18.0))
    assert shown(m, (-10, 2, 3)) == pytest.approx((-9.5, -15.5, 21.0))
