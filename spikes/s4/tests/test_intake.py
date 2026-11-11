"""Intake of review Issues (spike S4, step 4) on the fixtures, without network."""

import json
import re

import pytest
from intake import _done_sources, edit_warnings, process, reply, sentences, write
from issue_block import encode
from models import ItemType, Queue, ReviewItem

from conftest import FIXTURES

SOFIA = "sofia-test"
NEWS = (ItemType.NEWS, "pubmed-42971231")


@pytest.fixture
def queue() -> Queue:
    return Queue.model_validate_json((FIXTURES / "queue.json").read_text("utf-8"))


@pytest.fixture
def real_issue() -> dict:
    return json.loads((FIXTURES / "issue_opened_1.json").read_text("utf-8"))


def _event(decisions: list[dict], number: int = 7, page: str = "public", login: str = SOFIA):
    body = f"### Decisiones\n\n```text\n{encode('2026-11-11T06:00:00Z', page, decisions)}\n```"
    return {"action": "opened", "issue": {
        "number": number, "title": "Revisión de Sofía", "user": {"login": login},
        "created_at": "2026-11-12T20:30:00Z", "labels": [{"name": "revisión"}], "body": body,
    }}  # fmt: skip


def _d(queue: Queue, item: tuple, action: str, payload: dict | None = None, **kw) -> dict:
    it = queue.get(*item)
    return {"item_type": item[0].value, "item_id": item[1],
            "content_sha256": it.content_sha256 if it else None,
            "action": action, "payload": payload or {}, "note": None} | kw  # fmt: skip


def _es(queue: Queue) -> list[str]:
    return [s.text for s in queue.get(*NEWS).content.es]


# ---- who may write -------------------------------------------------------------------


def test_real_issue_by_the_reviewer_is_applied(real_issue, queue):
    out = process(real_issue, queue, "AdayCuestaCorrea")
    assert out.status == "processed" and not out.refused and not out.held
    assert [d.action.value for d in out.applied] == ["pick", "set_grade", "approve"]
    d = out.applied[0]
    assert (d.reviewed_by, d.source) == ("AdayCuestaCorrea", "issue#1")
    assert d.reviewed_at.isoformat() == "2026-11-11T17:15:14+00:00"


def test_anyone_else_is_ignored(real_issue, queue):
    out = process(real_issue, queue, SOFIA)
    assert out.status == "ignored" and not out.applied


def test_login_comparison_ignores_case(real_issue, queue):
    assert process(real_issue, queue, "adaycuestacorrea").status == "processed"


def test_only_opened_issues(real_issue, queue):
    assert process(real_issue | {"action": "edited"}, queue, "AdayCuestaCorrea").status == "ignored"


def test_the_same_issue_twice_adds_nothing(real_issue, queue, tmp_path):
    first = process(real_issue, queue, "AdayCuestaCorrea")
    write(first, tmp_path)
    done = _done_sources(tmp_path)
    assert done == {"issue#1"}
    assert process(real_issue, queue, "AdayCuestaCorrea", done=done).status == "duplicate"


def test_a_broken_block_is_refused_whole(queue):
    event = _event([])
    event["issue"]["body"] = "### Decisiones\n\n_No response_"
    out = process(event, queue, SOFIA)
    assert out.status == "refused" and "no SYNAPTICA review block" in out.reason
    assert "no se ha aplicado nada" in reply(out, {})


# ---- each decision -------------------------------------------------------------------


def test_stale_and_unknown_decisions_are_refused_and_the_rest_applied(queue):
    good = _d(queue, (ItemType.GLOSSARY, "gaba"), "approve")
    stale = good | {"item_id": "snr"}  # gaba's hash on snr
    unknown = good | {"item_id": "nope"}
    out = process(_event([good, stale, unknown]), queue, SOFIA)
    assert [d.item_id for d in out.applied] == ["gaba"]
    assert out.refused == [
        ("glossary/snr", "stale: the item changed after she reviewed it"),
        ("glossary/nope", "unknown item glossary/nope"),
    ]


def test_invalid_decision_is_refused_with_the_reason(queue):
    bad = _d(queue, (ItemType.EQUIVALENCE, "waxholm-1021"), "set_grade", {"grade": "clara"})
    out = process(_event([bad]), queue, SOFIA)
    assert out.refused[0][0] == "equivalence/waxholm-1021" and "clear" in out.refused[0][1]


def test_private_item_from_the_public_page_is_refused(queue):
    d = _d(queue, (ItemType.DISEASE, "test-placeholder"), "approve")
    assert process(_event([d]), queue, SOFIA).refused[0][1].startswith("private item")
    assert process(_event([d], page="private"), queue, SOFIA).applied


def test_keep_needs_a_warning(queue):
    keep = _d(queue, NEWS, "keep", {"reason": "La mantengo."})
    assert "nothing to keep" in process(_event([keep]), queue, SOFIA).refused[0][1]
    raw = queue.model_dump(mode="json")
    news = next(i for i in raw["items"] if i["item_id"] == NEWS[1])
    news["warnings"] = ["(español) La cifra 7 no está en el texto revisado ni en su fuente."]
    warned = Queue.model_validate(raw)
    assert process(_event([keep]), warned, SOFIA).applied  # same hash: warnings are not hashed


# ---- her edits -----------------------------------------------------------------------


def test_light_edit_passes(queue):
    es = _es(queue)
    es[3] = "Estos hallazgos sugieren que el dolutegravir no aumenta el riesgo durante el embarazo."
    out = process(_event([_d(queue, NEWS, "edit", {"es": "\n".join(es)})]), queue, SOFIA)
    assert out.applied and not out.held
    assert "en" not in out.applied[0].payload  # the English is rewritten by the pipeline


def test_a_new_number_is_held(queue):
    es = _es(queue)
    es[2] = es[2].replace("162", "126")
    out = process(_event([_d(queue, NEWS, "edit", {"es": "\n".join(es)})]), queue, SOFIA)
    assert not out.applied
    assert out.held[0].warnings == [
        "(español) La cifra 126 no está en el texto revisado ni en su fuente."
    ]


def test_a_new_name_is_held(queue):
    es = [*_es(queue), "Lo confirmó la Organización Mundial de la Salud."]
    w = edit_warnings(queue.get(*NEWS), {"es": "\n".join(es)}, {})
    assert "(español) «Organización» no aparece en el texto revisado ni en su fuente." in w
    assert any(x.startswith("(español) Frase nueva sin fuente: «Lo confirmó") for x in w)


def test_a_number_or_name_from_the_source_is_fine(queue):
    es = [*_es(queue), "El seguimiento empezó en Gaborone."]
    source = {"pubmed-42971231": "Surveillance started in Gaborone in 2014 at eight hospitals."}
    w = edit_warnings(queue.get(*NEWS), {"es": "\n".join(es)}, source)
    assert not [x for x in w if "Gaborone" in x and "no aparece" in x]


def test_copying_eight_words_from_the_source_is_held(queue):
    source = "The prevalence of neural tube defects remained low across every exposure group."
    en = [s.text for s in queue.get(*NEWS).content.en]
    en[3] = "The prevalence of neural tube defects remained low across every exposure group."
    w = edit_warnings(queue.get(*NEWS), {"en": "\n".join(en)}, {"pubmed-42971231": source})
    assert any(x.startswith("(inglés) Copia 8 palabras seguidas de la fuente") for x in w)


def test_items_without_sources_skip_the_citation_check(queue):
    item = queue.get(ItemType.DISEASE, "test-placeholder")
    assert edit_warnings(item, {"es": "Otra frase de prueba distinta."}, {}) == []


def test_terms_edits_have_no_text_checks(queue):
    d = _d(queue, (ItemType.SEARCH_TERMS, "waxholm-1021"), "edit", {"terms": ["hippocampus"]})
    assert process(_event([d]), queue, SOFIA).applied


def test_sentences_split_on_lines_and_full_stops():
    assert sentences("Uno. Dos.\nTres\n\n¿Cuatro? «Cinco».") == [
        "Uno.", "Dos.", "Tres", "¿Cuatro?", "«Cinco»."
    ]  # fmt: skip


# ---- the judge only advises ----------------------------------------------------------


def test_the_judge_never_blocks(queue):
    es = _es(queue)
    es[3] = "Estos hallazgos sugieren que el dolutegravir no aumenta el riesgo durante el embarazo."

    def judge(item: ReviewItem, decision) -> list[str]:
        return ["Puede sonar a consejo médico."]

    out = process(_event([_d(queue, NEWS, "edit", {"es": "\n".join(es)})]), queue, SOFIA,
                  judge=judge)  # fmt: skip
    assert out.applied and out.advice == [("news/pubmed-42971231", "Puede sonar a consejo médico.")]
    assert "no bloquea nada" in reply(out, {})


# ---- reply and files -----------------------------------------------------------------


def test_reply_in_spanish_with_titles(queue):
    es = _es(queue)
    es[2] = es[2].replace("162", "126")
    stale = _d(queue, (ItemType.GLOSSARY, "gaba"), "approve") | {"item_id": "snr"}
    out = process(_event([_d(queue, NEWS, "edit", {"es": "\n".join(es)}), stale]), queue, SOFIA)
    titles = {f"{i.item_type}/{i.item_id}": i.title_es for i in queue.items}
    text = reply(out, titles)
    assert text.startswith("Aplicadas: 0.")
    assert "- Resumen de S5: dolutegravir y defectos del tubo neural" in text
    assert "La cifra 126" in text
    assert "- SNr: el texto cambió después de que lo vieras" in text


def test_files_are_append_only(real_issue, queue, tmp_path):
    out = process(real_issue, queue, "AdayCuestaCorrea")
    write(out, tmp_path)
    es = _es(queue)
    es[2] = es[2].replace("162", "126")
    write(process(_event([_d(queue, NEWS, "edit", {"es": "\n".join(es)})]), queue, SOFIA), tmp_path)
    assert len((tmp_path / "decisions.jsonl").read_text().splitlines()) == 3
    held = [json.loads(x) for x in (tmp_path / "held.jsonl").read_text().splitlines()]
    assert held[0]["decision"]["source"] == "issue#7" and held[0]["warnings"]
    assert _done_sources(tmp_path) == {"issue#1", "issue#7"}


# ---- the workflow draft and the command ----------------------------------------------


def test_workflow_never_puts_issue_text_in_a_script():
    """Only numbers and the login (checked) go through ${{ }}; text comes from the event file."""
    path = FIXTURES.parents[2] / "spikes" / "s4" / "review-intake.yml"
    code = [x for x in path.read_text("utf-8").splitlines() if not x.lstrip().startswith("#")]
    used = {m for line in code for m in re.findall(r"\$\{\{\s*([^}]+?)\s*\}\}", line)}
    assert used == {"vars.REVIEWER_LOGIN", "github.event.issue.number", "github.token",
                    "steps.intake.outputs.status"}  # fmt: skip


def test_command_end_to_end(real_issue, tmp_path, monkeypatch, capsys):
    import intake

    (tmp_path / "event.json").write_text(json.dumps(real_issue), encoding="utf-8")
    args = ["intake.py", "--event", str(tmp_path / "event.json"),
            "--queue", str(FIXTURES / "queue.json"), "--data-dir", str(tmp_path / "data"),
            "--reviewer", "AdayCuestaCorrea", "--reply", str(tmp_path / "reply.md")]  # fmt: skip
    monkeypatch.setattr("sys.argv", args)
    intake.main()
    intake.main()  # idempotent
    lines = capsys.readouterr().out.splitlines()
    assert [json.loads(x)["status"] for x in lines] == ["processed", "duplicate"]
    assert len((tmp_path / "data" / "decisions.jsonl").read_text().splitlines()) == 3
    assert (tmp_path / "reply.md").read_text().startswith("Aplicadas: 3.")


# ---- aligning her sentences with the reviewed ones -----------------------------------


@pytest.mark.parametrize(
    ("new", "expected"),
    [
        (["A uno.", "B dos.", "C tres."], [0, 1, 2]),  # unchanged
        (["A uno.", "Otra cosa distinta.", "C tres."], [0, 1, 2]),  # rewritten in place
        (["A uno.", "Nueva.", "B dos.", "C tres."], [0, None, 1, 2]),  # inserted
        (["A uno.", "C tres."], [0, 2]),  # deleted
        (["A uno.", "B dos", "Añadida al final.", "C tres."], [0, 1, None, 2]),
    ],
)
def test_align(new, expected):
    from intake import align

    assert align(["A uno.", "B dos.", "C tres."], new) == expected


def test_a_short_fix_is_not_a_new_sentence(queue):
    """Seen in the S4 dry run: shortening the overstated sentence scored below 0.5."""
    es = _es(queue)
    es[3] = "Estos resultados no muestran más defectos del tubo neural con dolutegravir."
    assert edit_warnings(queue.get(*NEWS), {"es": "\n".join(es)}, {}) == []
