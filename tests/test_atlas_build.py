"""``syn atlas build`` (src/synaptica/atlas/): the pieces that do not need the atlases.

Tiny synthetic volumes and label tables; no network (the downloads go through an injected
fetch). The full build is checked by hand against the S3 data (SCOPE v160).
"""

import json

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("scipy")

from synaptica.atlas import build, palette  # noqa: E402
from synaptica.atlas.licences import LICENCES  # noqa: E402
from synaptica.atlas.volumes import add_centroids, majority_downsample, save_nifti  # noqa: E402

# ---------------------------------------------------------------- palette


def test_family_first_rule_wins_and_unknown_is_other():
    assert palette.family(["Brain", "Cerebral cortex", "Hippocampal formation"]) == "hippocampus"
    assert palette.family(["Brain", "Cerebral cortex", "Motor cortex"]) == "cortex"
    assert palette.family(["GapMap Frontal-I"]) == "cortex_gap"
    assert palette.family(["Something new"]) == "other"


def test_colours_are_stable_and_vary_between_neighbours():
    members = [("cortex", ["frontal lobe"], k) for k in ("b", "a", "c")]
    first = palette.colours(members)
    assert first == palette.colours(list(reversed(members)))  # order of input does not matter
    assert len({c for _, c in first.values()}) == 3  # neighbours of a family differ a little
    assert all(f == "cortex" for f, _ in first.values())
    assert all(c.startswith("#") and len(c) == 7 for _, c in first.values())


# ---------------------------------------------------------------- volumes


def test_majority_downsample_and_keep_small():
    vol = np.zeros((4, 4, 4), dtype=np.uint16)
    vol[:2, :2, :2] = 1  # fills one 2x2x2 block
    vol[2:, 2:, 2:] = 2
    vol[3, 3, 3] = 3  # one voxel: loses its block to label 2
    plain = majority_downsample(vol, 2)
    assert plain.shape == (2, 2, 2)
    assert plain[0, 0, 0] == 1 and plain[1, 1, 1] == 2 and 3 not in plain
    kept = majority_downsample(vol, 2, keep_small=True)
    assert 3 not in kept  # it would take label 2's only block, so 2 keeps it
    vol2 = vol.copy()
    vol2[2:, :2, :2] = 2  # now label 2 has a second block
    assert 3 in majority_downsample(vol2, 2, keep_small=True)


def test_add_centroids_counts_and_centres():
    vol = np.zeros((3, 3, 3), dtype=np.uint16)
    vol[0, 0, 0] = 1
    vol[2, 2, 2] = 1
    rows = [{"index": 0}, {"index": 1}, {"index": 2}]
    add_centroids(rows, vol, 2.0, np.array([-2.0, -2.0, -2.0]))
    assert rows[1] == {"index": 1, "voxels": 2, "centroid_mm": [0.0, 0.0, 0.0]}
    assert rows[2] == {"index": 2, "voxels": 0, "centroid_mm": None}  # nothing to centre on


def test_save_nifti_round_trip(tmp_path):
    nib = pytest.importorskip("nibabel")
    vol = np.arange(8, dtype=np.uint16).reshape(2, 2, 2)
    save_nifti(tmp_path / "v.nii.gz", vol, 0.5, np.array([1.0, 2.0, 3.0]))
    img = nib.load(tmp_path / "v.nii.gz")
    assert np.array_equal(np.asarray(img.dataobj), vol)
    assert np.allclose(img.affine, [[0.5, 0, 0, 1], [0, 0.5, 0, 2], [0, 0, 0.5, 3], [0, 0, 0, 1]])
    save_nifti(tmp_path / "u.nii.gz", vol, 1.0, np.zeros(3), dtype=np.uint8)
    assert nib.load(tmp_path / "u.nii.gz").get_data_dtype() == np.uint8


# ---------------------------------------------------------------- downloads and cache


def test_get_downloads_once_then_reads_the_cache(tmp_path):
    calls = []

    def fetch(url, params):
        calls.append((url, params))
        return b"data"

    b = build.Build(out=tmp_path / "out", cache=tmp_path / "cache", fetch=fetch)
    assert b.get("x/f.bin", "https://example.org/f", {"a": "1"}).read_bytes() == b"data"
    assert b.get("x/f.bin", "https://example.org/f").read_bytes() == b"data"
    assert calls == [("https://example.org/f", {"a": "1"})]


def test_get_offline_fails_on_a_missing_file(tmp_path):
    b = build.Build(out=tmp_path / "out", cache=tmp_path / "cache", fetch=None)
    with pytest.raises(FileNotFoundError):
        b.get("missing.nii", "https://example.org/missing.nii")


# ---------------------------------------------------------------- pairs


def write_layer(out, name, rows):
    (out / name).mkdir(parents=True)
    body = {"atlas": name, "rows": [{"index": 0, "name": "background"}, *rows]}
    (out / name / "labels.json").write_text(json.dumps(body))


@pytest.fixture
def layers_out(tmp_path):
    write_layer(tmp_path, "julich", [{"name": "CA1 (Hippocampus)", "area_id": "J_CA1", "label": 7}])
    write_layer(tmp_path, "cerebra", [{"name": "Brainstem", "area_id": "C_BS", "label": 11}])
    write_layer(tmp_path, "cit168", [])
    write_layer(tmp_path, "icbm_wm", [])
    return tmp_path


TERMS = {1021: {"abbreviation": "HF", "name": "Hippocampal formation"},
         47: {"abbreviation": "BS", "name": "Brainstem"}}  # fmt: skip


def test_pairs_carry_ids_and_names_only_and_no_grade(layers_out):
    proposed = [
        {"kind": "internal", "waxholm": 1021, "atlas": "julich", "human": ["CA1 (Hippocampus)"]},
        {"kind": "brainstem", "waxholm": 47, "atlas": "cerebra", "human": ["Brainstem"]},
    ]
    out = build.pairs(layers_out, TERMS, proposed)
    first = out["pairs"][0]
    assert first["waxholm"] == {"id": 1021, "acronym": "HF", "name": "Hippocampal formation"}
    assert first["human"] == [
        {"atlas": "julich", "area_id": "J_CA1", "label": 7, "name": "CA1 (Hippocampus)"}
    ]
    assert first["grade"] is None and first["note"] is None  # Sofía's, still pending
    assert out["grade_values"] == ["clear", "partial", "disputed"]
    # No geometry of either atlas in the pairs: they are our own data.
    text = json.dumps(out)
    assert "centroid" not in text and "voxels" not in text


def test_pairs_refuse_a_name_missing_from_its_layer(layers_out):
    bad = [{"kind": "x", "waxholm": 1021, "atlas": "cerebra", "human": ["CA1 (Hippocampus)"]}]
    with pytest.raises(ValueError, match="not in the atlas data"):
        build.pairs(layers_out, TERMS, bad)


def test_seed_pairs_file_is_well_formed():
    proposed = build.load_pairs()
    assert len(proposed) == 13  # the 12 of S3 and the zona incerta (v237)
    assert {p["atlas"] for p in proposed} <= {"julich", "cerebra", "cit168", "icbm_wm"}


def test_load_pairs_rejects_extra_fields(tmp_path):
    p = tmp_path / "pairs.toml"
    p.write_text('[[pair]]\nkind="a"\nwaxholm=1\natlas="julich"\nhuman=["x"]\ngrade="clear"\n')
    with pytest.raises(ValueError, match="malformed"):
        build.load_pairs(p)


# ---------------------------------------------------------------- manifest and licences


def test_manifest_budget_is_per_brain_initial_load(tmp_path):
    for folder, size in {"waxholm": 1000, "julich": 2_000_000, "cerebra": 1_500_000,
                         "nissl": 5_000_000}.items():  # fmt: skip
        (tmp_path / folder).mkdir()
        (tmp_path / folder / "f.bin").write_bytes(b"\0" * size)
    report = build.manifest(tmp_path, {"waxholm": {}, "julich": {}, "cerebra": {}, "nissl": {}})
    assert report["initial_load"]["rat"] == {"bytes": 1000, "within_budget": True}
    assert report["initial_load"]["human"] == {"bytes": 3_500_000, "within_budget": False}
    assert report["on_demand"] == {"nissl": 5_000_000}  # never counted in the initial load


def test_every_licence_names_its_licence_source_and_changes():
    for name, lic in LICENCES.items():
        for field in ("atlas", "short", "licence", "licence_url", "source_url", "derived"):
            assert lic.get(field), f"{name}: {field}"
        assert name == "julich" or lic["citation"]  # Julich-Brain's comes from siibra
        assert "mesh" not in lic["derived"].lower()  # mock-up B's meshes are gone
