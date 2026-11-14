"""Every open review Issue on each run (the fix for the runs GitHub cancelled on
2026-11-14), on the fixtures, without network."""

import json
import re
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from synaptica.review.issue_block import encode
from synaptica.review.models import ItemType, Queue
from synaptica.review.sweep import WAITING, marker, open_events, sweep

FIXTURES = Path(__file__).parent / "fixtures" / "review"
WORKFLOW = FIXTURES.parents[2] / ".github" / "workflows" / "review-intake.yml"
REVIEWER = "AdayCuestaCorrea"  # the author of the real Issue in the fixture
NEWS = (ItemType.NEWS, "pubmed-42971231")


def _listed(number: int, body: str, login: str = REVIEWER, labels=("revisión",), comments=()):
    """An Issue as `gh issue list --json number,title,body,author,createdAt,labels,comments`."""
    return {"number": number, "title": f"Revisión de Sofía · {number}", "body": body,
            "author": {"login": login}, "createdAt": "2026-11-14T18:34:15Z",
            "labels": [{"name": x} for x in labels],
            "comments": [{"author": {"login": "github-actions"}, "body": c}
                         for c in comments]}  # fmt: skip


@pytest.fixture
def real_body() -> str:
    return json.loads((FIXTURES / "issue_opened_1.json").read_text("utf-8"))["issue"]["body"]


@pytest.fixture
def edit_body() -> str:
    """An edit of a study summary: its abstract is not in the (empty) cache, so it waits."""
    queue = Queue.model_validate_json((FIXTURES / "queue.json").read_text("utf-8"))
    item = queue.get(*NEWS)
    decision = {"item_type": NEWS[0].value, "item_id": NEWS[1],
                "content_sha256": item.content_sha256, "action": "edit",
                "payload": {"es": "\n".join(s.text for s in item.content.es)},
                "note": None}  # fmt: skip
    block = encode("2026-11-11T06:00:00Z", "public", [decision])
    return f"### Decisiones\n\n```text\n{block}\n```"


@pytest.fixture
def dirs(tmp_path) -> dict:
    queues = tmp_path / "review-queues"
    queues.mkdir()
    shutil.copy(FIXTURES / "queue.json", queues / "queue-2026-11-11.json")
    return {"queue_dir": queues, "data_dir": tmp_path / "data", "reviewer": REVIEWER,
            "cache_root": tmp_path / "empty-cache"}  # fmt: skip


def _decisions(data_dir: Path) -> list[str]:
    path = data_dir / "decisions.jsonl"
    return path.read_text("utf-8").splitlines() if path.exists() else []


def test_only_her_open_review_issues_oldest_first(real_body):
    events = open_events([
        _listed(13, real_body), _listed(11, real_body),
        _listed(12, real_body, login="stranger"),
        _listed(14, real_body, labels=("bug",)),
        _listed(15, real_body, login=REVIEWER.lower()),  # the login is compared without case
    ], REVIEWER)  # fmt: skip
    assert [e["issue"]["number"] for e, _ in events] == [11, 13, 15]
    issue = events[0][0]["issue"]
    assert events[0][0]["action"] == "opened"
    assert issue["user"] == {"login": REVIEWER} and issue["created_at"] == "2026-11-14T18:34:15Z"


def test_a_run_picks_up_issues_whose_runs_were_cancelled(real_body, dirs, tmp_path):
    """Two Issues open, one run: both are read; the second one's decisions were already
    recorded by the first (she sent the same part twice), so nothing is applied twice."""
    plan = sweep([_listed(12, real_body), _listed(11, real_body)], out_dir=tmp_path / "o", **dirs)
    assert [(r["number"], r["status"], r["close"]) for r in plan] == [
        (11, "processed", True), (12, "processed", True)]  # fmt: skip
    assert plan[0]["result"]["applied"] == 3
    assert plan[1]["result"]["repeated"] == 3
    assert len(_decisions(dirs["data_dir"])) == 3
    reply = (tmp_path / "o" / plan[0]["reply"]).read_text("utf-8")
    assert reply.startswith("Aplicadas: 3.") and marker("processed") in reply
    assert json.loads((tmp_path / "o" / "plan.json").read_text("utf-8")) == plan


def test_an_issue_without_its_source_waits_with_a_plain_notice(edit_body, dirs, tmp_path):
    plan = sweep([_listed(11, edit_body)], out_dir=tmp_path / "o", **dirs)
    assert [(r["status"], r["close"]) for r in plan] == [("error", False)]
    reply = (tmp_path / "o" / plan[0]["reply"]).read_text("utf-8")
    assert reply.startswith(WAITING) and marker("error") in reply
    assert not _decisions(dirs["data_dir"])


def test_the_notice_is_not_posted_twice(edit_body, dirs, tmp_path):
    """The waiting Issue stays open and every run reads it again."""
    first = sweep([_listed(11, edit_body)], out_dir=tmp_path / "a", **dirs)
    posted = (tmp_path / "a" / first[0]["reply"]).read_text("utf-8")
    again = sweep([_listed(11, edit_body, comments=[posted])], out_dir=tmp_path / "b", **dirs)
    assert [(r["status"], r["reply"], r["close"]) for r in again] == [("error", None, False)]


def test_one_waiting_issue_does_not_stop_the_others(real_body, edit_body, dirs, tmp_path):
    plan = sweep([_listed(11, edit_body), _listed(12, real_body)], out_dir=tmp_path / "o", **dirs)
    assert [(r["number"], r["status"]) for r in plan] == [(11, "error"), (12, "processed")]
    assert len(_decisions(dirs["data_dir"])) == 3


def test_an_issue_recorded_but_left_open_is_closed_without_a_new_reply(real_body, dirs, tmp_path):
    """A run recorded it and then failed to close it: the next run only closes it."""
    first = sweep([_listed(11, real_body)], out_dir=tmp_path / "a", **dirs)
    posted = (tmp_path / "a" / first[0]["reply"]).read_text("utf-8")
    again = sweep([_listed(11, real_body, comments=[posted])], out_dir=tmp_path / "b", **dirs)
    assert [(r["status"], r["reply"], r["close"]) for r in again] == [("duplicate", None, True)]
    assert len(_decisions(dirs["data_dir"])) == 3  # idempotent


def test_without_its_queue_the_issue_waits(real_body, dirs, tmp_path):
    for q in dirs["queue_dir"].iterdir():
        q.unlink()
    plan = sweep([_listed(11, real_body)], out_dir=tmp_path / "o", **dirs)
    assert [(r["status"], r["close"]) for r in plan] == [("error", False)]
    assert "no tienes que volver a enviarla" in (tmp_path / "o" / plan[0]["reply"]).read_text()


def test_syn_review_sweep_exits_2_when_an_issue_waits(edit_body, dirs, tmp_path, monkeypatch):
    from synaptica.cli import app

    monkeypatch.setenv("SYN_DATA_DIR", str(tmp_path / "syn"))
    issues = tmp_path / "issues.json"
    issues.write_text(json.dumps([_listed(11, edit_body)]), encoding="utf-8")
    args = ["review", "sweep", "--issues", str(issues), "--queue-dir", str(dirs["queue_dir"]),
            "--reviewer", REVIEWER, "--out", str(tmp_path / "o"),
            "--cache-root", str(dirs["cache_root"])]  # fmt: skip
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 2, result.output
    assert json.loads(result.output.splitlines()[0])["status"] == "error"


# ---- the workflow --------------------------------------------------------------------


def _code(path: Path) -> list[str]:
    return [x for x in path.read_text("utf-8").splitlines() if not x.lstrip().startswith("#")]


def test_the_workflow_never_puts_issue_text_in_a_script():
    """Only the login, the token, ids and the numbers the code chose go through ${{ }}."""
    used = {m for line in _code(WORKFLOW) for m in re.findall(r"\$\{\{\s*([^}]+?)\s*\}\}", line)}
    assert used == {"vars.REVIEWER_LOGIN", "github.token", "github.workspace", "github.run_id",
                    "steps.intake.outputs.processed"}  # fmt: skip
    text = "\n".join(_code(WORKFLOW))
    assert not re.search(r"issue\.(body|title)|comment\.body", text)


def test_the_workflow_keeps_least_privilege_and_the_reviewer_check():
    text = "\n".join(_code(WORKFLOW))
    perms = re.search(r"^permissions:\n((?:  .+\n)+)", text + "\n", re.M).group(1)
    assert sorted(perms.split()) == sorted(["contents:", "write", "issues:", "write"])
    assert "github.event.issue.user.login == vars.REVIEWER_LOGIN" in text
    assert "vars.REVIEWER_LOGIN != ''" in text
    assert '--author "$REVIEWER"' in text and "--label revisión" in text
    assert "syn review sweep" in text and "cancel-in-progress: false" in text
