"""The block of decisions sent in a GitHub Issue (spike S4, step 3), without network."""

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from synaptica.review.issue_block import DECISION_KEYS, MAGIC, BlockError, decode, encode
from synaptica.review.models import Decision, Queue, check_against
from synaptica.review.page import MAX_URL, TEMPLATE

FIXTURES = Path(__file__).parent / "fixtures" / "review"


INTAKE = ("reviewed_by", "reviewed_at", "source")


@pytest.fixture
def queue() -> Queue:
    return Queue.model_validate_json((FIXTURES / "queue.json").read_text("utf-8"))


@pytest.fixture
def sent() -> list[dict]:
    """The fixture decisions as the page sends them: without the fields of the intake."""
    lines = (FIXTURES / "decisions.jsonl").read_text("utf-8").splitlines()
    return [{k: v for k, v in json.loads(x).items() if k not in INTAKE} for x in lines]


def _form_body(block: str) -> str:
    """What GitHub writes for the Issue form: the field label and a fenced block."""
    return f"### Decisiones\n\n```text\n{block}\n```"


def test_round_trip_through_the_issue_form(sent, queue):
    block = decode(_form_body(encode("2026-11-11T06:00:00Z", "public", sent)))
    assert (block.queue, block.page, block.part) == ("2026-11-11T06:00:00Z", "public", (1, 1))
    assert block.decisions == sent
    intake = {"reviewed_by": "sofia-test", "reviewed_at": datetime.now(UTC), "source": "issue#1"}
    for d in block.decisions:
        assert check_against(Decision.model_validate(d | intake), queue) == []


def test_bare_block_and_windows_line_ends(sent):
    text = encode("q", "private", sent[:2], part=(2, 3)).replace("\n", "\r\n")
    block = decode("Pegado a mano:\r\n\r\n" + text)
    assert block.part == (2, 3) and block.decisions == sent[:2]


def test_free_text_survives(sent):
    tricky = {**sent[0], "note": 'Línea 1\n```\n### no es un título\n"comillas" </script>'}
    assert decode(_form_body(encode("q", "public", [tricky]))).decisions == [tricky]


def test_the_block_cannot_claim_who_or_when(sent):
    forged = encode("q", "public", [sent[0] | {"reviewed_by": "someone"}])
    assert "reviewed_by" not in forged  # encode keeps only the decision fields
    raw = forged.replace('"note":null', '"note":null,"reviewed_by":"someone"')
    with pytest.raises(BlockError, match="unexpected fields"):
        decode(raw)


@pytest.mark.parametrize(
    ("body", "match"),
    [
        ("### Decisiones\n\n_No response_", "no SYNAPTICA review block"),
        (f"{MAGIC}\nqueue: q\npage: public\n" + '{"item_type":"x"}', "header line 'part'"),
        (f"{MAGIC}\nqueue: q\npage: public\npart: 3/2\n" + '{"item_type":"x"}', "wrong part"),
        (f"{MAGIC}\nqueue: q\npage: public\npart: 1/1\n" + "{not json", "not valid JSON"),
        (f"{MAGIC}\nqueue: q\npage: public\npart: 1/1\n", "no decisions"),
        (f"{MAGIC}\nqueue: q\npage: public\npart: 1/1\n[1, 2]", "unexpected fields"),
    ],
)
def test_broken_blocks(body, match):
    with pytest.raises(BlockError, match=match):
        decode(body)


def test_the_page_writes_the_same_format():
    """The page's blockOf (JavaScript) and encode share the magic line and the field order."""
    html = TEMPLATE.read_text("utf-8")
    assert f'const MAGIC = "{MAGIC}";' in html
    keys = re.search(r"const DECISION_KEYS = (\[.*?\]);", html).group(1)
    assert tuple(json.loads(keys)) == DECISION_KEYS


def test_max_url_stays_below_the_measured_limit():
    assert MAX_URL <= 6920 - 500  # results/README.md: 302 up to 6920, 500 from 6982


def test_real_issue_from_the_form(queue):
    """Issue #1, sent from the page through the form: GitHub's body decodes and applies."""
    event = json.loads((FIXTURES / "issue_opened_1.json").read_text("utf-8"))
    issue = event["issue"]
    block = decode(issue["body"])
    assert (block.page, block.part) == ("public", (1, 1))
    assert [d["action"] for d in block.decisions] == ["pick", "set_grade", "approve"]
    intake = {
        "reviewed_by": issue["user"]["login"],
        "reviewed_at": issue["created_at"],
        "source": f"issue#{issue['number']}",
    }
    for d in block.decisions:
        assert check_against(Decision.model_validate(d | intake), queue) == []


def test_send_id_is_optional_and_round_trips():
    d = {"item_type": "glossary", "item_id": "gaba", "content_sha256": "x" * 64,
         "action": "approve", "payload": {}, "note": None}  # fmt: skip
    assert decode(encode("q", "public", [d], (2, 4), "3f9a01c2")).send == "3f9a01c2"
    assert decode(encode("q", "public", [d], (2, 4))).send is None


def test_a_wrong_send_id_is_refused():
    body = "synaptica-review v1\nqueue: q\npage: public\npart: 1/2\nsend: nope\n{}"
    with pytest.raises(BlockError, match="send"):
        decode(body)
