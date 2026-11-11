"""From the decision log to the state of every item (spike S4, step 5), without network."""

from datetime import UTC, datetime, timedelta

import pytest
from apply import (
    Event,
    edited_text,
    next_queue,
    proposals,
    publishable,
    read_log,
    requeued,
    state,
    states,
)
from intake import process, write
from issue_block import encode
from models import Decision, ItemType, Queue

from conftest import FIXTURES

NEWS = (ItemType.NEWS, "pubmed-42971231")
DISEASE = (ItemType.DISEASE, "test-placeholder")
HF = (ItemType.EQUIVALENCE, "waxholm-1021")
T0 = datetime(2026, 11, 12, 19, 0, tzinfo=UTC)


@pytest.fixture
def queue() -> Queue:
    return Queue.model_validate_json((FIXTURES / "queue.json").read_text("utf-8"))


def _ev(queue, key, action, payload=None, n=1, sha=None, warnings=()) -> Event:
    item = queue.get(*key)
    return Event(Decision(
        item_type=key[0], item_id=key[1],
        content_sha256=sha or (item.content_sha256 if item else None),
        action=action, payload=payload or {}, reviewed_by="sofia-test",
        reviewed_at=T0 + timedelta(minutes=n), source=f"issue#{n}",
    ), tuple(warnings))  # fmt: skip


def _changed(queue: Queue, key, text="Borrador nuevo.") -> Queue:
    raw = queue.model_dump(mode="json")
    item = next(i for i in raw["items"] if (i["item_type"], i["item_id"]) == (key[0], key[1]))
    item["content"]["es"][0]["text"] = text
    return Queue.model_validate(raw)


def _es(queue) -> list[str]:
    return [s.text for s in queue.get(*NEWS).content.es]


def _en(queue) -> list[str]:
    return [s.text for s in queue.get(*NEWS).content.en]


# ---- Neuro Diseases ------------------------------------------------------------------


def test_disease_without_approval_is_not_published(queue):
    st = state(queue.get(*DISEASE), [])
    assert st.status == "pending" and not publishable(st)


def test_disease_approved_is_published_with_who_and_when(queue):
    st = state(queue.get(*DISEASE), [_ev(queue, DISEASE, "approve")])
    assert publishable(st)
    assert (st.reviewed_by, st.reviewed_at) == ("sofia-test", T0 + timedelta(minutes=1))


def test_a_changed_draft_loses_its_approval(queue):
    events = [_ev(queue, DISEASE, "approve")]
    changed = _changed(queue, DISEASE)
    st = state(changed.get(*DISEASE), events)
    assert st.status == "pending" and not publishable(st) and st.reviewed_by is None
    assert next_queue(changed, states(changed, events)).get(*DISEASE) is not None


def test_rejected_is_never_published(queue):
    st = state(queue.get(*NEWS), [_ev(queue, NEWS, "reject")])
    assert st.status == "rejected" and not publishable(st)
    assert next_queue(queue, {**states(queue, []), NEWS: st}).get(*NEWS) is None


def test_other_texts_are_published_while_they_wait(queue):
    assert publishable(state(queue.get(ItemType.GLOSSARY, "gaba"), []))


# ---- her edits -----------------------------------------------------------------------


def test_edit_in_spanish_only_waits_for_the_english(queue):
    es = _es(queue)
    es[3] = "Estos hallazgos sugieren que el dolutegravir no aumenta el riesgo."
    st = state(queue.get(*NEWS), [_ev(queue, NEWS, "edit", {"es": "\n".join(es)})])
    assert st.status == "edited" and st.awaiting_en and not publishable(st)
    assert st.text.es[3].text == es[3]
    assert st.text.es[3].cites == ["pubmed-42971231"]  # matched: keeps the citation
    assert [s.text for s in st.text.en] == _en(queue)  # untouched until it is rewritten


def test_edit_in_both_languages_is_published(queue):
    es, en = _es(queue), _en(queue)
    es[3], en[3] = "No aumenta el riesgo.", "It does not raise the risk."
    st = state(queue.get(*NEWS), [_ev(queue, NEWS, "edit", {"es": "\n".join(es),
                                                              "en": "\n".join(en)})])  # fmt: skip
    assert publishable(st) and not st.awaiting_en


def test_a_new_sentence_cites_nothing(queue):
    text = edited_text(queue.get(*NEWS).content, {"es": "Una frase que no se parece a ninguna."})
    assert [s.cites for s in text.es] == [[]]


# ---- held edits ----------------------------------------------------------------------

WARN = ("(español) La cifra 126 no está en el texto revisado ni en su fuente.",)


def _held(queue) -> Event:
    es = _es(queue)
    es[2] = es[2].replace("162", "126")
    return _ev(queue, NEWS, "edit", {"es": "\n".join(es)}, n=1, warnings=WARN)


def test_held_edit_goes_back_to_her_queue_with_her_text(queue):
    held = _held(queue)
    st = state(queue.get(*NEWS), [held])
    assert st.status == "held"
    item = next_queue(queue, states(queue, [held])).get(*NEWS)
    assert item.warnings == list(WARN)
    assert "126" in item.content.es[2].text and item.base == queue.get(*NEWS).content
    assert item.content_sha256 != queue.get(*NEWS).content_sha256


def test_keep_answers_the_held_edit(queue):
    held = _held(queue)
    sha = requeued(queue.get(*NEWS), held).content_sha256
    keep = _ev(queue, NEWS, "keep", {"reason": "Es 126; el abstract lo dice."}, n=2, sha=sha)
    st = state(queue.get(*NEWS), [held, keep])
    assert st.status == "edited" and st.kept_reason == "Es 126; el abstract lo dice."
    assert "126" in st.text.es[2].text and st.awaiting_en


def test_keep_on_the_draft_hash_does_nothing(queue):
    keep = _ev(queue, NEWS, "keep", {"reason": "Nada que mantener."}, n=2)
    assert state(queue.get(*NEWS), [_held(queue), keep]).status == "held"


def test_a_new_edit_on_the_held_text_settles_it(queue):
    held = _held(queue)
    sha = requeued(queue.get(*NEWS), held).content_sha256
    fixed = _ev(queue, NEWS, "edit", {"es": "\n".join(_es(queue))}, n=2, sha=sha)
    st = state(queue.get(*NEWS), [held, fixed])
    assert st.status == "edited" and st.held is None


def test_re_edit_is_checked_against_the_original_draft(queue):
    """Through the intake: a number she added does not become «known» when it comes back."""
    held = _held(queue)
    again = next_queue(queue, states(queue, [held]))
    item = again.get(*NEWS)
    d = {"item_type": "news", "item_id": NEWS[1], "content_sha256": item.content_sha256,
         "action": "edit", "payload": {"es": "\n".join(s.text for s in item.content.es)},
         "note": None}  # fmt: skip
    body = f"```text\n{encode('q', 'public', [d])}\n```"
    event = {"action": "opened", "issue": {"number": 9, "user": {"login": "s"},
             "created_at": "2026-11-13T10:00:00Z", "body": body}}  # fmt: skip
    out = process(event, again, "s")
    assert out.held and "126" in out.held[0].warnings[0]


# ---- grades, picks, topics, terms ----------------------------------------------------


def test_grade_history_is_kept(queue):
    events = [_ev(queue, HF, "set_grade", {"grade": "partial", "note_es": "Primera."}, n=1),
              _ev(queue, HF, "set_grade", {"grade": "clear"}, n=2)]  # fmt: skip
    st = state(queue.get(*HF), events)
    assert (st.grade, st.grade_note_es) == ("clear", None)
    assert [(g.grade, g.note_es) for g in st.grades] == [("partial", "Primera."), ("clear", None)]


def test_a_changed_pair_keeps_history_but_needs_a_new_grade(queue):
    events = [_ev(queue, HF, "set_grade", {"grade": "partial"})]
    raw = queue.model_dump(mode="json")
    pair = next(i for i in raw["items"] if i["item_id"] == "waxholm-1021"
                and i["item_type"] == "equivalence")  # fmt: skip
    pair["content"]["human"] = pair["content"]["human"][:2]
    st = state(Queue.model_validate(raw).get(*HF), events)
    assert st.grade is None and st.status == "pending"
    assert [(g.grade, g.current_version) for g in st.grades] == [("partial", False)]


def test_picks_topics_and_terms(queue):
    cl = (ItemType.CLASSICS, "2026-w46")
    doi = queue.get(*cl).content.candidates[0].doi
    topic = (ItemType.NEWS_TOPIC, "clinical-trials")
    terms = (ItemType.SEARCH_TERMS, "waxholm-1021")
    assert state(queue.get(*cl), [_ev(queue, cl, "pick", {"dois": [doi]})]).picks == [doi]
    assert state(queue.get(*topic), []).enabled
    assert not state(queue.get(*topic), [_ev(queue, topic, "disable")]).enabled
    st = state(queue.get(*terms), [_ev(queue, terms, "edit", {"terms": ["hippocampus"]})])
    assert st.terms == ["hippocampus"] and st.status == "decided"


# ---- the whole log -------------------------------------------------------------------


def test_fixture_log_end_to_end(queue, tmp_path):
    """The fixture decisions, read from disk: tomorrow's queue keeps only what waits."""
    (tmp_path / "decisions.jsonl").write_text(
        (FIXTURES / "decisions.jsonl").read_text("utf-8"), encoding="utf-8"
    )
    events = read_log(tmp_path)
    sts = states(queue, events)
    assert sts[("glossary", "gaba")].status == "approved"
    assert sts[("glossary", "snr")].status == "rejected"
    assert sts[("equivalence", "waxholm-1021")].grade == "clear"
    assert not sts[("news_topic", "clinical-trials")].enabled
    assert [p.payload["term"] for p in proposals(events)] == ["LTP"]
    waiting = {i.key for i in next_queue(queue, sts).items}
    assert ("disease", "test-placeholder") in waiting
    assert ("glossary", "gaba") not in waiting and ("classics", "2026-w46") not in waiting


def test_the_real_issue_through_intake_and_apply(queue, tmp_path):
    import json

    event = json.loads((FIXTURES / "issue_opened_1.json").read_text("utf-8"))
    write(process(event, queue, "AdayCuestaCorrea"), tmp_path)
    sts = states(queue, read_log(tmp_path))
    assert sts[("equivalence", "waxholm-1021")].grade == "clear"
    assert sts[("equivalence", "waxholm-1021")].grade_note_es == "prueba prueba"
    assert sts[("search_terms", "waxholm-1021")].status == "decided"
