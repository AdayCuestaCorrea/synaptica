"""Sofía's review: CerebrA fills only what Julich-Brain lacks (cerebra.py), and the coverage
audit counts families (coverage.py). Small synthetic volumes, no atlas files, no network."""

import json

import pytest

np = pytest.importorskip("numpy")

import cerebra as cb  # noqa: E402
from coverage import by_family, lowest_z  # noqa: E402

from conftest import FIXTURES  # noqa: E402

CSV = """Mindboggle ID,Label Name,CerebrA ID,,Notes,Dice Kappa
,,RH Labels,LH Labels,,
16,Brainstem,11,62,,0.65
45,Cerebellum Gray Matter,46,97,,0.83
2035,Insula,23,74,,0.88
"""


@pytest.fixture
def details(tmp_path):
    p = tmp_path / "CerebrA_LabelDetails.csv"
    p.write_text(CSV, encoding="utf-8")
    return cb.read_details(p)


def test_read_details_both_sides(details):
    assert {(d["name"], d["side"], d["value"]) for d in details} == {
        ("Brainstem", "R", 11), ("Brainstem", "L", 62),
        ("Cerebellum Gray Matter", "R", 46), ("Cerebellum Gray Matter", "L", 97),
        ("Insula", "R", 23), ("Insula", "L", 74),
    }  # fmt: skip


def volumes():
    """CerebrA: brainstem (fully free), cerebellum (3 of 4 voxels free), insula (all under
    Julich-Brain). Julich-Brain: the insula and one cerebellum voxel."""
    cv = np.zeros((4, 4, 4), dtype=np.int64)
    jv = np.zeros((4, 4, 4), dtype=np.uint16)
    cv[0, 0, :2] = 11  # brainstem R
    cv[1, 0, :2] = 62  # brainstem L
    cv[2, 0, :4] = 46  # cerebellum R
    cv[3, 3, :2] = 23  # insula R
    jv[3, 3, :2] = 5
    jv[2, 0, 3] = 7  # Julich-Brain has one cerebellum voxel (a deep nucleus)
    return cv, jv


def test_select_keeps_only_free_structures_and_voxels(details):
    cv, jv = volumes()
    compact, rows, report = cb.select(cv, jv, details)
    assert report["kept"] == ["Brainstem", "Cerebellum Gray Matter"]
    assert report["left_out"] == ["Insula"]
    assert report["structures"]["Cerebellum Gray Matter"]["free_fraction"] == 0.75
    # Never two regions in one voxel: where Julich-Brain has a label, CerebrA has none.
    assert not np.any((compact > 0) & (jv > 0))
    assert int((compact > 0).sum()) == 2 + 2 + 3
    names = [(r["name"], r["side"]) for r in rows[1:]]
    assert names == [("Brainstem", "L"), ("Brainstem", "R"), ("Cerebellum Gray Matter", "R")]
    assert [r["index"] for r in rows] == list(range(len(rows)))
    assert rows[1]["area_id"] == "CEREBRA_BRAINSTEM" and rows[1]["family"] == "hindbrain"
    # every compact value points to its row
    assert compact[1, 0, 0] == 1 and compact[0, 0, 0] == 2 and compact[2, 0, 0] == 3


def test_select_threshold(details):
    cv, jv = volumes()
    _, _, report = cb.select(cv, jv, details, min_free=0.8)
    assert report["kept"] == ["Brainstem"]


def test_select_refuses_other_grid(details):
    cv, jv = volumes()
    with pytest.raises(ValueError):
        cb.select(cv, jv[:3], details)


def test_by_family_and_lowest_z():
    vol = np.zeros((2, 2, 3), dtype=np.uint16)
    vol[0, 0, 1:] = 1
    vol[1, 1, 2] = 2
    rows = [
        {"index": 0},
        {"index": 1, "group": "hindbrain", "area_id": "A", "id": "a"},
        {"index": 2, "group": "hindbrain", "area_id": "A", "id": "b"},  # same area, other side
    ]
    fam = by_family(vol, rows, 2.0)
    assert fam == {"hindbrain": {"regions": 1, "mm3": 6.0, "share": 1.0}}
    aff = np.diag([1.0, 1.0, 1.0, 1.0])
    aff[2, 3] = -10.0
    assert lowest_z(vol, aff) == -9.0


def test_published_cerebra_files_are_consistent():
    """The files the viewer loads: own licence, rows in index order, no Julich-Brain rows."""
    site = FIXTURES.parents[2] / "spikes" / "s3" / "site" / "data"
    lic = json.loads((site / "cerebra" / "licence.json").read_text())
    assert lic["licence"].startswith("CC0 1.0") and "Mindboggle" in lic["licence"]
    rows = json.loads((site / "cerebra" / "labels.json").read_text())["rows"]
    assert [r["index"] for r in rows] == list(range(len(rows)))
    assert all(r["area_id"].startswith("CEREBRA_") for r in rows[1:])
    pairs = json.loads((site / "equivalencias.json").read_text())["pairs"]
    assert all("human" in p and "julich" not in p for p in pairs)
    assert {h["atlas"] for p in pairs for h in p["human"]} == {"julich", "cerebra"}
