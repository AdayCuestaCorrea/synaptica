"""The Neuro Atlas page (src/synaptica/site/atlas.py, site/templates/atlas.html.j2). No network:
tiny label tables for the lists, and the committed site/static/atlas/ for the full build."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from synaptica.site import atlas
from synaptica.site.build import SiteBuilder
from synaptica.site.check import check_site

LICENSED = {"hero": {"files": [], "author": "Sofía", "licence": "CC BY-SA 4.0"}}


def write(root: Path, name: str, rows: list[dict]) -> None:
    (root / name).mkdir(parents=True)
    body = {"rows": [{"index": 0, "name": "background"}, *rows]}
    (root / name / "labels.json").write_text(json.dumps(body))
    lic = {"short": name.title(), "licence": "CC BY 4.0", "source_url": "https://example.org",
           "licence_url": "https://creativecommons.org/licenses/by/4.0/"}  # fmt: skip
    (root / name / "licence.json").write_text(json.dumps(lic))


def row(name: str, side: str, group: str, acronym: str | None = None) -> dict:
    return {"name": name, "side": side, "group": group, "acronym": acronym, "color_calm": "#aabbcc",
            "id": len(name), "area_id": name.upper()}  # fmt: skip


@pytest.fixture
def atlas_dir(tmp_path: Path) -> Path:
    write(tmp_path, "waxholm", [
        row("Cornu ammonis 1", "L", "hippocampus", "CA1"),
        row("Cornu ammonis 1", "R", "hippocampus", "CA1"),
        row("Primary motor area", "L", "cortex", "M1"),
    ])  # fmt: skip
    write(tmp_path, "julich", [row("CA1 (Hippocampus)", "L", "hippocampus")])
    write(tmp_path, "cerebra", [row("Brainstem", "L", "hindbrain")])
    write(tmp_path, "cit168", [])
    write(tmp_path, "icbm_wm", [])
    return tmp_path


def test_regions_join_both_sides_and_go_from_the_surface_inwards(atlas_dir: Path) -> None:
    fams = atlas.regions(atlas_dir, "rat")
    assert [f["family"] for f in fams] == ["cortex", "hippocampus"]
    assert [f["depth"] for f in fams] == ["surface", "interior"]
    assert fams[1]["regions"] == [
        {
            "name": "Cornu ammonis 1",
            "acronym": "CA1",
            "atlas": "waxholm",
            "colour": "#aabbcc",
            "key": "w15",
        }
    ]


def test_human_regions_keep_the_layer_they_come_from(atlas_dir: Path) -> None:
    found = {r["name"]: r["atlas"] for f in atlas.regions(atlas_dir, "human") for r in f["regions"]}
    assert found == {"CA1 (Hippocampus)": "julich", "Brainstem": "cerebra"}
    assert [c["atlas"] for c in atlas.credits(atlas_dir, "human")] == list(atlas.BRAINS["human"])


def test_a_family_without_a_place_is_refused(atlas_dir: Path) -> None:
    write(atlas_dir / "x", "waxholm", [row("Mystery", "L", "new_family")])
    with pytest.raises(ValueError, match="new_family"):
        atlas.regions(atlas_dir / "x", "rat")


def test_every_family_of_the_palette_has_a_place() -> None:
    palette = pytest.importorskip("synaptica.atlas.palette")
    assert set(palette.FAMILIES) == set(atlas.FAMILIES)


def test_the_page_lists_both_brains_with_their_credits(tmp_path: Path) -> None:
    out = tmp_path / "site"
    SiteBuilder(out, images=LICENSED).build()
    assert check_site(out).passed
    page = (out / "es" / "atlas.html").read_text("utf-8")
    for credit in ("Waxholm v4.01", "Julich-Brain v3.1", "CC BY 4.0", "CC BY-NC-SA 4.0"):
        assert credit in page
    assert 'id="rat"' in page and 'id="human"' in page
    assert page.count("<li data-key=") > 400  # every region of both brains, sides joined
    assert (out / "en" / "atlas.html").exists()
    # The viewer's data travel with the site, each atlas with its licence.
    for folder in ("waxholm", "julich", "cerebra", "cit168", "icbm_wm", "bigbrain", "nissl"):
        assert (out / "static" / "atlas" / folder / "licence.json").exists()
    # The viewer and Niivue (with its licence) are served by the site itself: no other domain.
    assert (out / "static" / "viewer" / "viewer.js").exists()
    assert (out / "static" / "vendor" / "niivue-0.69.0" / "LICENSE").exists()
    assert 'data-niivue="../static/vendor/niivue-0.69.0/niivue.umd.js' in page
    assert 'data-atlas-viewer="../static/atlas"' in page


def test_the_home_card_opens_the_atlas_page(tmp_path: Path) -> None:
    out = tmp_path / "site"
    SiteBuilder(out, images=LICENSED).build()
    home = (out / "es" / "index.html").read_text("utf-8")
    assert 'class="card card--atlas" href="atlas.html"' in home


# ---------------------------------------------------------------- region pages (step 5)

ATLAS = Path(__file__).parents[1] / "site" / "static" / "atlas"


def test_slug_is_plain_ascii() -> None:
    assert (
        atlas.slug("Subc (Hippocampus, Subicular complex)") == "subc-hippocampus-subicular-complex"
    )
    assert atlas.slug("Área 4a") == "area-4a"


def test_region_pages_cover_both_sides_of_every_pair() -> None:
    pages = atlas.region_pages(ATLAS)
    by_page = {r["page"]: r for r in pages}
    assert len(by_page) == len(pages)  # one page per region
    pairs = json.loads((ATLAS / "pairs.json").read_text("utf-8"))["pairs"]
    assert sum(r["brain"] == "rat" for r in pages) == len(pairs)
    assert sum(r["brain"] == "human" for r in pages) == sum(len(p["human"]) for p in pairs)
    for r in pages:
        assert r["page"].startswith(r["atlas"] + "-")  # a rat and a human page never clash
        for p in r["pairs"]:
            for other in p["counterparts"]:  # links go both ways, across brains only
                assert by_page[other]["brain"] != r["brain"]
                assert any(r["page"] in q["counterparts"] for q in by_page[other]["pairs"])
            assert p["grade"] is None  # Sofía's, still pending


def test_region_pages_are_built_linked_and_mark_their_gaps(tmp_path: Path) -> None:
    out = tmp_path / "site"
    SiteBuilder(out, images=LICENSED).build()
    assert check_site(out).passed  # also: every region page is linked from another page
    page = (out / "es" / "atlas" / "regiones" / "waxholm-hippocampal-formation.html").read_text()
    assert "julich-ca1-hippocampus.html" in page and "#w1021" in page
    assert "Waxholm v4.01" in page and "CC BY 4.0" in page
    for gap in ("gap-region_text", "gap-region_studies", "gap-region_diseases", "gap-pair_grade"):
        assert gap in page
    assert (out / "en" / "atlas" / "regions" / "julich-ca1-hippocampus.html").exists()
    atlas_page = (out / "es" / "atlas.html").read_text()
    assert "regiones/waxholm-hippocampal-formation.html" in atlas_page  # the pairs section
