"""Next round of review pages from the log (what the daily pipeline will do).

Moved from the spike ``spikes/s4/ronda.py`` (plan, step R; ADR 0005).

Reads the queue of drafts and the decision log, applies it (``apply.py``) and writes the
two review pages with what is still waiting for Sofía, her held edits included, and the
queue they show (``queue.json``): her next Issues are read against that one. Also
prints the state of every item, for the test notes. Command: ``syn review round``.
"""

from __future__ import annotations

from pathlib import Path

from synaptica.review.apply import next_queue, read_log, states
from synaptica.review.models import Queue
from synaptica.review.page import OUT, page_items, render


def round_pages(queue: Queue, data_dir: Path, out_dir: Path) -> tuple[Queue, dict]:
    sts = states(queue, read_log(data_dir))
    waiting = next_queue(queue, sts)
    out_dir.mkdir(parents=True, exist_ok=True)
    # The round in the file name: two rounds' files must never look the same (round 2 of the
    # test: both were «revision.html» and she opened the old one).
    label = out_dir.name
    # The queue the pages were built from: her Issues of this round are checked against it
    # (a held edit comes back as a new version with its own hash). Round 3 of the test was
    # refused as stale because its Issue was checked against the first queue.
    (out_dir / "queue.json").write_text(waiting.model_dump_json(indent=1), encoding="utf-8")
    for variant, default in OUT.items():
        if not page_items(waiting, variant):
            continue  # no empty page to send her
        name = f"{default.stem}-{label}{default.suffix}"
        (out_dir / name).write_text(render(waiting, variant, label), encoding="utf-8")
    return waiting, sts
