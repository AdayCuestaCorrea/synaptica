"""Study figures from PMC's open-access bucket (plan, step 23b), without network.

The bucket answers come from ``tests/fixtures/pmc/``: the real JSON and listing of two
articles and their XML trimmed to authors, licence and figures (captions removed, they are
paragraphs of the article). The image files are made up here with Pillow: plain colour
blocks of a chosen size, enough to test resizing and the choice of Figure 1."""

from __future__ import annotations

import datetime as dt
import io
import json
import re
from pathlib import Path

import httpx
import pytest
from PIL import Image

from synaptica import figures
from synaptica.config import project_root
from synaptica.http import Throttle, make_client

FIX = project_root() / "tests" / "fixtures" / "pmc"
TODAY = dt.date(2026, 11, 13)
NO_WAIT = Throttle(1000, sleep=lambda _: None)
CC_BY = "PMC13733655"  # CC BY 4.0; Figure 1 is g002 (the bucket lists g001 first)
NC_ND = "PMC13742447"  # CC BY-NC-ND 4.0; Figure 1 is gr1


def png(width: int, height: int, mode: str = "RGB") -> bytes:
    buf = io.BytesIO()
    colour = (0, 128, 128, 100) if mode == "RGBA" else "teal"  # see-through when RGBA
    Image.new(mode, (width, height), colour).save(buf, "PNG")
    return buf.getvalue()


class FakeBucket:
    """Serves the fixtures; ``images`` maps a file stem to its bytes (big ones by
    default). ``meta`` overrides fields of the article JSON; ``missing`` PMCIDs list
    nothing, as for an article not yet in the open-access subset."""

    def __init__(self, images=None, meta=None, missing=(), fail=()):
        self.images = images or {}
        self.meta = meta or {}
        self.missing = set(missing)
        self.fail = set(fail)
        self.calls: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.lstrip("/")
        self.calls.append(path or "list:" + request.url.params["prefix"])
        if not path:
            pmcid = request.url.params["prefix"].rstrip(".")
            if pmcid in self.missing:
                return httpx.Response(200, text="<ListBucketResult></ListBucketResult>")
            return httpx.Response(200, text=(FIX / f"{pmcid}-list.xml").read_text())
        folder, name = path.split("/", 1)
        pmcid = folder.split(".")[0]
        if name in self.fail:
            return httpx.Response(404, text="NoSuchKey")
        if name.endswith(".json"):
            meta = json.loads((FIX / f"{pmcid}.json").read_text()) | self.meta.get(pmcid, {})
            return httpx.Response(200, json=meta)
        if name.endswith(".xml"):
            return httpx.Response(200, text=(FIX / f"{pmcid}.xml").read_text())
        stem = Path(name).stem
        return httpx.Response(200, content=self.images.get(stem, png(1200, 900)))


def study(pmcid: str, sid: str | None = None, **kw) -> dict:
    return {"study_id": sid or f"10.1/{pmcid.lower()}", "pmcid": pmcid,
            "authors": ["Fallback A"]} | kw  # fmt: skip


def run(tmp_path: Path, fake: FakeBucket, studies, today=TODAY) -> figures.Result:
    with make_client(transport=httpx.MockTransport(fake)) as client:
        return figures.run(client, studies, derived_root=tmp_path / "derived",
                           cache_root=tmp_path / "cache", today=today,
                           throttle=NO_WAIT)  # fmt: skip


def rows(tmp_path: Path) -> dict[str, dict]:
    return figures.load_rows(figures.figures_path(tmp_path / "derived"))


def test_figure_1_is_chosen_by_the_article_not_by_the_bucket_order(tmp_path):
    fake = FakeBucket()
    result = run(tmp_path, fake, [study(CC_BY)])
    assert (result.found, result.without, result.failed) == (1, 0, 0)
    row = rows(tmp_path)["10.1/pmc13733655"]
    assert row["label"] == "FIGURE 1"
    assert row["source_key"] == "PMC13733655.1/DEO2-7-e70460-g002.webp"
    assert "PMC13733655.1/DEO2-7-e70460-g001.webp" not in fake.calls


def test_row_carries_licence_with_version_author_and_source(tmp_path):
    run(tmp_path, FakeBucket(), [study(CC_BY), study(NC_ND)])
    by, nd = rows(tmp_path)["10.1/pmc13733655"], rows(tmp_path)["10.1/pmc13742447"]
    assert by["license"] == "CC BY 4.0"
    assert by["license_url"] == "https://creativecommons.org/licenses/by/4.0/"
    assert by["credit"] == "Fujinaga et al."
    assert by["source_url"] == "https://pmc.ncbi.nlm.nih.gov/articles/PMC13733655/"
    assert by["citation"].startswith("DEN Open. 2026")
    assert nd["license"] == "CC BY-NC-ND 4.0" and nd["credit"] == "Demchenko et al."
    assert "caption" not in by  # a paragraph of the article: never stored


def test_webp_is_resized_never_cropped_with_a_thumbnail(tmp_path):
    run(tmp_path, FakeBucket(images={"DEO2-7-e70460-g002": png(1600, 400)}), [study(CC_BY)])
    row = rows(tmp_path)["10.1/pmc13733655"]
    full = Image.open(tmp_path / "cache" / "figures" / row["file"])
    thumb = Image.open(tmp_path / "cache" / "figures" / row["thumb"])
    assert full.format == thumb.format == "WEBP"
    assert full.size == (760, 190) == (row["width"], row["height"])  # same 4:1 proportions
    assert thumb.size == (240, 60)


def test_small_image_is_never_enlarged(tmp_path):
    run(tmp_path, FakeBucket(images={"DEO2-7-e70460-g002": png(500, 400)}), [study(CC_BY)])
    assert rows(tmp_path)["10.1/pmc13733655"]["width"] == 500


def test_icon_sized_figure_1_falls_to_figure_2(tmp_path):
    run(tmp_path, FakeBucket(images={"DEO2-7-e70460-g002": png(120, 80)}), [study(CC_BY)])
    row = rows(tmp_path)["10.1/pmc13733655"]
    assert row["label"] == "FIGURE 2" and row["source_key"].endswith("g001.webp")


def test_transparent_figure_keeps_its_alpha(tmp_path):
    fake = FakeBucket(images={"DEO2-7-e70460-g002": png(800, 600, "RGBA")})
    run(tmp_path, fake, [study(CC_BY)])
    row = rows(tmp_path)["10.1/pmc13733655"]
    assert Image.open(tmp_path / "cache" / "figures" / row["file"]).mode == "RGBA"


@pytest.mark.parametrize(("meta", "reason"), [
    ({"license_code": None}, "no_cc_licence"),
    ({"license_code": "NO-CC CODE"}, "no_cc_licence"),
    ({"is_pmc_openaccess": False}, "not_open_access"),
])  # fmt: skip
def test_without_a_cc_licence_there_is_no_figure(tmp_path, meta, reason):
    fake = FakeBucket(meta={CC_BY: meta})
    result = run(tmp_path, fake, [study(CC_BY)])
    row = rows(tmp_path)["10.1/pmc13733655"]
    assert (result.found, result.without) == (0, 1)
    assert row["status"] == "none" and row["reason"] == reason
    assert not any(c.endswith(".webp") for c in fake.calls)  # no image downloaded
    assert not (tmp_path / "cache" / "figures").exists()


def test_unreadable_image_gives_no_figure(tmp_path):
    fake = FakeBucket(images={s: b"not an image" for s in
                              ("DEO2-7-e70460-g002", "DEO2-7-e70460-g001",
                               "DEO2-7-e70460-g004")})  # fmt: skip
    run(tmp_path, fake, [study(CC_BY)])
    assert rows(tmp_path)["10.1/pmc13733655"]["reason"] == "unreadable_image"


def test_licence_without_version_keeps_the_bucket_code():
    meta = {"is_pmc_openaccess": True, "license_code": "CC BY"}
    assert figures.licence(meta, "<article/>") == ("CC BY", None)
    # A URL of another licence never lends its version.
    other = '<license xlink:href="https://creativecommons.org/licenses/by-nc/4.0/"/>'
    assert figures.licence(meta, other) == ("CC BY", None)
    zero = {"is_pmc_openaccess": True, "license_code": "CC0"}
    url = "https://creativecommons.org/publicdomain/zero/1.0/"
    assert figures.licence(zero, f'<x href="{url}"/>') == ("CC0 1.0", url)


def test_credit_forms_and_fallback():
    one = '<contrib contrib-type="author"><name><surname>Ramón</surname></name></contrib>'
    two = one + '<contrib contrib-type="author"><name><surname>Cajal</surname></name></contrib>'
    group = '<contrib contrib-type="author"><collab>The BRAIN Group</collab></contrib>'
    assert figures.credit(one) == "Ramón"
    assert figures.credit(two) == "Ramón, Cajal"
    assert figures.credit(group) == "The BRAIN Group"
    assert figures.credit("<article/>", ["Smith J", "Jones K", "Li W"]) == "Smith J et al."
    with pytest.raises(figures.NoFigure, match="no_author"):
        figures.credit("<article/>", [])


def test_supplementary_figures_are_not_figure_1():
    xml = ('<fig><label>Figure S1</label><graphic xlink:href="s1.jpg"/></fig>'
           '<fig><label>Figure 1</label><graphic xlink:href="f1.jpg"/></fig>')  # fmt: skip
    assert figures.figure_candidates(xml) == [("Figure 1", "f1")]


def test_links_in_the_caption_are_not_the_figure():
    # Found on the first real run (PMC13749619): a link in Figure 1's caption came first.
    xml = ('<fig><label>Figure 1</label><caption><p>See <ext-link xlink:href="iwc7elm"/>'
           '</p></caption><graphic xlink:href="g006.webp"/></fig>')  # fmt: skip
    assert figures.figure_candidates(xml) == [("Figure 1", "g006")]


def test_second_run_asks_nothing(tmp_path):
    run(tmp_path, FakeBucket(), [study(CC_BY), study(NC_ND)])
    before = figures.figures_path(tmp_path / "derived").read_bytes()
    fake = FakeBucket()
    result = run(tmp_path, fake, [study(CC_BY), study(NC_ND)])
    assert fake.calls == [] and result.up_to_date == 2
    assert figures.figures_path(tmp_path / "derived").read_bytes() == before


def test_lost_cache_is_fetched_again_with_the_stored_key(tmp_path):
    run(tmp_path, FakeBucket(), [study(CC_BY)])
    for f in (tmp_path / "cache" / "figures").iterdir():
        f.unlink()
    fake = FakeBucket()
    result = run(tmp_path, fake, [study(CC_BY)])
    assert result.refetched == 1
    assert fake.calls == ["PMC13733655.1/DEO2-7-e70460-g002.webp"]  # no listing, no XML
    assert len(list((tmp_path / "cache" / "figures").iterdir())) == 2


def test_not_in_bucket_is_asked_again_the_next_day_only(tmp_path):
    run(tmp_path, FakeBucket(missing={CC_BY}), [study(CC_BY)])
    assert rows(tmp_path)["10.1/pmc13733655"]["reason"] == "not_in_bucket"
    same_day = FakeBucket()
    assert run(tmp_path, same_day, [study(CC_BY)]).up_to_date == 1 and not same_day.calls
    result = run(tmp_path, FakeBucket(), [study(CC_BY)], today=TODAY + dt.timedelta(days=1))
    assert result.found == 1 and rows(tmp_path)["10.1/pmc13733655"]["status"] == "ok"


def test_final_reasons_are_not_asked_again(tmp_path):
    run(tmp_path, FakeBucket(meta={CC_BY: {"license_code": None}}), [study(CC_BY)])
    fake = FakeBucket()
    run(tmp_path, fake, [study(CC_BY)], today=TODAY + dt.timedelta(days=3))
    assert fake.calls == []


def test_network_error_leaves_no_row_and_is_retried(tmp_path):
    fake = FakeBucket(fail={"PMC13733655.1.json"})
    result = run(tmp_path, fake, [study(CC_BY)])
    assert result.failed == 1 and rows(tmp_path) == {}


def test_files_of_studies_no_longer_shown_are_removed(tmp_path):
    run(tmp_path, FakeBucket(), [study(CC_BY), study(NC_ND)])
    result = run(tmp_path, FakeBucket(), [study(NC_ND)])
    names = sorted(f.name for f in (tmp_path / "cache" / "figures").iterdir())
    assert result.removed == 2 and names == ["pmc13742447-t.webp", "pmc13742447.webp"]
    assert "10.1/pmc13733655" in rows(tmp_path)  # its metadata stays: not asked again


def test_a_new_pmcid_for_the_study_is_asked_again(tmp_path):
    run(tmp_path, FakeBucket(), [study(CC_BY, sid="10.1/x")])
    fake = FakeBucket()
    run(tmp_path, fake, [study(NC_ND, sid="10.1/x")])
    assert rows(tmp_path)["10.1/x"]["pmcid"] == NC_ND and fake.calls


def test_newest_version_folder_in_numeric_order():
    keys = {f"PMC1.{v}/PMC1.{v}.json": 1 for v in (1, 2, 9, 10)}
    assert figures._latest_version(keys, "PMC1") == "PMC1.10"
    assert figures._latest_version({}, "PMC1") is None


def test_fixtures_keep_no_caption_text():
    for xml in FIX.glob("*.xml"):
        for cap in re.findall(r"<caption>(.*?)</caption>", xml.read_text(), re.S):
            assert cap == "<p>(caption removed)</p>"


def test_command_needs_the_warehouse(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from synaptica.cli import app

    monkeypatch.setenv("SYN_DATA_DIR", str(tmp_path))
    result = CliRunner().invoke(app, ["figures"])
    assert result.exit_code == 1 and "syn build" in result.output


def test_only_latest_studies_with_a_pmcid_are_asked(tmp_path):
    from test_site_news import study as site_study
    from test_site_news import warehouse

    rows_in = [site_study("doi:10.1/a", pmcid="PMC1"), site_study("doi:10.1/b"),
               site_study("doi:10.1/nsc", sources=["journals"], pmcid="PMC2"),
               site_study("doi:10.1/noise", news_type="noise", pmcid="PMC3")]  # fmt: skip
    path = warehouse(tmp_path, studies=rows_in) / "warehouse.duckdb"
    assert [s["pmcid"] for s in figures.studies_to_show(path)] == ["PMC1"]
