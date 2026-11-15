"""Her held edits, checked again with today's code (``syn review recheck-held``).

Why (seen on 2026-11-14): two of her eight held edits were held by a false positive of
``intake.align`` (a reviewed paragraph compared with her one-sentence lines). Fixing the
check does not release them: the log is append only and ``held.jsonl`` still holds them.

This command walks the held edits that are still on her table (no later answer of hers),
runs ``intake.edit_warnings`` on them again against the same queue and sources, and for
each one that now passes appends to ``decisions.jsonl`` the very same decision with
``rechecked_at`` set. Her text, her login, her date and her Issue stay as they were; the
log shows that it was applied later (and the commit, by whom). An edit that still fails
stays held, with its old warnings. An edit whose study source has no text is not looked
at (the copy check would be skipped): it stays held and the command exits 2. Running it
twice adds nothing: once released, the edit is no longer held.

Nothing goes to an LLM, and nothing is rewritten.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from synaptica.review.apply import read_log, state
from synaptica.review.intake import dump, edit_warnings, study_source
from synaptica.review.models import Decision, Queue, TextContent


def recheck(
    data_dir: Path, queue: Queue, texts: dict[str, str], now: dt.datetime
) -> tuple[list[Decision], list[Decision], list[Decision]]:
    """(released, still held, held without source text). Only held edits of a draft in
    ``queue`` are looked at; a re-edit of a held text is the intake's job."""
    events = read_log(data_dir)
    released, still, waiting = [], [], []
    for item in queue.items:
        if not isinstance(item.content, TextContent):
            continue
        st = state(item, events)
        if st.status != "held" or st.held is None:
            continue
        d = st.held.decision
        if d.content_sha256 != item.content_sha256:
            still.append(d)
        elif any(study_source(s.id) and s.id not in texts for s in item.content.sources):
            waiting.append(d)
        elif edit_warnings(item, d.payload, texts):
            still.append(d)
        else:
            released.append(d.model_copy(update={"rechecked_at": now}))
    return released, still, waiting


def run(data_dir: Path, queue: Queue, texts: dict[str, str], now: dt.datetime) -> dict:
    released, still, waiting = recheck(data_dir, queue, texts, now)
    if released:
        data_dir.mkdir(parents=True, exist_ok=True)
        with (data_dir / "decisions.jsonl").open("a", encoding="utf-8") as f:
            for d in released:
                f.write(json.dumps(dump(d), ensure_ascii=False) + "\n")
    ids = lambda ds: [d.item_id for d in ds]  # noqa: E731
    return {"released": ids(released), "held": ids(still), "without_source": ids(waiting)}
