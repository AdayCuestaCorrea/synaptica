"""The test with Sofía (spike S4, step 6): its queue, its tools, and a dry run of what
GUION.md promises for round 2. Without network."""

import json
from pathlib import Path

from event_from_issue import to_event
from intake import process, write
from issue_block import encode
from models import ItemType, Queue
from ronda import round_pages

PRUEBA = Path(__file__).parents[1] / "prueba"
FIXTURES = Path(__file__).parents[3] / "tests" / "fixtures" / "review"
T7 = "El seguimiento se repetirá en 2031."


def _queue() -> Queue:
    return Queue.model_validate_json((PRUEBA / "queue.json").read_text("utf-8"))


def test_committed_queue_is_what_make_queue_builds():
    import sys

    sys.path.insert(0, str(PRUEBA))
    from make_queue import test_queue

    assert _queue() == test_queue()


def test_round_1_pages_have_everything_pending():
    queue = _queue()
    assert len(queue.items) == 19
    html = (PRUEBA / "ronda-1" / "revision.html").read_text("utf-8")
    assert html.count('"item_type": "') == 18  # all but the private sheet
    private = (PRUEBA / "ronda-1" / "revision-privada.html").read_text("utf-8")
    assert '"item_type": "disease"' in private and '"item_type": "news"' not in private


def test_to_event_matches_the_fixture_shape():
    gh = {"number": 1, "title": "Revisión de Sofía · 2026-11-11 · 1/1",
          "author": {"id": "x", "is_bot": False, "login": "AdayCuestaCorrea", "name": "A"},
          "createdAt": "2026-11-11T17:15:14Z",
          "labels": [{"id": "y", "name": "revisión", "description": "", "color": "2c5d8f"}],
          "body": "### Decisiones\n\n```text\n…\n```"}  # fmt: skip
    fixture = json.loads((FIXTURES / "issue_opened_1.json").read_text("utf-8"))
    event = to_event(gh)
    assert event["issue"].keys() <= fixture["issue"].keys()
    assert event["issue"]["user"] == {"login": "AdayCuestaCorrea"}
    assert event["issue"]["labels"] == [{"name": "revisión"}]


def test_dry_run_of_the_two_rounds(tmp_path):
    """What GUION.md says will happen: T6 and the rest settle, T7 comes back with warnings."""
    queue = _queue()
    news = {pmid: queue.get(ItemType.NEWS, f"pubmed-{pmid}") for pmid in ("42971231", "42997796")}

    def d(item, action, payload=None):
        return {"item_type": item.item_type.value, "item_id": item.item_id,
                "content_sha256": item.content_sha256, "action": action,
                "payload": payload or {}, "note": None}  # fmt: skip

    t6 = [s.text for s in news["42971231"].content.es]
    t6[3] = "Estos resultados no muestran más defectos del tubo neural con dolutegravir."
    t7 = [s.text for s in news["42997796"].content.es] + [T7]
    gaba = queue.get(ItemType.GLOSSARY, "gaba")
    decisions = [d(news["42971231"], "edit", {"es": "\n".join(t6)}),
                 d(news["42997796"], "edit", {"es": "\n".join(t7)}),
                 d(gaba, "approve")]  # fmt: skip
    body = f"### Decisiones\n\n```text\n{encode('x', 'public', decisions)}\n```"
    event = {"action": "opened", "issue": {"number": 20, "user": {"login": "sofia"},
             "created_at": "2026-11-20T18:00:00Z", "body": body}}  # fmt: skip
    out = process(event, queue, "sofia")
    write(out, tmp_path / "datos")
    assert [x.item_id for x in out.applied] == ["pubmed-42971231", "gaba"]

    waiting, sts = round_pages(queue, tmp_path / "datos", tmp_path / "ronda-2")
    keys = {i.key for i in waiting.items}
    assert ("news", "pubmed-42971231") not in keys and ("glossary", "gaba") not in keys
    t7_item = waiting.get(ItemType.NEWS, "pubmed-42997796")
    assert t7_item.warnings == [
        "(español) La cifra 2031 no está en el texto revisado ni en su fuente.",
        f"(español) Frase nueva sin fuente: «{T7}».",
    ]
    assert sts[("news", "pubmed-42971231")].awaiting_en  # the English is rewritten by the LLM
    assert len(waiting.items) == 19 - 2  # T6 and GABA settled; T7 back with its warnings
    assert "Vuelve a tu cola por esto" in (tmp_path / "ronda-2" / "revision.html").read_text()
