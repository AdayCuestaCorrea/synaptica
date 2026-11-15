"""Glossary texts: their checks against the Wikipedia leads and her review items. Uses the
committed ``sources.json`` (written by ``syn glossary sources``): no network."""

from dataclasses import replace

import pytest

from synaptica.glossary import load_terms
from synaptica.glossary.sources import load_sources
from synaptica.glossary.texts import load_texts, problems, queue_item
from synaptica.review.models import ItemType

TERMS = {t.term_id: t for t in load_terms()}
TEXTS = load_texts()
SOURCES = load_sources()


def edited(term_id, lang, definition):
    text = TEXTS[term_id]
    return replace(text, definition={**text.definition, lang: definition})


def test_every_term_has_both_languages_and_its_origin():
    assert set(TEXTS) == set(TERMS)
    for t in TERMS.values():
        es_from = TEXTS[t.term_id].origin["es"]
        assert (
            es_from == "docs/propuesta.md"
            if t.origin == "proposal"
            else es_from.startswith("issue#")
        )
        assert TEXTS[t.term_id].origin["en"].startswith("llm-draft:")


@pytest.mark.parametrize("term_id", sorted(TERMS))
def test_the_committed_texts_pass_their_checks(term_id):
    assert problems(TERMS[term_id], TEXTS[term_id], SOURCES[term_id]) == []


def test_a_copied_run_of_eight_words_fails():
    lead = SOURCES["da"]["en"]["lead"]  # «… is a neuromodulatory molecule that plays several …»
    copied = " ".join(lead.split()[10:22])
    found = problems(TERMS["da"], edited("da", "en", copied), SOURCES["da"])
    assert any("Copia 8 palabras" in p for p in found), found


def test_an_invented_number_or_name_fails():
    found = problems(TERMS["da"], edited("da", "en", "Found in 1957 by Smithers."), SOURCES["da"])
    assert any("La cifra 1957" in p for p in found)
    assert any("«Smithers»" in p for p in found)


def test_a_term_without_any_source_fails_and_gets_no_item():
    none = {"en": {"title": None, "accepted": False}, "es": {"title": None, "accepted": False}}
    assert problems(TERMS["da"], TEXTS["da"], none) == [
        "(inglés) Sin fuente de Wikipedia aceptada.", "(español) Sin fuente de Wikipedia aceptada.",
    ]  # fmt: skip
    assert queue_item(TERMS["da"], TEXTS["da"], none) is None


def test_item_cites_its_language_or_english_without_spanish_article():
    """SNr has no Spanish article: its Spanish text cites the English lead (option a)."""
    da = queue_item(TERMS["da"], TEXTS["da"], SOURCES["da"])
    assert da.item_type is ItemType.GLOSSARY and da.item_id == "da" and da.title_es == "DA"
    assert da.content.es[0].cites == ["wikipedia-es-da"]
    assert da.content.en[0].cites == ["wikipedia-en-da"]
    assert da.content.es[0].text.startswith("DA (Dopamina): ")
    snr = queue_item(TERMS["snr"], TEXTS["snr"], SOURCES["snr"])
    assert snr.content.es[0].cites == snr.content.en[0].cites == ["wikipedia-en-snr"]
    assert [s.id for s in snr.content.sources] == ["wikipedia-en-snr"]
    assert "oldid=" in snr.content.sources[0].url


def test_bad_texts_file_fails(tmp_path):
    from synaptica.glossary.texts import TEXTS as PATH

    rows = PATH.read_text("utf-8").splitlines()
    rows[1] = rows[1].replace("llm-draft:claude-opus-5-5:2026-11-15", "somebody")
    path = tmp_path / "t.csv"
    path.write_text("\n".join(rows) + "\n", "utf-8")
    with pytest.raises(ValueError, match="unknown origin"):
        load_texts(path)
