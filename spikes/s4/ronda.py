"""S4 · Next round of review pages from the log (what the daily pipeline will do).

Reads the queue of drafts and the decision log, applies it (``apply.py``) and writes the
two review pages with what is still waiting for Sofía, her held edits included, and the
queue they show (``queue.json``): her next Issues are read against that one. Also
prints the state of every item, for the test notes. Run from the repo root:

    uv run --group spike-s4 python spikes/s4/ronda.py --queue Q --data-dir D --out DIR
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from apply import next_queue, publishable, read_log, states  # noqa: E402
from models import Queue  # noqa: E402
from review_page import OUT, page_items, render  # noqa: E402


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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--queue", type=Path, required=True)
    ap.add_argument("--data-dir", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    queue = Queue.model_validate_json(args.queue.read_text("utf-8"))
    waiting, sts = round_pages(queue, args.data_dir, args.out)
    for key, st in sts.items():
        extra = f" grade={st.grade}" if st.grade else ""
        extra += " awaiting_en" if st.awaiting_en else ""
        print(f"{'/'.join(key):40} {st.status:9} publishable={publishable(st)}{extra}")
    print(
        f"waiting: {len(waiting.items)} {dict(Counter(i.item_type.value for i in waiting.items))}"
    )


if __name__ == "__main__":
    main()
