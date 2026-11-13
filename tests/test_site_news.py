"""Neuro News on the website (plan, step 23). No network: a tiny warehouse with the columns
the site reads, written with DuckDB in ``tmp_path``. The rows are made up for the tests."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import duckdb
import pytest

from synaptica.narrative.write import text_path
from synaptica.site import news
from synaptica.site.build import SiteBuilder
from synaptica.site.check import check_site

LICENSED = {"hero": {"files": [], "author": "Sofía", "licence": "CC BY-SA 4.0"}}
AS_OF = dt.date(2026, 11, 9)


def study(sid: str, **kw) -> dict:
    row = {
        "study_id": sid, "doi": sid.removeprefix("doi:"), "pmid": None, "pmcid": None,
        "title": f"Title of {sid}", "journal": "Neuron", "published_on": AS_OF,
        "entered_on": AS_OF, "authors": ["A. One"], "sources": ["pubmed"],
        "review_status": "journal", "species": "animals", "integrity": "none",
        "integrity_notices": [], "license": "cc by", "publication_types": [],
        "news_type": None, "news_candidate": True, "is_neuro": True,
    }  # fmt: skip
    return row | kw


STUDIES = [
    study("doi:10.1/new"),
    study("doi:10.1/old", entered_on=AS_OF - dt.timedelta(days=10)),  # out of Latest
    study("doi:10.1/noise", news_type="noise"),
    study("doi:10.1/trial", publication_types=["Randomized Controlled Trial"],
          species="humans"),
    study("doi:10.1/pre", review_status="preprint", sources=["biorxiv"], license=None),
    study("doi:10.1/nsc", sources=["journals"], journal="Nature"),
    study("doi:10.1/ret", integrity="retracted", news_candidate=False,
          integrity_notices=["10.1/notice"]),
]  # fmt: skip
NEWS = [
    {"news_item_id": "news:a", "story_id": "news:a", "origin": "outlet", "feed": "sinc",
     "outlet": "SINC", "lang": "es", "url": "https://www.agenciasinc.es/a", "title": "Titular A",
     "published_at": dt.datetime(2026, 11, 8, 9), "entered_on": AS_OF, "is_neuro": True},
    {"news_item_id": "news:b", "story_id": "news:b", "origin": "outlet", "feed": "sinc",
     "outlet": "SINC", "lang": "es", "url": "https://www.agenciasinc.es/b", "title": "No neuro",
     "published_at": dt.datetime(2026, 11, 8, 9), "entered_on": AS_OF, "is_neuro": False},
]  # fmt: skip


def warehouse(data: Path, studies=STUDIES, items=NEWS) -> Path:
    data.mkdir(parents=True, exist_ok=True)
    path = data / "warehouse.duckdb"
    with duckdb.connect(str(path)) as con:
        con.execute("""create table dim_study (study_id varchar, doi varchar, pmid varchar,
            pmcid varchar, title varchar, journal varchar, published_on date, entered_on date,
            authors varchar[], sources varchar[], review_status varchar, species varchar,
            integrity varchar, integrity_notices varchar[], license varchar,
            publication_types varchar[], news_type varchar, news_candidate boolean,
            is_neuro boolean, figure_label varchar, figure_file varchar,
            figure_thumb varchar, figure_width integer, figure_height integer,
            figure_license varchar, figure_license_url varchar, figure_credit varchar,
            figure_source_url varchar, title_es varchar)""")
        con.execute("""create table fct_news_item (news_item_id varchar, story_id varchar,
            origin varchar, feed varchar, outlet varchar, lang varchar, url varchar,
            title varchar, published_at timestamp, entered_on date, is_neuro boolean)""")
        con.execute("create table news_feeds (feed varchar, license varchar)")
        con.execute("insert into news_feeds values ('sinc', 'CC BY 4.0')")
        for table, rows in (("dim_study", studies), ("fct_news_item", items)):
            for r in rows:
                cols = ", ".join(r)
                con.execute(f"insert into {table} ({cols}) values "
                            f"({', '.join('?' * len(r))})", list(r.values()))  # fmt: skip
    return data


def build(tmp_path: Path, data: Path | None) -> Path:
    out = tmp_path / "site"
    SiteBuilder(out, images=LICENSED, data_dir=data).build()
    return out


@pytest.fixture
def site(tmp_path: Path) -> Path:
    return build(tmp_path, warehouse(tmp_path / "data"))


def test_load_selects_each_block(tmp_path: Path) -> None:
    data = news.load(warehouse(tmp_path / "data") / "warehouse.duckdb")
    assert data is not None and data.as_of == AS_OF
    ids = [s["study_id"] for s in data.latest]
    assert "doi:10.1/old" not in ids and "doi:10.1/noise" not in ids  # 7 days; no noise
    assert "doi:10.1/nsc" not in ids and [s["study_id"] for s in data.nsc] == ["doi:10.1/nsc"]
    assert [[i["title"] for i in s] for s in data.stories] == [["Titular A"]]  # only neuro
    assert data.examples["retracted"]["study_id"] == "doi:10.1/ret"
    assert data.examples["preprint"]["study_id"] == "doi:10.1/pre"
    assert data.examples["corrected"] is None
    trial = next(s for s in data.latest if s["study_id"] == "doi:10.1/trial")
    assert trial["type"] == "clinical_trial"  # from PubMed, without the classifier


def test_no_warehouse_means_no_data() -> None:
    assert news.load(Path("/nonexistent/warehouse.duckdb")) is None


def test_site_with_studies_passes_the_check(site: Path) -> None:
    result = check_site(site)
    assert result.passed, result.problems
    for rel in ("es/noticias.html", "en/news.html", "es/semana.html", "en/week.html",
                "es/estudio/doi_10.1_new.html", "en/study/doi_10.1_ret.html"):  # fmt: skip
        assert (site / rel).exists(), rel
    assert not (site / "en/study/doi_10.1_old.html").exists()  # not shown → no page


def test_every_study_shows_its_three_signals(site: Path) -> None:
    page = (site / "en/study/doi_10.1_pre.html").read_text()
    for key in ("review", "subject", "integrity"):
        assert f'data-signal="{key}"' in page
    assert "Preprint · not peer reviewed" in page and "Animals" in page


def test_fallback_text_and_no_abstract(site: Path) -> None:
    page = (site / "es/estudio/doi_10.1_new.html").read_text()
    assert "Texto de respaldo" in page
    assert "Estudio en animales publicado en Neuron el 9 de noviembre de 2026." in page
    assert "Estudio original: CC BY." in page


def test_verified_summary_is_shown_when_the_judge_passed(tmp_path: Path) -> None:
    data = warehouse(tmp_path / "data")
    for lang, text in (("en", "Mice slept more."), ("es", "Los ratones durmieron más.")):
        path = text_path("doi:10.1/new", lang, verified=True, derived_root=data / "derived")
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "status": "verified",
            "sentences": [{"text": text, "fact_ids": ["f1"]}],
            "generator": "groq/qwen",
            "judge": {"passed": True, "generator": "groq/oss"},
        }
        path.write_text(json.dumps(record), encoding="utf-8")
    out = build(tmp_path, data)
    page = (out / "es/estudio/doi_10.1_new.html").read_text()
    assert "Los ratones durmieron más." in page and "Resumen verificado" in page
    assert "qwen (groq)" in page and "oss (groq)" in page
    home = (out / "en/index.html").read_text()
    assert "Mice slept more." in home  # the verified study is the featured one


def test_spanish_titles_are_marked_as_english_with_a_gap(site: Path) -> None:
    page = (site / "es/noticias.html").read_text()
    assert 'lang="en">Title of doi:10.1/new</a>' in page
    assert 'id="gap-title_es"' in page and 'id="gap-types"' in page
    assert 'id="gap-groups"' in page  # every story alone: grouping has not run
    assert 'id="gap-title_es"' not in (site / "en/news.html").read_text()


def test_home_shows_today(site: Path) -> None:
    home = (site / "es/index.html").read_text()
    # Three studies in Latest: the newest is featured, the other two are headlines.
    assert 'id="hoy"' in home and home.count('class="headline-card"') == 2


def test_method_examples_and_their_gap(site: Path) -> None:
    page = (site / "en/how-we-evaluate.html").read_text()
    assert 'data-study="doi:10.1/ret"' in page and 'data-study="doi:10.1/pre"' in page
    assert 'id="gap-example_corrected"' in page


def test_week_page_without_verified_text_shows_fallback_and_gap(site: Path) -> None:
    page = (site / "en/week.html").read_text()
    assert "2026-W45" in page and 'id="gap-week"' in page
    assert "Week of 2 November to 8 November 2026: no studies summarized." in page


def test_search_index_lists_every_study_page(site: Path) -> None:
    rows = json.loads((site / "es/buscar.json").read_text())
    urls = {r[3] for r in rows}
    for page in (site / "es/estudio").glob("*.html"):
        assert f"es/estudio/{page.name}" in urls
    assert "https://www.agenciasinc.es/a" in urls
    assert 'data-index="buscar.json"' in (site / "es/noticias.html").read_text()


def test_check_catches_a_study_missing_from_the_index(site: Path) -> None:
    rows = json.loads((site / "en/search.json").read_text())
    kept = [r for r in rows if r[3] != "en/study/doi_10.1_new.html"]
    kept.append(["Page", "Gone", "", "en/gone.html"])
    (site / "en/search.json").write_text(json.dumps(kept))
    problems = check_site(site).problems
    assert any("doi_10.1_new.html: not in en/search.json" in p for p in problems)
    assert any("en/gone.html does not exist" in p for p in problems)


def test_without_warehouse_the_news_pages_say_so(tmp_path: Path) -> None:
    out = build(tmp_path, tmp_path / "empty")
    assert check_site(out).passed
    page = (out / "en/news.html").read_text()
    assert 'id="gap-no_data"' in page and not (out / "en/study").exists()


def test_build_with_studies_is_idempotent(tmp_path: Path, site: Path) -> None:
    first = {p: p.read_bytes() for p in site.rglob("*") if p.is_file()}
    SiteBuilder(site, images=LICENSED, data_dir=tmp_path / "data").build()
    assert {p: p.read_bytes() for p in site.rglob("*") if p.is_file()} == first


def test_future_issue_date_does_not_jump_to_the_top(tmp_path: Path) -> None:
    rows = [
        study("doi:10.1/a", published_on=AS_OF - dt.timedelta(days=1)),
        study("doi:10.1/b", published_on=dt.date(2027, 2, 1)),  # print issue months ahead
        study("doi:10.1/c", published_on=AS_OF),
    ]
    data = news.load(warehouse(tmp_path / "data", rows) / "warehouse.duckdb")
    assert [s["study_id"] for s in data.latest] == ["doi:10.1/b", "doi:10.1/c", "doi:10.1/a"]


def test_biorxiv_no_reuse_licence_is_named(tmp_path: Path) -> None:
    t = {"lic_text_fallback": "T", "lic_meta": "M {src}", "lic_original": "O {lic}",
         "lic_original_none": "none", "lic_original_closed": "closed"}  # fmt: skip
    s = {"summary": {"en": {"kind": "fallback"}}, "sources": ["biorxiv"]}
    assert news.licence_lines(s | {"license": "cc_no"}, "en", t)[-1] == "closed"
    assert news.licence_lines(s | {"license": "cc0_ng"}, "en", t)[-1] == "O CC0"
    assert news.licence_lines(s | {"license": None}, "en", t)[-1] == "none"


def test_examples_are_neuroscience_only(tmp_path: Path) -> None:
    rows = [study("doi:10.1/gut", integrity="corrected", is_neuro=False, news_candidate=False)]
    data = news.load(warehouse(tmp_path / "data", rows) / "warehouse.duckdb")
    assert data.examples["corrected"] is None  # a gap, not a study the site never shows


def test_print_issue_date_is_shown_apart_not_as_the_day(tmp_path: Path) -> None:
    rows = [study("doi:10.1/glia", journal="Glia", published_on=dt.date(2027, 1, 1))]
    out = build(tmp_path, warehouse(tmp_path / "data", rows))
    card = (out / "es/noticias.html").read_text()
    assert "9 nov 2026" in card and "número de enero de 2027" in card and "1 ene 2027" not in card
    page = (out / "en/study/doi_10.1_glia.html").read_text()
    assert "Study in animals published in Glia in the January 2027 issue." in page
    assert "Print issue" in page and "January 2027" in page


def _verified(data: Path, sid: str, en: list[str], es: list[str]) -> None:
    for lang, lines in (("en", en), ("es", es)):
        path = text_path(sid, lang, verified=True, derived_root=data / "derived")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "status": "verified", "generator": "groq/qwen",
            "sentences": [{"text": t, "fact_ids": ["f1"]} for t in lines],
            "judge": {"passed": True, "generator": "groq/oss"},
        }), encoding="utf-8")  # fmt: skip


def test_the_fact_of_the_day_is_a_verified_sentence_with_its_source(tmp_path: Path) -> None:
    data = warehouse(tmp_path / "data")
    home = (build(tmp_path, data) / "es/index.html").read_text()
    assert "Dato del día" not in home  # no verified summary: no fact
    _verified(data, "doi:10.1/new", ["Lead one.", "Lead two."], ["Uno.", "Dos."])
    home = (build(tmp_path / "a", data) / "es/index.html").read_text()
    assert "Dato del día" not in home  # the only verified study is the lead
    _verified(
        data,
        "doi:10.1/trial",
        ["It was tested.", "Seizures fell by 30%."],
        ["Se probó.", "Las crisis bajaron un 30 %."],
    )
    out = build(tmp_path / "b", data)
    es, en = (out / "es/index.html").read_text(), (out / "en/index.html").read_text()
    # The newest verified study (by id on the same day: trial) leads; the other gives
    # the fact, its second sentence, with its source linked.
    assert '<p class="fact-text">Dos.</p>' in es and '<p class="fact-text">Lead two.</p>' in en
    assert 'href="estudio/doi_10.1_new.html">Neuron</a>' in es


# -- figures (step 23b) -------------------------------------------------------------------

FIGURE = {"figure_label": "Figure 1.", "figure_file": "pmc1.webp", "figure_thumb": "pmc1-t.webp",
          "figure_width": 760, "figure_height": 380, "figure_license": "CC BY 4.0",
          "figure_license_url": "https://creativecommons.org/licenses/by/4.0/",
          "figure_credit": "Ramón et al.",
          "figure_source_url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC1/"}  # fmt: skip


def with_figure(tmp_path: Path, cached: bool = True) -> Path:
    data = warehouse(
        tmp_path / "data", studies=[study("doi:10.1/new", pmcid="PMC1", **FIGURE), *STUDIES[1:]]
    )
    if cached:
        (data / "cache" / "figures").mkdir(parents=True)
        for name in ("pmc1.webp", "pmc1-t.webp"):
            (data / "cache" / "figures" / name).write_bytes(b"RIFF....WEBP")
    return build(tmp_path, data)


def test_figure_is_self_hosted_with_credit_and_passes_the_check(tmp_path: Path) -> None:
    out = with_figure(tmp_path)
    assert check_site(out).passed, check_site(out).problems
    assert (out / "static" / "fig" / "pmc1.webp").exists()
    assert (out / "static" / "fig" / "pmc1-t.webp").exists()
    news_es = (out / "es" / "noticias.html").read_text(encoding="utf-8")
    assert 'src="../static/fig/pmc1-t.webp"' in news_es
    assert 'Ramón et al. <span class="credit-lic">CC BY 4.0</span>' in news_es
    pages = [p.read_text(encoding="utf-8") for p in (out / "es" / "estudio").glob("*.html")]
    page_es = next(p for p in pages if "fig/pmc1.webp" in p)
    assert "Figura 1 · Ramón et al." in page_es and "vía PMC" in page_es
    assert 'href="https://creativecommons.org/licenses/by/4.0/"' in page_es
    assert "Redimensionada y convertida a WebP" in page_es  # in the licences block
    page_en = next(p.read_text(encoding="utf-8") for p in (out / "en" / "study").glob("*.html")
                   if "fig/pmc1.webp" in p.read_text(encoding="utf-8"))  # fmt: skip
    assert "Figure 1 · Ramón et al." in page_en and "via PMC" in page_en


def test_figure_missing_from_the_cache_is_not_shown(tmp_path: Path) -> None:
    out = with_figure(tmp_path, cached=False)
    assert check_site(out).passed
    assert not (out / "static" / "fig").exists()
    assert "Ramón et al." not in (out / "es" / "noticias.html").read_text(encoding="utf-8")


def test_nature_science_cell_never_show_a_figure(tmp_path: Path) -> None:
    nsc = study("doi:10.1/nsc", sources=["journals"], journal="Nature", pmcid="PMC1", **FIGURE)
    data = warehouse(tmp_path / "data", studies=[nsc])
    (data / "cache" / "figures").mkdir(parents=True)
    for name in ("pmc1.webp", "pmc1-t.webp"):
        (data / "cache" / "figures" / name).write_bytes(b"x")
    out = build(tmp_path, data)  # even if a figure row reached it, it is not used
    assert not (out / "static" / "fig").exists()


def test_spanish_title_shown_in_spanish_with_its_original(tmp_path: Path) -> None:
    translated = [study(s["study_id"], **{**s, "title_es": f"Título de {s['study_id']}"})
                  for s in STUDIES]  # fmt: skip
    out = build(tmp_path, warehouse(tmp_path / "data", studies=translated))
    assert check_site(out).passed, check_site(out).problems
    news_es = (out / "es" / "noticias.html").read_text(encoding="utf-8")
    assert 'lang="es">Título de doi:10.1/new</a>' in news_es
    assert 'id="gap-title_es"' not in news_es  # every title shown is translated
    page = next(p.read_text(encoding="utf-8") for p in (out / "es" / "estudio").glob("*.html")
                if "Título de doi:10.1/new<" in p.read_text(encoding="utf-8"))  # fmt: skip
    assert '<h1 class="study-title" lang="es">Título de doi:10.1/new</h1>' in page
    assert '<span lang="en">Title of doi:10.1/new</span>' in page  # the original, in sight
    news_en = (out / "en" / "news.html").read_text(encoding="utf-8")
    assert "Título de" not in news_en and 'lang="en">Title of doi:10.1/new</a>' in news_en
    index = json.loads((out / "es" / "buscar.json").read_text(encoding="utf-8"))
    entry = next(e for e in index if e[1] == "Título de doi:10.1/new")
    assert "Title of doi:10.1/new" in entry[2]  # found by the English title too


def test_untranslated_title_keeps_the_original_and_the_gap(tmp_path: Path) -> None:
    some = [study("doi:10.1/new", title_es="Título nuevo"), *STUDIES[1:]]
    out = build(tmp_path, warehouse(tmp_path / "data", studies=some))
    news_es = (out / "es" / "noticias.html").read_text(encoding="utf-8")
    assert 'lang="es">Título nuevo</a>' in news_es
    assert 'lang="en">Title of doi:10.1/trial</a>' in news_es and 'id="gap-title_es"' in news_es
