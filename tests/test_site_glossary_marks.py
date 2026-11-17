"""C2 (sheet row 36, v203): published glossary terms marked in a study page's summary and
the featured excerpt, without changing the stored text. No network: her decisions are
written in ``tmp_path`` against the committed terms and texts."""

from __future__ import annotations

from pathlib import Path

import pytest

from synaptica.glossary.texts import published
from synaptica.site.build import SiteBuilder
from synaptica.site.check import check_site
from synaptica.site.glossary import Glossary
from test_site_glossary import LICENSED, decide


@pytest.fixture
def gl(tmp_path: Path) -> Glossary:
    decide(tmp_path, ("da", "approve", {}), ("ad", "approve", {}), ("vta", "approve", {}))
    return Glossary(published(tmp_path / "review"), "en")


def test_first_appearance_only_and_the_text_unchanged(gl: Glossary) -> None:
    used: set[str] = set()
    text = "VTA neurons <fire> & the VTA again"
    out = gl.mark_text(text, used, "glossary.html")
    assert out.count('data-gl="vta"') == 1 and "&lt;fire&gt; &amp;" in out
    assert used == {"vta"}
    # Same page, next sentence: already marked.
    assert "data-gl" not in gl.mark_text("The VTA projects.", used, "glossary.html")


def test_two_letter_acronyms_need_their_full_name_nearby(gl: Glossary) -> None:
    alone = gl.mark_text("Patients born in 1950 AD were scanned.", set(), "g.html")
    assert "data-gl" not in alone
    named = gl.mark_text("AD was studied.", set(), "g.html",
                         context="AD was studied. Alzheimer's disease starts early.")  # fmt: skip
    assert 'data-gl="ad"' in named
    # Exact case: never a lowercase word that spells an acronym.
    assert "data-gl" not in gl.mark_text("a da capo ending", set(), "g.html")
    assert 'data-gl="da"' in gl.mark_text("Dopamine (DA) release", set(), "g.html")


def test_a_term_without_its_english_is_not_marked_on_english_pages(tmp_path: Path) -> None:
    mine = "DA (Dopamina): Neurotransmisor del movimiento y la recompensa."
    decide(tmp_path, ("da", "edit", {"es": mine}))
    entries = published(tmp_path / "review")
    en, es = Glossary(entries, "en"), Glossary(entries, "es")
    assert "data-gl" not in en.mark_text("Dopamine (DA) release", set(), "g.html")
    assert 'data-gl="da"' in es.mark_text("Liberación de dopamina (DA)", set(), "g.html")


def test_study_page_and_featured_excerpt_mark_terms(tmp_path: Path) -> None:
    from test_site_news import STUDIES, warehouse

    data = warehouse(tmp_path / "data", studies=STUDIES)
    decide(data, ("vta", "approve", {}), ("da", "approve", {}))
    out = tmp_path / "site"
    builder = SiteBuilder(out, images=LICENSED, data_dir=data)
    lead = builder.news_data.lead
    sm = lead["summary"]["en"]
    if sm["kind"] == "verified":
        sm["sentences"][0]["text"] = "Dopamine (DA) neurons of the VTA fire in bursts."
    else:
        sm["text"] = "Dopamine (DA) neurons of the VTA fire in bursts."
    builder.build()
    assert check_site(out).passed
    home = (out / "en" / "index.html").read_text()
    assert 'data-gl="vta"' in home and 'href="glossary.html#vta"' in home
    study = (out / "en" / "study" / f"{lead['slug']}.html").read_text()
    assert 'href="../glossary.html#da"' in study and study.count('data-gl="vta"') == 1
