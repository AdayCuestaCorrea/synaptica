"""Every open review Issue of hers, in number order, on each run of the intake workflow.

Why (seen on 2026-11-14): GitHub keeps at most one *pending* run per concurrency group, so
when she sent five parts in twenty seconds two runs were cancelled and their Issues (#12,
#13) stayed open with nothing applied. Now each run reads all her open Issues with the
label, oldest number first, and the last run picks up whatever an earlier one missed.

Nothing here talks to GitHub: the workflow passes the output of ``gh issue list --json
number,title,body,author,createdAt,labels,comments`` and acts on ``plan.json`` (comment,
close). Each Issue goes through ``intake.run``, so the deduplication is the existing one:
an Issue already recorded is a ``duplicate`` and a decision already recorded is
``repeated``. Running the sweep twice adds nothing.

Every comment carries a hidden marker with its status, and a comment is not posted again
when the Issue already has one with that marker: an Issue that waits for Aday stays open
and is read again by every run, and it must not collect a copy of the notice each time.
"""

from __future__ import annotations

import json
from pathlib import Path

from synaptica.review.intake import queue_for, run

LABEL = "revisión"
WAITING = "Esta parte la procesa Aday a mano; no tienes que volver a enviarla."
NO_QUEUE = ("No encuentro la página de revisión de la que viene esta parte. "
            "Aday la mira a mano; no tienes que volver a enviarla.")  # fmt: skip


def marker(status: str) -> str:
    return f"<!-- syn-intake:{status} -->"


def open_events(issues: list[dict], reviewer: str) -> list[tuple[dict, list[str]]]:
    """Her open review Issues as ``issues: opened`` events, with their comments' bodies.

    Only her login and the label count (the same checks as the workflow's ``if``; the
    intake checks the author once more). Issues come from ``gh issue list``, whose fields
    are renamed to the webhook payload's (``author`` → ``user``, ``createdAt`` →
    ``created_at``).
    """
    out = []
    for issue in issues:
        login = (issue.get("author") or {}).get("login") or ""
        labels = issue.get("labels") or []
        if login.lower() != reviewer.lower() or LABEL not in {x.get("name") for x in labels}:
            continue
        event = {"action": "opened", "issue": {
            "number": int(issue["number"]), "title": issue.get("title") or "",
            "user": {"login": login}, "created_at": issue["createdAt"],
            "labels": labels, "body": issue.get("body") or "",
        }}  # fmt: skip
        comments = [c.get("body") or "" for c in issue.get("comments") or []]
        out.append((event, comments))
    return sorted(out, key=lambda x: x[0]["issue"]["number"])


def sweep(
    issues: list[dict],
    queue_dir: Path,
    data_dir: Path,
    reviewer: str,
    out_dir: Path,
    cache_root: Path | None = None,
    efetch: list[Path] | None = None,
) -> list[dict]:
    """Process her open Issues one by one; write ``plan.json`` and the replies in ``out_dir``.

    Each row of the plan: ``number``, ``status`` (processed | refused | duplicate | error),
    ``reply`` (a file name in ``out_dir``, or None: nothing to post) and ``close``.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    plan = []
    for event, comments in open_events(issues, reviewer):
        n = event["issue"]["number"]
        event_path, reply_path = out_dir / f"event-{n}.json", out_dir / f"reply-{n}.md"
        event_path.write_text(json.dumps(event, ensure_ascii=False), encoding="utf-8")
        queue = queue_for(event_path, queue_dir)
        if queue is None:
            result = {"status": "error", "no_queue": True}
            reply_path.write_text(NO_QUEUE + "\n", encoding="utf-8")
        else:
            result = run(event_path, queue, data_dir, reviewer, reply_path,
                         cache_root=cache_root, efetch=efetch)  # fmt: skip
        status = result["status"]
        if status == "error" and queue is not None:
            reply_path.write_text(WAITING + "\n", encoding="utf-8")
        reply = None
        posted = any(marker(status) in c for c in comments)
        if status in ("processed", "refused", "error") and reply_path.exists() and not posted:
            text = reply_path.read_text("utf-8").rstrip("\n")
            reply_path.write_text(f"{text}\n\n{marker(status)}\n", encoding="utf-8")
            reply = reply_path.name
        # A duplicate was recorded by an earlier run that could not close it.
        plan.append({"number": n, "status": status, "reply": reply,
                     "close": status in ("processed", "duplicate"), "result": result})  # fmt: skip
    (out_dir / "plan.json").write_text(json.dumps(plan, indent=1) + "\n", encoding="utf-8")
    return plan
