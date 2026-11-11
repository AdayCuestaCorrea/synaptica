"""The review queue and decision models (spike S4, step 1) on the fixtures, without network."""

import json
from datetime import datetime

import pytest
from make_fixtures import GENERATED_AT, decisions, items
from models import Decision, ItemType, Queue, ReviewItem, check_against
from pydantic import ValidationError

from conftest import FIXTURES


@pytest.fixture
def queue() -> Queue:
    return Queue.model_validate_json((FIXTURES / "queue.json").read_text("utf-8"))


@pytest.fixture
def log() -> list[Decision]:
    lines = (FIXTURES / "decisions.jsonl").read_text("utf-8").splitlines()
    return [Decision.model_validate_json(line) for line in lines]


def _raw(queue: Queue, item_type: str, item_id: str) -> dict:
    return queue.get(ItemType(item_type), item_id).model_dump(mode="json")


def _decision(**changes) -> dict:
    base = {
        "item_type": "glossary", "item_id": "gaba", "content_sha256": "0" * 64,
        "action": "approve", "reviewed_by": "sofia-test",
        "reviewed_at": "2026-11-12T19:00:00Z", "source": "issue#1",
    }  # fmt: skip
    return base | changes


def test_fixtures_are_up_to_date(queue, log):
    """The committed fixtures are what make_fixtures.py builds (regenerate them if not)."""
    assert queue == Queue(generated_at=GENERATED_AT, items=items())
    assert log == decisions(queue)


def test_every_item_type_and_action_has_an_example(queue, log):
    assert {i.item_type for i in queue.items} == set(ItemType) - {
        ItemType.ATLAS, ItemType.LAB, ItemType.LEARN,  # same "text" shape as glossary
    }  # fmt: skip
    assert {d.action.value for d in log} >= {"approve", "edit", "reject", "keep", "set_grade",
                                             "pick", "disable", "propose"}  # fmt: skip


def test_all_example_decisions_apply_to_the_queue(queue, log):
    assert {d.source: check_against(d, queue) for d in log} == {d.source: [] for d in log}


def test_hash_is_stable_and_changes_with_the_content(queue):
    item = queue.get(ItemType.GLOSSARY, "gaba")
    raw = item.model_dump(mode="json")
    assert ReviewItem.model_validate(raw).content_sha256 == item.content_sha256
    raw["content"]["es"][0]["text"] += " Cambio."
    assert ReviewItem.model_validate(raw).content_sha256 != item.content_sha256


def test_the_hash_ignores_the_title_but_not_the_language(queue):
    raw = _raw(queue, "glossary", "gaba")
    original = ReviewItem.model_validate(raw).content_sha256
    raw["title_es"] = "Otro título"
    assert ReviewItem.model_validate(raw).content_sha256 == original
    raw["content"]["en"][0]["text"] = "Changed."
    assert ReviewItem.model_validate(raw).content_sha256 != original


def test_a_changed_draft_makes_the_approval_stale(queue, log):
    approval = log[0]
    raw = queue.model_dump(mode="json")
    gaba = next(i for i in raw["items"] if i["item_id"] == "gaba")
    gaba["content"]["es"][0]["text"] = "GABA: borrador nuevo."
    assert check_against(approval, Queue.model_validate(raw)) == [
        "stale: the item changed after she reviewed it"
    ]


def test_disease_drafts_are_never_public(queue):
    raw = _raw(queue, "disease", "test-placeholder")
    assert queue.get(ItemType.DISEASE, "test-placeholder").blocking
    with pytest.raises(ValidationError, match="never go on the public review page"):
        ReviewItem.model_validate(raw | {"public": True})


def test_text_items_need_both_languages(queue):
    raw = _raw(queue, "glossary", "gaba")
    raw["content"]["en"] = []
    with pytest.raises(ValidationError):
        ReviewItem.model_validate(raw)


def test_sentences_cite_known_sources(queue):
    raw = _raw(queue, "glossary", "gaba")
    raw["content"]["es"][0]["cites"] = ["nowhere"]
    with pytest.raises(ValidationError, match="unknown sources"):
        ReviewItem.model_validate(raw)


def test_content_kind_matches_the_item_type(queue):
    raw = _raw(queue, "news_topic", "diseases")
    with pytest.raises(ValidationError, match="needs content of kind"):
        ReviewItem.model_validate(raw | {"item_type": "glossary"})


def test_duplicate_items_are_rejected(queue):
    raw = queue.model_dump(mode="json")
    raw["items"].append(raw["items"][0])
    with pytest.raises(ValidationError, match="duplicate"):
        Queue.model_validate(raw)


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"action": "set_grade", "payload": {"grade": "clear"}}, "does not apply"),
        ({"content_sha256": None}, "needs its content hash"),
        ({"content_sha256": "abc"}, "String should match pattern"),
        ({"item_type": "equivalence", "action": "set_grade", "payload": {"grade": "clara"}},
         "grade"),
        ({"action": "edit", "payload": {}}, "at least one language"),
        ({"action": "keep", "payload": {}}, "reason"),
        ({"action": "approve", "payload": {"extra": 1}}, "Extra inputs"),
        ({"action": "propose", "payload": {"term": "LTP", "meaning_es": "x"}}, "no content hash"),
        ({"item_type": "disease", "action": "propose", "content_sha256": None,
          "payload": {"term": "x", "meaning_es": "y"}}, "cannot be proposed"),
        ({"reviewed_at": "2026-11-12T19:00:00"}, "time zone"),
        ({"source": "whatsapp"}, "String should match pattern"),
    ],
)  # fmt: skip
def test_invalid_decisions(changes, match):
    with pytest.raises(ValidationError, match=match):
        Decision.model_validate(_decision(**changes))


def test_dates_are_stored_in_utc():
    d = Decision.model_validate(_decision(reviewed_at="2026-11-12T20:00:00+01:00"))
    assert d.reviewed_at == datetime.fromisoformat("2026-11-12T19:00:00+00:00")
    assert d.model_dump(mode="json")["reviewed_at"] == "2026-11-12T19:00:00Z"


def test_unknown_item(queue):
    d = Decision.model_validate(_decision(item_id="nope"))
    assert check_against(d, queue) == ["unknown item glossary/nope"]


def test_picks_must_be_candidates_and_within_the_limit(queue):
    item = queue.get(ItemType.CLASSICS, "2026-w46")
    dois = [c.doi for c in item.content.candidates]
    d = Decision.model_validate(_decision(
        item_type="classics", item_id="2026-w46", content_sha256=item.content_sha256,
        action="pick", payload={"dois": [*dois[:3], "10.1/made-up"]},
    ))  # fmt: skip
    assert check_against(d, queue) == [
        "picks outside the candidates: ['10.1/made-up']",
        "more than 2 picks",
    ]


def test_fixtures_carry_no_publisher_text():
    """No abstracts in the queue: only our own summaries and metadata (CLAUDE.md)."""
    text = (FIXTURES / "queue.json").read_text("utf-8")
    assert not {"abstract", "abstract_inverted_index"} & set(json.loads(text)["items"][0])
    assert "abstract" not in text.lower()
