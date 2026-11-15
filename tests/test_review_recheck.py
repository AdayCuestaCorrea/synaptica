"""Reviewed paragraphs aligned sentence by sentence, and `syn review recheck-held` (seen on
2026-11-14: two of her edits held by a false «frase nueva sin fuente»). Without network."""

import datetime as dt
import json
from pathlib import Path

import pytest

from synaptica.review import recheck
from synaptica.review.apply import edited_text, read_log, state
from synaptica.review.intake import Held, Outcome, _align, align, edit_warnings, process, write
from synaptica.review.issue_block import encode
from synaptica.review.models import Action, Decision, ItemType, Queue

FIXTURES = Path(__file__).parent / "fixtures" / "review"
NEWS = (ItemType.NEWS, "pubmed-42971231")
SOURCE = {"pubmed-42971231": "Fine particles (PM2.5) were measured."}
NOW = dt.datetime(2026, 11, 15, 9, 0, tzinfo=dt.UTC)
WARN = ["(español) Frase nueva sin fuente: «El trabajo siguió a 11 110 bebés…»."]


@pytest.fixture
def queue() -> Queue:
    """The fixture queue with its Spanish stored as two paragraphs (as the qwen9b batch)."""
    raw = json.loads((FIXTURES / "queue.json").read_text("utf-8"))
    item = next(i for i in raw["items"] if i["item_id"] == NEWS[1])
    es = item["content"]["es"]
    item["content"]["es"] = [
        {"text": f"{es[0]['text']} {es[1]['text']}", "cites": es[0]["cites"]},
        {"text": f"{es[2]['text']} {es[3]['text']}", "cites": es[2]["cites"]},
    ]
    return Queue.model_validate(raw)


def _lines(queue: Queue) -> list[str]:
    """Her page: one sentence per line."""
    raw = json.loads((FIXTURES / "queue.json").read_text("utf-8"))
    item = next(i for i in raw["items"] if i["item_id"] == NEWS[1])
    return [s["text"] for s in item["content"]["es"]]


def _her_edit(queue: Queue) -> dict:
    es = _lines(queue)
    es[1] = es[1].replace("El estudio siguió", "El trabajo siguió")
    return {"es": "\n".join(es)}


def _held(queue: Queue, data_dir: Path, payload: dict, n: int = 11) -> Decision:
    """A held edit in the log, as the intake wrote it before the fix."""
    item = queue.get(*NEWS)
    d = Decision(item_type=NEWS[0], item_id=NEWS[1], content_sha256=item.content_sha256,
                 action="edit", payload=payload, reviewed_by="sofia-test",
                 reviewed_at=dt.datetime(2026, 11, 14, 18, 34, tzinfo=dt.UTC),
                 source=f"issue#{n}")  # fmt: skip
    write(Outcome("processed", held=[Held(d, WARN)]), data_dir)
    return d


# ---- align ---------------------------------------------------------------------------


def test_a_paragraph_is_aligned_as_its_sentences():
    old = ["Uno primero largo. Dos segundo largo.", "Tres tercero largo."]
    new = ["Uno primero largo.", "Dos segundo corto.", "Nueva frase.", "Tres tercero largo."]
    assert align(old, new) == [0, 0, None, 1]


def test_her_lines_against_the_paragraphs_were_held_before(queue):
    """The bug itself: compared with the whole paragraph, a lightly fixed sentence of a
    real qwen9b-like text matched nothing (kept as a regression guard of the test)."""
    old = [s.text for s in queue.get(*NEWS).content.es]
    mine = _her_edit(queue)["es"].split("\n")
    assert None in _align(old, mine) and None not in align(old, mine)


def test_a_light_fix_inside_a_paragraph_passes(queue):
    assert edit_warnings(queue.get(*NEWS), _her_edit(queue), SOURCE) == []


def test_her_sentences_inherit_the_paragraph_cites(queue):
    text = edited_text(queue.get(*NEWS).content, _her_edit(queue))
    assert len(text.es) == 4 and all(s.cites == ["pubmed-42971231"] for s in text.es)


def test_an_added_sentence_is_still_new(queue):
    es = _lines(queue)
    es.insert(2, "Además, los bebés crecieron sanos durante años.")
    w = edit_warnings(queue.get(*NEWS), {"es": "\n".join(es)}, SOURCE)
    assert w == [
        "(español) Frase nueva sin fuente: «Además, los bebés crecieron sanos durante años.»."
    ]


# ---- recheck-held --------------------------------------------------------------------


def test_a_false_positive_is_released_as_her_decision(queue, tmp_path):
    held = _held(queue, tmp_path, _her_edit(queue))
    out = recheck.run(tmp_path, queue, SOURCE, NOW)
    assert out == {"released": [NEWS[1]], "held": [], "without_source": []}
    row = json.loads((tmp_path / "decisions.jsonl").read_text("utf-8"))
    assert row == held.model_dump(mode="json") | {"rechecked_at": "2026-11-15T09:00:00Z"}
    st = state(queue.get(*NEWS), read_log(tmp_path))
    assert st.status == "edited" and st.held is None and st.reviewed_by == "sofia-test"


def test_recheck_twice_adds_nothing(queue, tmp_path):
    _held(queue, tmp_path, _her_edit(queue))
    recheck.run(tmp_path, queue, SOURCE, NOW)
    assert recheck.run(tmp_path, queue, SOURCE, NOW)["released"] == []
    assert len((tmp_path / "decisions.jsonl").read_text("utf-8").splitlines()) == 1


def test_an_edit_that_still_fails_stays_held(queue, tmp_path):
    es = _lines(queue)
    es[1] = es[1].replace("11 110", "12 000")
    _held(queue, tmp_path, {"es": "\n".join(es)})
    assert recheck.run(tmp_path, queue, SOURCE, NOW)["held"] == [NEWS[1]]
    assert not (tmp_path / "decisions.jsonl").read_text("utf-8")


def test_without_source_text_nothing_is_released(queue, tmp_path):
    """The copy check needs the abstract: no text, no release (the command exits 2)."""
    _held(queue, tmp_path, _her_edit(queue))
    assert recheck.run(tmp_path, queue, {}, NOW)["without_source"] == [NEWS[1]]
    assert not (tmp_path / "decisions.jsonl").read_text("utf-8")


def test_an_edit_she_already_answered_is_left_alone(queue, tmp_path):
    held = _held(queue, tmp_path, _her_edit(queue))
    later = held.model_copy(update={"action": Action.REJECT, "payload": {}, "source": "issue#20",
                                    "reviewed_at": NOW})  # fmt: skip
    write(Outcome("processed", applied=[later]), tmp_path)
    assert recheck.run(tmp_path, queue, SOURCE, NOW) == {
        "released": [], "held": [], "without_source": []}  # fmt: skip


# ---- the intake never lets an Issue set it --------------------------------------------


def test_an_issue_cannot_claim_a_recheck(queue, tmp_path):
    item = queue.get(*NEWS)
    raw = {"item_type": "news", "item_id": NEWS[1], "content_sha256": item.content_sha256,
           "action": "approve", "payload": {}, "note": None,
           "rechecked_at": "2026-01-01T00:00:00Z"}  # fmt: skip
    body = f"```text\n{encode('2026-11-11T06:00:00Z', 'public', [raw])}\n```"
    event = {"action": "opened", "issue": {"number": 30, "user": {"login": "sofia-test"},
             "created_at": "2026-11-15T08:00:00Z", "body": body}}  # fmt: skip
    out = process(event, queue, "sofia-test")
    assert out.applied and out.applied[0].rechecked_at is None
    write(out, tmp_path)
    assert "rechecked_at" not in (tmp_path / "decisions.jsonl").read_text("utf-8")


def test_syn_review_recheck_held(queue, tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from synaptica.cli import app

    monkeypatch.setenv("SYN_DATA_DIR", str(tmp_path / "data"))
    _held(queue, tmp_path / "data" / "review", _her_edit(queue))
    (tmp_path / "q.json").write_text(queue.model_dump_json(), encoding="utf-8")
    efetch = tmp_path / "efetch.xml"
    efetch.write_text(
        "<PubmedArticleSet><PubmedArticle><MedlineCitation><PMID>42971231</PMID><Article>"
        "<Abstract><AbstractText>Fine particles (PM2.5) were measured.</AbstractText>"
        "</Abstract></Article></MedlineCitation></PubmedArticle></PubmedArticleSet>",
        encoding="utf-8",
    )
    args = ["review", "recheck-held", "--queue", str(tmp_path / "q.json"),
            "--cache-root", str(tmp_path / "cache")]  # fmt: skip
    runner = CliRunner()
    assert runner.invoke(app, args).exit_code == 2  # no abstract: nothing released
    result = runner.invoke(app, [*args, "--efetch", str(efetch)])
    assert result.exit_code == 0 and json.loads(result.stdout)["released"] == [NEWS[1]]
