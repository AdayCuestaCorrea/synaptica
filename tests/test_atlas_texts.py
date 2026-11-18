"""Neuro Atlas's region texts (src/synaptica/atlas/texts.py, v212): one «what it is and what
it does» per pair, from its Wikipedia lead with the shared chain; clinical facts never
written; her queue and the region pages. No network, no LLM: a fake model answering by
output schema and a lead written for the test."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from synaptica.atlas import texts
from synaptica.site.build import SiteBuilder
from synaptica.site.check import check_site

LEAD = ("The hippocampus is a structure in the temporal lobe of the brain, part of the "
        "limbic system. It has a major role in forming new memories and in spatial "
        "navigation. Damage to it can cause amnesia.")  # fmt: skip
FACTS = [
    ("It sits in the temporal lobe and belongs to the limbic system.",
     "a structure in the temporal lobe of the brain, part of the limbic system", "anatomy"),
    ("It is central to making new memories and to finding one's way.",
     "a major role in forming new memories and in spatial navigation", "function"),
    ("Injury to it may lead to memory loss.", "Damage to it can cause amnesia", "clinical"),
]  # fmt: skip
EN = [("The hippocampus lies in the temporal lobe and forms part of the limbic system, a "
       "group of linked structures deep in the brain.", ["f1"]),
      ("It is central to making new memories and to finding one's way through space.",
       ["f2"])]  # fmt: skip
ES = ["El hipocampo está en el lóbulo temporal y forma parte del sistema límbico, un grupo "
      "de estructuras conectadas en el interior del cerebro.",
      "Es fundamental para crear recuerdos nuevos y para orientarse en el espacio."]  # fmt: skip


class FakeLLM:
    label = "fake/model"

    def __init__(self, facts=None):
        self.facts = FACTS if facts is None else facts
        self.calls: list[str] = []
        self.users: list[str] = []

    def complete_json(self, system, user, output, max_tokens):
        self.calls.append(output.__name__)
        self.users.append(user)
        if output.__name__ == "AtlasFacts":
            data = {"facts": [{"statement": s, "quote": q, "kind": k} for s, q, k in self.facts]}
        elif output.__name__ == "Summary":
            data = {"sentences": [{"text": t, "fact_ids": f} for t, f in EN]}
        else:
            data = {"sentences": [{"index": i, "text": t} for i, t in enumerate(ES, 1)]}
        return output.model_validate(data)


def sources(tmp_path: Path, revid: int = 7) -> Path:
    path = tmp_path / "sources.json"
    en = {"title": "Hippocampus", "accepted": True, "revid": revid, "lead": LEAD,
          "url": f"https://en.wikipedia.org/w/index.php?oldid={revid}"}  # fmt: skip
    es = {"title": "Hipocampo (anatomía)", "accepted": True, "revid": 3, "lead": "…",
          "url": "https://es.wikipedia.org/w/index.php?oldid=3"}  # fmt: skip
    path.write_text(json.dumps({"pairs": {"internal": {"leads": {"en": en, "es": es}}}}))
    return path


def drafted(tmp_path: Path) -> tuple[Path, Path]:
    out, src = tmp_path / "texts.json", sources(tmp_path)
    assert texts.write(FakeLLM(), sources_path=src, path=out) == {"internal": "drafted"}
    return out, src


def decide(review: Path, item, action: str = "approve") -> None:
    review.mkdir(parents=True, exist_ok=True)
    with (review / "decisions.jsonl").open("a") as f:
        f.write(json.dumps({
            "item_type": "atlas", "item_id": item.item_id, "content_sha256": item.content_sha256,
            "action": action, "payload": {}, "note": None, "reviewed_by": "sofia",
            "reviewed_at": "2026-11-25T10:00:00Z", "source": "issue#40"}) + "\n")  # fmt: skip


def test_one_section_from_anatomy_and_function_never_clinical(tmp_path: Path) -> None:
    out, _ = drafted(tmp_path)
    rec = json.loads(out.read_text())["pairs"]["internal"]
    assert rec["about"]["status"] == "drafted" and rec["revid"] == 7
    assert [f["kind"] for f in rec["facts"]] == ["anatomy", "function", "clinical"]
    assert rec["prompts"]["atlas_facts"].startswith("atlas-facts-v1")
    assert rec["source_es"] == "https://es.wikipedia.org/w/index.php?oldid=3"
    text = " ".join(s["text"] for s in rec["about"]["en"])
    assert "amnesia" not in text and "memory loss" not in text


def test_the_writer_never_sees_the_clinical_facts(tmp_path: Path) -> None:
    llm = FakeLLM()
    texts.write(llm, sources_path=sources(tmp_path), path=tmp_path / "texts.json")
    assert llm.calls[:2] == ["AtlasFacts", "Summary"]
    writer = llm.users[1]
    assert writer.startswith("REGION: Hippocampus") and "memory loss" not in writer


def test_a_rerun_from_the_same_revision_asks_nothing(tmp_path: Path) -> None:
    out, src = drafted(tmp_path)
    llm = FakeLLM()
    assert texts.write(llm, sources_path=src, path=out) == {} and llm.calls == []


def test_too_few_facts_no_text_and_no_card(tmp_path: Path) -> None:
    out, src = tmp_path / "texts.json", sources(tmp_path)
    status = texts.write(FakeLLM(FACTS[1:]), sources_path=src, path=out)  # 1 usable fact
    assert status == {"internal": "too_few_facts"}
    assert texts.review_items(out, src) == []


def test_her_card_cites_the_lead_at_its_revision(tmp_path: Path) -> None:
    out, src = drafted(tmp_path)
    (item,) = texts.review_items(out, src)
    assert (item.item_type, item.item_id) == ("atlas", "waxholm-1021")
    assert item.title_es == "Hipocampo · Qué es y qué hace"
    assert [s.id for s in item.content.sources] == ["wikipedia-en-atlas-waxholm-1021"]
    assert texts.source_texts([item], src) == {"wikipedia-en-atlas-waxholm-1021": LEAD}
    newer = sources(tmp_path, revid=8)  # the lead was refreshed since: out of her queue
    assert texts.review_items(out, newer) == []


def test_only_what_she_approved_is_published(tmp_path: Path) -> None:
    out, src = drafted(tmp_path)
    (item,) = texts.review_items(out, src)
    review = tmp_path / "review"
    assert texts.published(review, out, src) == {}
    decide(review, item)
    shown = texts.published(review, out, src)["internal"]
    assert shown["mark"] == "approved" and shown["es"].startswith("El hipocampo está")
    assert shown["source"]["title"] == "Hippocampus"


def test_the_region_pages_show_her_approved_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out, src = drafted(tmp_path)
    monkeypatch.setattr(texts, "TEXTS", out)
    monkeypatch.setattr(texts, "SOURCES", src)
    data = tmp_path / "data"
    (item,) = texts.review_items()
    decide(data / "review", item)
    site = tmp_path / "site"
    licensed = {"hero": {"files": [], "author": "Sofía", "licence": "CC BY-SA 4.0"}}
    SiteBuilder(site, images=licensed, data_dir=data).build()
    assert check_site(site).passed
    regions = site / "es" / "atlas" / "regiones"
    rat = (regions / "waxholm-hippocampal-formation.html").read_text()
    assert 'data-region-text="internal"' in rat and ES[0] in rat
    assert 'gap-region_text"' not in rat and "CC BY-SA 4.0" in rat
    assert "estructura completa" not in rat  # the rat pair has one page
    ca1 = (regions / "julich-ca1-hippocampus.html").read_text()
    assert ES[0] in ca1 and "estructura completa" in ca1  # one of five human pages
    en = (site / "en" / "atlas" / "regions" / "waxholm-hippocampal-formation.html").read_text()
    assert EN[0][0] in en
    other = (regions / "waxholm-cerebellum.html").read_text()
    assert "data-region-text" not in other and "gap-region_text" in other


def test_a_non_breaking_hyphen_reaches_the_model_as_a_plain_one(tmp_path: Path) -> None:
    """v220: with a non-breaking hyphen (U+2011) in its lead, Groq gave no valid JSON."""
    src = sources(tmp_path)
    data = json.loads(src.read_text())
    lead = data["pairs"]["internal"]["leads"]["en"]
    lead["lead"] = LEAD.replace("limbic system", "limbic\u2011system")
    src.write_text(json.dumps(data))
    facts = [(s, q.replace("limbic system", "limbic-system"), k) for s, q, k in FACTS]
    llm = FakeLLM(facts)
    out = tmp_path / "texts.json"
    assert texts.write(llm, sources_path=src, path=out) == {"internal": "drafted"}
    assert "\u2011" not in llm.users[0] and "limbic-system" in llm.users[0]
    assert len(json.loads(out.read_text())["pairs"]["internal"]["facts"]) == 3
    (item,) = texts.review_items(out, src)
    assert "\u2011" not in texts.source_texts([item], src)[item.content.sources[0].id]
