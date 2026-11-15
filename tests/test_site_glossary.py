"""Neuro Glossary on the site: only what Sofía approved, both languages, the gap for an
English still to be written, cross-links between definitions. No network: decisions are
written in ``tmp_path`` against the committed terms, texts and Wikipedia sources."""

from __future__ import annotations

import json
from pathlib import Path

from synaptica.glossary.texts import published, review_items
from synaptica.site.build import SiteBuilder
from synaptica.site.check import check_site

LICENSED = {"hero": {"files": [], "author": "Sofía", "licence": "CC BY-SA 4.0"}}
ITEMS = {i.item_id: i for i in review_items()}
KINDS = ("home", "method", "sources", "status", "about", "glossary")  # the fixed pages they link


def decide(data: Path, *rows: tuple[str, str, dict], sha: str | None = None) -> None:
    """Her decisions on glossary terms, as the intake records them."""
    review = data / "review"
    review.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps({
        "item_type": "glossary", "item_id": k, "content_sha256": sha or ITEMS[k].content_sha256,
        "action": action, "payload": payload, "note": None, "reviewed_by": "sofia",
        "reviewed_at": f"2026-11-18T10:{n:02d}:00Z", "source": f"issue#{n}",
    }) for n, (k, action, payload) in enumerate(rows, 1)]  # fmt: skip
    with (review / "decisions.jsonl").open("a") as f:
        f.write("\n".join(lines) + "\n")


def build(tmp_path: Path, data: Path | None) -> Path:
    out = tmp_path / "site"
    SiteBuilder(out, images=LICENSED, data_dir=data, kinds=KINDS).build()
    return out


def test_nothing_approved_no_page_and_no_link(tmp_path: Path) -> None:
    out = build(tmp_path, tmp_path / "data")
    assert not (out / "es/glosario.html").exists()
    assert "glosario.html" not in (out / "es/index.html").read_text()


def test_only_approved_terms_are_published(tmp_path: Path) -> None:
    data = tmp_path / "data"
    decide(data, ("da", "approve", {}), ("vta", "approve", {}), ("pd", "reject", {}))
    decide(data, ("aav", "approve", {}), sha="0" * 64)  # a decision on an older version
    assert [e.term.term_id for e in published(data / "review")] == ["da", "vta"]
    out = build(tmp_path, data)
    es, en = (out / "es/glosario.html").read_text(), (out / "en/glossary.html").read_text()
    assert 'id="da"' in es and 'id="vta"' in es and 'id="pd"' not in es and 'id="aav"' not in es
    assert "Neurotransmisor ligado al movimiento" in es and "Neurotransmitter linked" in en
    assert 'href="glosario.html"' in (out / "es/index.html").read_text()
    assert "oldid=" in es and "CC BY-SA 4.0" in es
    assert check_site(out).problems == []


def test_spanish_edit_waits_for_its_english_as_a_gap(tmp_path: Path) -> None:
    data = tmp_path / "data"
    mine = "DA (Dopamina): Neurotransmisor del movimiento y la recompensa."
    decide(data, ("da", "edit", {"es": mine}))
    (entry,) = published(data / "review")
    assert entry.definition == {"es": "Neurotransmisor del movimiento y la recompensa.",
                                "en": None} and entry.mark == "edited"  # fmt: skip
    out = build(tmp_path, data)
    en = (out / "en/glossary.html").read_text()
    assert "English definition pending" in en and 'href="#gap-glossary_en"' in en
    assert "Neurotransmitter linked" not in en  # never the old draft beside her new Spanish
    assert check_site(out).problems == []


def test_a_definition_links_the_other_published_terms(tmp_path: Path) -> None:
    """SNc's definition names Parkinson: a link to PD's entry, only once PD is published."""
    data = tmp_path / "data"
    decide(data, ("snc", "approve", {}))
    es = (build(tmp_path, data) / "es/glosario.html").read_text()
    assert 'data-gl="pd"' not in es
    decide(data, ("pd", "approve", {}))
    es = (build(tmp_path / "2", data) / "es/glosario.html").read_text()
    assert 'href="#pd" data-gl="pd"' in es


def test_her_meaning_with_brackets_is_split_whole(tmp_path: Path) -> None:
    data = tmp_path / "data"
    decide(data, ("5-ht", "approve", {}))
    (entry,) = published(data / "review")
    assert entry.meaning["es"] == "5-hidroxitriptamina (serotonina)"


def test_the_check_catches_a_term_without_its_source(tmp_path: Path) -> None:
    data = tmp_path / "data"
    decide(data, ("da", "approve", {}))
    out = build(tmp_path, data)
    page = out / "es/glosario.html"
    page.write_text(page.read_text().replace("oldid=", "rev="))
    assert "es/glosario.html: glossary term da without its source or licence" in (
        check_site(out).problems
    )
