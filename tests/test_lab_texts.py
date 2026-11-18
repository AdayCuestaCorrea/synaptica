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
