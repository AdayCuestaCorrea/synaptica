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


# ---- the viewer (P6) ------------------------------------------------------------------


def test_every_mapped_region_exists_in_its_atlas_and_term_in_the_glossary() -> None:
    """The viewer's key is the atlas and its short name (viewer.js ``names``)."""
    from synaptica.config import project_root
    from synaptica.glossary.regions import load_region_terms

    atlas = project_root() / "site/static/atlas"
    shorts = {}
    for name in ("waxholm", "julich"):
        rows = json.loads((atlas / name / "labels.json").read_text("utf-8"))["rows"]
        shorts[name] = {r.get("acronym") or r["name"].split(" (")[0] for r in rows}
    for r in load_region_terms():
        assert r["short"] in shorts[r["atlas"]], r
        assert r["term_id"] in ITEMS, r


def test_the_atlas_page_gets_the_approved_region_terms_only(tmp_path: Path) -> None:
    data = tmp_path / "data"
    decide(data, ("vta", "approve", {}), ("nac", "approve", {}), ("da", "approve", {}))
    out = tmp_path / "site"
    SiteBuilder(out, images=LICENSED, data_dir=data, kinds=(*KINDS, "atlas")).build()
    index = json.loads((out / "es/glosario-atlas.json").read_text())
    assert index["page"] == "glosario.html"
    assert index["regions"]["waxholm:VTA"] == {"term": "vta", "relation": "same"}
    assert index["regions"]["julich:AcbM"] == {"term": "nac", "relation": "part"}
    assert "waxholm:STh" not in index["regions"]  # STN is not approved
    assert set(index["terms"]) == {"vta", "nac"}  # DA is not a region
    assert index["terms"]["vta"]["meaning"] == "Área tegmental ventral"
    en = json.loads((out / "en/glossary-atlas.json").read_text())
    assert en["terms"]["vta"]["definition"].startswith("Midbrain region")
    assert 'data-glossary-index="glosario-atlas.json"' in (out / "es/atlas.html").read_text()
    assert check_site(out).problems == []


def test_without_approved_terms_the_viewer_gets_no_index(tmp_path: Path) -> None:
    out = tmp_path / "site"
    SiteBuilder(out, images=LICENSED, data_dir=tmp_path / "data", kinds=(*KINDS, "atlas")).build()
    assert not (out / "es/glosario-atlas.json").exists()
    assert "data-glossary-index" not in (out / "es/atlas.html").read_text()


# ---- her own proposals (option B, v183) ----------------------------------------------

PROPOSALS = Path(__file__).parent / "fixtures" / "review" / "glossary_proposals.jsonl"
HERS = {"nmda", "bdnf", "5-ht", "pet", "ltd", "stn", "ros"}


def proposals(data: Path, edit=None) -> None:
    """Her 7 real proposals (issues #14 and #15 on the data branch), optionally edited."""
    (data / "review").mkdir(parents=True, exist_ok=True)
    lines = PROPOSALS.read_text("utf-8").splitlines()
    if edit:
        lines = [edit(json.loads(x)) for x in lines]
        lines = [json.dumps(x) for x in lines]
    (data / "review" / "decisions.jsonl").write_text("\n".join(lines) + "\n", "utf-8")


def test_her_proposals_show_her_spanish_and_the_english_gap(tmp_path: Path) -> None:
    data = tmp_path / "data"
    proposals(data)
    entries = {e.term.term_id: e for e in published(data / "review")}
    assert set(entries) == HERS  # the 17 terms of the proposal: not hers, not shown
    nmda = entries["nmda"]
    assert nmda.mark == "proposed" and nmda.reviewed_at == "2026-11-14"
    assert nmda.meaning == {"es": "N-metil-D-aspartato", "en": None}
    assert nmda.definition["en"] is None
    out = build(tmp_path, data)
    es, en = (out / "es/glosario.html").read_text(), (out / "en/glossary.html").read_text()
    assert "Tipo de receptor de glutamato implicado en la plasticidad sináptica" in es
    assert "Propuesta y escrita por nuestra revisora científica el 14 nov 2026" in es
    assert en.count('class="gl-pending"') == 7 and "#gap-glossary_en" in en
    assert "Type of glutamate receptor" not in en  # the LLM draft she has not seen
    assert check_site(out).problems == []


def test_only_her_exact_words_are_shown_as_hers(tmp_path: Path) -> None:
    def change(d):
        if d["payload"]["term"] == "PET":
            d["payload"]["explanation_es"] += " Otra frase."
        return d

    data = tmp_path / "data"
    proposals(data, change)
    assert "pet" not in {e.term.term_id for e in published(data / "review")}


def test_approving_the_item_adds_the_english_and_rejecting_takes_it_off(tmp_path: Path) -> None:
    data = tmp_path / "data"
    proposals(data)
    decide(data, ("nmda", "approve", {}), ("ros", "reject", {}))
    entries = {e.term.term_id: e for e in published(data / "review")}
    assert entries["nmda"].mark == "approved"
    assert entries["nmda"].definition["en"].startswith("Type of glutamate receptor")
    assert "ros" not in entries and "bdnf" in entries


def test_her_stn_shows_in_the_viewer_in_spanish_only(tmp_path: Path) -> None:
    data = tmp_path / "data"
    proposals(data)
    out = tmp_path / "site"
    SiteBuilder(out, images=LICENSED, data_dir=data, kinds=(*KINDS, "atlas")).build()
    es = json.loads((out / "es/glosario-atlas.json").read_text())
    en = json.loads((out / "en/glossary-atlas.json").read_text())
    assert es["regions"]["waxholm:STh"]["term"] == "stn"
    assert es["terms"]["stn"]["definition"].startswith("Estructura de los ganglios basales")
    assert en["terms"]["stn"]["definition"] is None  # the viewer says «pending»


# ---- her Spanish-only correction and the English redrafted in a session (row 34) ----

MINE = "DA (Dopamina): Neurotransmisor del movimiento y la recompensa."


def redraft(tmp_path: Path, monkeypatch):
    """A copy of texts.csv the test may rewrite, and her Spanish-only edit of DA."""
    import shutil

    from synaptica.glossary import texts

    copy = tmp_path / "texts.csv"
    shutil.copy(texts.TEXTS, copy)
    monkeypatch.setattr(texts, "TEXTS", copy)
    data = tmp_path / "data"
    decide(data, ("da", "edit", {"es": MINE}))
    return texts, data, copy


def test_her_spanish_edit_is_listed_until_its_english_is_drafted(tmp_path, monkeypatch):
    import datetime as dt

    texts, data, copy = redraft(tmp_path, monkeypatch)
    (w,) = texts.awaiting_en(data / "review")
    assert (w.term.term_id, w.meaning_es, w.source) == ("da", "Dopamina", "issue#1")
    assert w.definition_es == "Neurotransmisor del movimiento y la recompensa."
    before = copy.read_text()
    bad = texts.with_english_draft(w, "Dopamine", "Released by 42 neurons.", "claude-opus-5-5",
                                   dt.date(2026, 11, 18))  # fmt: skip
    assert any("42" in p for p in bad) and copy.read_text() == before  # nothing written
    assert texts.with_english_draft(w, "Dopamine", "Neurotransmitter of movement and reward.",
                                    "claude-opus-5-5", dt.date(2026, 11, 18)) == []  # fmt: skip
    row = texts.load_texts()["da"]
    assert row.origin == {"es": "issue#1", "en": "llm-draft:claude-opus-5-5:2026-11-18"}
    assert texts.awaiting_en(data / "review") == []
    # Others untouched: only the DA line changed.
    changed = set(before.splitlines()) ^ set(copy.read_text().splitlines())
    assert all(line.startswith("da,") for line in changed)


def test_while_the_draft_waits_the_site_keeps_her_spanish_then_her_yes_adds_english(
    tmp_path, monkeypatch
):
    import datetime as dt

    texts, data, _ = redraft(tmp_path, monkeypatch)
    (w,) = texts.awaiting_en(data / "review")
    texts.with_english_draft(w, "Dopamine", "Neurotransmitter of movement and reward.",
                             "claude-opus-5-5", dt.date(2026, 11, 18))  # fmt: skip
    (entry,) = published(data / "review")  # the new version waits in her queue
    assert entry.mark == "edited" and entry.definition["en"] is None
    assert entry.definition["es"] == "Neurotransmisor del movimiento y la recompensa."
    new = next(i for i in texts.review_items() if i.item_id == "da")
    assert new.content_sha256 != ITEMS["da"].content_sha256  # back in her queue
    decide(data, ("da", "approve", {}), sha=new.content_sha256)
    (entry,) = published(data / "review")
    assert entry.mark == "approved"
    assert entry.definition["en"] == "Neurotransmitter of movement and reward."


def test_a_text_without_its_opening_is_not_split_by_guess(tmp_path, monkeypatch):
    import datetime as dt

    texts, data, copy = redraft(tmp_path, monkeypatch)
    decide(data, ("da", "edit", {"es": "Neurotransmisor del movimiento."}))
    (w,) = texts.awaiting_en(data / "review")
    assert w.meaning_es is None
    before = copy.read_text()
    assert texts.with_english_draft(w, "Dopamine", "Neurotransmitter of movement.",
                                    "claude-opus-5-5", dt.date(2026, 11, 18))  # fmt: skip
    assert copy.read_text() == before
