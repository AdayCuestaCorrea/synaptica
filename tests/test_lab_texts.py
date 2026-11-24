"""Neuro Lab's text drafts (src/synaptica/lab/texts.py, v208): facts from the Wikipedia
lead, English and Spanish per section with the summaries' checks. No network, no LLM: a
fake model answering by output schema and a lead written for the test."""

from __future__ import annotations

import json
from pathlib import Path

from synaptica.lab import texts

LEAD = ("Optogenetics is a biological technique to control the activity of neurons with "
        "light. Neurons are made to express light-sensitive ion channels, so that a flash of "
        "light can switch them on or off within milliseconds. The method requires genetic "
        "modification of the target cells, and light scatters in brain tissue.")  # fmt: skip
FACTS = [
    ("Researchers use light to turn the activity of chosen nerve cells up or down.",
     "control the activity of neurons with light", "what"),
    ("The cells carry channels that respond to light and can be switched within milliseconds.",
     "a flash of light can switch them on or off within milliseconds", "what"),
    ("The target cells must first be genetically changed.",
     "requires genetic modification of the target cells", "limit"),
    ("It sees through walls.", "Optogenetics sees through walls", "what"),  # not in the lead
]  # fmt: skip
EN = {
    "what": [("Optogenetics lets researchers switch chosen nerve cells on or off with light, "
              "because those cells carry channels that respond to it.", ["f1", "f2"]),
             ("The switch happens within milliseconds, fast enough to follow brain activity "
              "as it unfolds.", ["f2"])],
    "limit": [("Before it can be used, the target cells must be genetically changed so that "
               "they respond to light at all.", ["f3"])],
}  # fmt: skip
ES = {
    "what": ["La optogenética permite encender o apagar con luz las neuronas elegidas, porque "
             "esas células llevan canales que responden a ella.",
             "El cambio ocurre en milisegundos, lo bastante rápido para seguir la actividad "
             "del cerebro mientras sucede."],
    "limit": ["Antes de usarla, hay que modificar genéticamente las células elegidas para que "
              "respondan a la luz."],
}  # fmt: skip


class FakeLLM:
    label = "fake/model"

    def __init__(self, english=None):
        self.english = english or EN
        self.calls: list[str] = []
        self.section = "what"

    def complete_json(self, system, user, output, max_tokens):
        self.calls.append(output.__name__)
        if output.__name__ == "LabFacts":
            data = {"facts": [{"statement": s, "quote": q, "kind": k} for s, q, k in FACTS]}
        elif output.__name__ == "Summary":
            self.section = "limit" if "SECTION: limits" in user else "what"
            data = {
                "sentences": [{"text": t, "fact_ids": f} for t, f in self.english[self.section]]
            }
        else:
            data = {"sentences": [{"index": i, "text": t}
                                  for i, t in enumerate(ES[self.section], 1)]}  # fmt: skip
        return output.model_validate(data)


def sources(tmp_path: Path, accepted: bool = True) -> Path:
    path = tmp_path / "sources.json"
    entry = {"title": "Optogenetics", "accepted": accepted, "revid": 7, "lead": LEAD,
             "url": "https://en.wikipedia.org/w/index.php?oldid=7"}  # fmt: skip
    path.write_text(json.dumps({"techniques": {"optogenetics": {
        "en": entry, "es": {"title": None, "accepted": False}}}}))  # fmt: skip
    return path


def test_both_sections_drafted_from_verified_facts_only(tmp_path: Path) -> None:
    out = tmp_path / "texts.json"
    status = texts.write(FakeLLM(), sources_path=sources(tmp_path), path=out)
    assert status == {"optogenetics": {"what": "drafted", "limit": "drafted"}}
    rec = json.loads(out.read_text())["techniques"]["optogenetics"]
    assert [f["kind"] for f in rec["facts"]] == ["what", "what", "limit"]
    assert rec["rejected"] == ["quote not found verbatim in the source"]
    assert rec["what"]["es"][0]["text"].startswith("La optogenética")
    assert "quote" not in rec["facts"][0]  # the lead's words stay in sources.json only
    assert "Not published" in out.read_text()


def test_a_rerun_from_the_same_revision_asks_nothing(tmp_path: Path) -> None:
    out, src = tmp_path / "texts.json", sources(tmp_path)
    texts.write(FakeLLM(), sources_path=src, path=out)
    again = FakeLLM()
    assert texts.write(again, sources_path=src, path=out) == {} and again.calls == []


def test_a_copied_english_text_fails_and_is_not_kept(tmp_path: Path) -> None:
    copied = EN | {"limit": [("The method requires genetic modification of the target cells, "
                              "and light scatters in brain tissue.", ["f3"])]}  # fmt: skip
    out = tmp_path / "texts.json"
    status = texts.write(FakeLLM(copied), sources_path=sources(tmp_path), path=out)
    assert status["optogenetics"]["limit"] == "failed_en"
    rec = json.loads(out.read_text())["techniques"]["optogenetics"]["limit"]
    assert "en" not in rec and any("copies 8+ words" in p for p in rec["problems"])
    assert "genetic modification of the target" not in out.read_text()


def test_no_accepted_lead_no_draft(tmp_path: Path) -> None:
    llm = FakeLLM()
    assert texts.write(llm, sources_path=sources(tmp_path, accepted=False),
                       path=tmp_path / "t.json") == {}  # fmt: skip
    assert llm.calls == []


class BrokenLLM(FakeLLM):
    def complete_json(self, system, user, output, max_tokens):
        from synaptica.llm import LLMOutputError

        raise LLMOutputError("fake/model: invalid output")


def test_a_model_error_skips_the_technique_and_saves_nothing_for_it(tmp_path: Path) -> None:
    out = tmp_path / "texts.json"
    status = texts.write(BrokenLLM(), sources_path=sources(tmp_path), path=out)
    assert status == {"optogenetics": {"what": "model_error", "limit": "model_error"}}
    assert json.loads(out.read_text())["techniques"] == {}  # asked again on the next run


# ---- her review and the site (v210) ---------------------------------------------------


def drafted(tmp_path: Path) -> tuple[Path, Path]:
    out, src = tmp_path / "texts.json", sources(tmp_path)
    texts.write(FakeLLM(), sources_path=src, path=out)
    return out, src


def decide(review: Path, item, action: str, payload: dict | None = None) -> None:
    review.mkdir(parents=True, exist_ok=True)
    with (review / "decisions.jsonl").open("a") as f:
        f.write(json.dumps({
            "item_type": "lab", "item_id": item.item_id, "content_sha256": item.content_sha256,
            "action": action, "payload": payload or {}, "note": None, "reviewed_by": "sofia",
            "reviewed_at": "2026-11-19T10:00:00Z", "source": "issue#30"}) + "\n")  # fmt: skip


def test_one_item_per_drafted_section_citing_its_lead(tmp_path: Path) -> None:
    out, src = drafted(tmp_path)
    items = texts.review_items(out, src)
    assert [(i.item_type, i.item_id, i.title_es) for i in items] == [
        ("lab", "optogenetics-what", "Optogenética · Qué permite ver"),
        ("lab", "optogenetics-limit", "Optogenética · Límites"),
    ]
    what = items[0].content
    assert what.es[0].text.startswith("La optogenética") and len(what.en) == 2
    assert [s.id for s in what.sources] == ["wikipedia-en-lab-optogenetics"]
    assert texts.source_texts(items, src) == {"wikipedia-en-lab-optogenetics": LEAD}


def test_a_failed_section_or_a_newer_lead_is_not_queued(tmp_path: Path) -> None:
    copied = EN | {"limit": [("The method requires genetic modification of the target cells, "
                              "and light scatters in brain tissue.", ["f3"])]}  # fmt: skip
    out, src = tmp_path / "texts.json", sources(tmp_path)
    texts.write(FakeLLM(copied), sources_path=src, path=out)
    assert [i.item_id for i in texts.review_items(out, src)] == ["optogenetics-what"]
    body = json.loads(src.read_text())
    body["techniques"]["optogenetics"]["en"]["revid"] = 8  # the lead was refreshed since
    src.write_text(json.dumps(body))
    assert texts.review_items(out, src) == []


def test_only_what_she_approved_or_corrected_is_published(tmp_path: Path) -> None:
    out, src = drafted(tmp_path)
    what, limit = texts.review_items(out, src)
    review = tmp_path / "review"
    assert texts.published(review, out, src) == {}
    decide(review, what, "approve")
    decide(review, limit, "edit", {"es": "Primero hay que modificar genéticamente las células."})
    shown = texts.published(review, out, src)["optogenetics"]
    assert shown["what"]["mark"] == "approved" and shown["what"]["reviewed_at"] == "2026-11-19"
    assert shown["what"]["en"].startswith("Optogenetics lets researchers")
    assert shown["what"]["source"]["title"] == "Optogenetics"
    assert shown["limit"]["es"].startswith("Primero hay que") and shown["limit"]["en"] is None


# ---- «limits» from a section of the article (v214) ------------------------------------

SECTION = ("Not every cell expresses the opsin at the same level, so the same light has "
           "different effects on each cell. Light also fades as it goes deeper into brain "
           "tissue.")  # fmt: skip
LIMIT_FACTS = [
    ("Cells take up the light-sensitive protein unevenly, so one flash affects them "
     "differently.", "Not every cell expresses the opsin at the same level", "limit"),
    ("Light weakens the deeper it travels into the brain.",
     "Light also fades as it goes deeper into brain tissue", "limit"),
]  # fmt: skip
LIMIT_EN = [
    (
        "Cells take up the light-sensitive protein unevenly, so a single flash does not "
        "affect them all alike, and light weakens deeper in the brain.",
        ["l1", "l2"],
    )
]
LIMIT_ES = ["Las células captan de forma desigual la proteína sensible a la luz, así que un "
            "mismo destello no las afecta igual, y la luz se debilita en lo profundo del "
            "cerebro."]  # fmt: skip


class SectionLLM(FakeLLM):
    """The lead gives no «limits» facts; the section gives two."""

    def complete_json(self, system, user, output, max_tokens):
        if output.__name__ == "LabFacts" and "SECTION «" in user:
            self.calls.append("LabFacts:section")
            assert SECTION in user and LEAD not in user
            data = {"facts": [{"statement": s, "quote": q, "kind": k}
                              for s, q, k in LIMIT_FACTS]}  # fmt: skip
            return output.model_validate(data)
        if output.__name__ == "LabFacts":
            self.calls.append("LabFacts")
            data = {"facts": [{"statement": s, "quote": q, "kind": k}
                              for s, q, k in FACTS if k != "limit"]}  # fmt: skip
            return output.model_validate(data)
        if output.__name__ == "Summary" and "SECTION: limits" in user:
            self.calls.append("Summary")
            self.section = "limit"
            return output.model_validate(
                {"sentences": [{"text": t, "fact_ids": f} for t, f in LIMIT_EN]}
            )
        if output.__name__ != "Summary" and self.section == "limit":
            self.calls.append(output.__name__)
            return output.model_validate(
                {"sentences": [{"index": i, "text": t} for i, t in enumerate(LIMIT_ES, 1)]}
            )
        return super().complete_json(system, user, output, max_tokens)


def with_section(tmp_path: Path, heading: str = "Technical challenges and limitations") -> Path:
    src = sources(tmp_path)
    body = json.loads(src.read_text())
    body["techniques"]["optogenetics"]["limits_en"] = {
        "heading": heading, "revid": 7, "url": "https://en.wikipedia.org/w/index.php?oldid=7",
        "retrieved": "2026-11-18", "text": SECTION}  # fmt: skip
    src.write_text(json.dumps(body))
    return src


def test_limits_from_the_section_without_asking_the_lead_again(tmp_path: Path) -> None:
    out, src = tmp_path / "texts.json", sources(tmp_path)
    assert texts.write(SectionLLM(), sources_path=src, path=out)["optogenetics"] == {
        "what": "drafted",
        "limit": "too_few_facts",
    }  # the lead alone: no limits
    before = json.loads(out.read_text())["techniques"]["optogenetics"]
    src = with_section(tmp_path)
    llm = SectionLLM()
    assert texts.write(llm, sources_path=src, path=out) == {"optogenetics": {"limit": "drafted"}}
    assert llm.calls[0] == "LabFacts:section" and "LabFacts" not in llm.calls
    rec = json.loads(out.read_text())["techniques"]["optogenetics"]
    assert rec["what"] == before["what"]  # already in her queue: not touched
    assert rec["limit"]["section"] == "Technical challenges and limitations"
    assert [f["id"] for f in rec["facts"]] == ["f1", "f2", "l1", "l2"]
    again = SectionLLM()
    assert texts.write(again, sources_path=src, path=out) == {} and again.calls == []


def test_her_limits_card_cites_the_section(tmp_path: Path) -> None:
    out, src = tmp_path / "texts.json", with_section(tmp_path)
    texts.write(SectionLLM(), sources_path=src, path=out)  # first draft: lead, then section
    items = {i.item_id: i for i in texts.review_items(out, src)}
    limit = items["optogenetics-limit"]
    (s,) = limit.content.sources
    assert s.id == "wikipedia-en-lab-optogenetics-limits"
    assert "sección «Technical challenges and limitations»" in s.label
    assert items["optogenetics-what"].content.sources[0].id == "wikipedia-en-lab-optogenetics"
    got = texts.source_texts(list(items.values()), src)
    assert got[s.id] == SECTION and got["wikipedia-en-lab-optogenetics"] == LEAD
    # The section is no longer stored (renamed in the article): the card leaves her queue.
    renamed = with_section(tmp_path, heading="Limitations")
    assert "optogenetics-limit" not in {i.item_id for i in texts.review_items(out, renamed)}


class BadLimitSpanish(FakeLLM):
    def complete_json(self, system, user, output, max_tokens):
        if output.__name__ == "AdaptedText" and self.section == "limit":
            self.calls.append(output.__name__)
            bad = ES["limit"][0].replace("respondan", "miñojen")
            return output.model_validate({"sentences": [{"index": 1, "text": bad}]})
        return super().complete_json(system, user, output, max_tokens)


def test_a_failed_spanish_limit_is_asked_again_alone(tmp_path: Path) -> None:
    """v223: only the section whose Spanish failed, and only its Spanish."""
    out, src = tmp_path / "texts.json", sources(tmp_path)
    status = texts.write(BadLimitSpanish(), sources_path=src, path=out)
    assert status == {"optogenetics": {"what": "drafted", "limit": "failed_es"}}
    what = json.loads(out.read_text())["techniques"]["optogenetics"]["what"]
    llm = FakeLLM()
    llm.section = "limit"
    again = texts.spanish_again(llm, sources_path=src, path=out)
    assert again == {"optogenetics": {"limit": "drafted"}} and llm.calls == ["AdaptedText"]
    rec = json.loads(out.read_text())["techniques"]["optogenetics"]
    assert rec["what"] == what and rec["limit"]["es"][0]["text"] == ES["limit"][0]
    assert "problems" not in rec["limit"] and rec["limit"]["es_generator"] == "fake/model"


class AgainLLM(FakeLLM):
    """Answers like ``FakeLLM``, citing the facts asked again (``r1``…)."""

    def __init__(self, english=None):
        super().__init__({k: [(text, [i.replace("f", "r") for i in ids]) for text, ids in v]
                          for k, v in (english or EN).items()})  # fmt: skip


def test_a_failed_english_section_is_asked_again_alone(tmp_path: Path) -> None:
    """v232: only the section whose English failed; the other one keeps its facts and text."""
    copied = EN | {"limit": [("The method requires genetic modification of the target cells, "
                              "and light scatters in brain tissue.", ["f3"])]}  # fmt: skip
    out, src = tmp_path / "texts.json", sources(tmp_path)
    texts.write(FakeLLM(copied), sources_path=src, path=out)
    before = json.loads(out.read_text())["techniques"]["optogenetics"]
    assert before["limit"]["status"] == "failed_en"
    llm = AgainLLM()
    again = texts.english_again(llm, sources_path=src, path=out)
    assert again == {"optogenetics": {"limit": "drafted"}}
    assert llm.calls == ["LabFacts", "Summary", "AdaptedText"]
    rec = json.loads(out.read_text())["techniques"]["optogenetics"]
    assert rec["what"] == before["what"]
    assert [f["id"] for f in rec["facts"]] == ["f1", "f2", "f3", "r1", "r2", "r3"]
    assert rec["limit"]["en"][0]["fact_ids"] == ["r3"]
    assert rec["limit"]["prompts"]["lab_write_en"].startswith("lab-write-en-v2")
    assert texts.english_again(AgainLLM(), sources_path=src, path=out) == {}  # nothing left
