"""The blind sheet of same-story pairs that Aday labels (step 15, decision of Aday: option A).

Measured on 2026-11-14: the LLM had judged 405 real pairs, all "no", and the highest TF-IDF
similarity was 0.28, so a random sample would hold no positives and say nothing about
recall. The sheet therefore picks the pairs where a "yes" is likely, plus a control:

- every pair the LLM said "yes" to (its precision);
- the ``top`` pairs most alike by TF-IDF (the duplicates the LLM may have missed);
- every pair across languages (where TF-IDF is weak and the LLM is the only judge);
- ``sample`` pairs at random from the rest (a control for the easy "no").

It is *blind*: no column says what the LLM answered or why a pair was picked, and the rows
are shuffled. The universe is the pairs the LLM judged (``derived/news/pairs.json``),
whose two items are in the warehouse. Because the selection is not uniform, the precision
and recall measured on it describe these pairs, not the whole stream; the report says so.

The sheet has the feeds' texts (ScienceDaily's summaries are copyrighted), so it is
written outside the repository; ``to_gold`` keeps only ``key_a,key_b,same`` for
``eval/news/pairs.csv``. No LLM is called here.
"""

from __future__ import annotations

import csv
import random
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from synaptica.news.evaluate import PAIR_COLUMNS, SEED, pair_text

TOP = 30
SAMPLE = 20
SHEET_COLUMNS = ("key_a", "key_b", "lang_a", "outlet_a", "published_a", "title_a", "summary_a",
                 "lang_b", "outlet_b", "published_b", "title_b", "summary_b", "same")  # fmt: skip
REPO = Path(__file__).resolve().parents[3]


def select(
    answers: dict[tuple[str, str], bool],
    items: dict[str, dict[str, Any]],
    top: int = TOP,
    sample: int = SAMPLE,
    seed: int = SEED,
) -> list[tuple[str, str]]:
    """The pairs of the sheet, shuffled (see the module docstring)."""
    from synaptica.news.group import tfidf_similarity

    universe = sorted(p for p in answers if p[0] in items and p[1] in items)
    if not universe:
        return []
    keys = sorted({k for p in universe for k in p})
    index = {k: i for i, k in enumerate(keys)}
    matrix = tfidf_similarity([pair_text(items[k]) for k in keys])
    sim = {p: float(matrix[index[p[0]], index[p[1]]]) for p in universe}

    chosen = {p for p in universe if answers[p]}
    chosen |= set(sorted(universe, key=lambda p: (-sim[p], p))[:top])
    chosen |= {p for p in universe if items[p[0]]["lang"] != items[p[1]]["lang"]}
    rng = random.Random(seed)
    rest = [p for p in universe if p not in chosen]
    chosen |= set(rng.sample(rest, min(sample, len(rest))))
    out = sorted(chosen)
    rng.shuffle(out)
    return out


def outside_repo(path: Path) -> bool:
    """True when ``path`` cannot be committed by mistake: outside the repository, or in
    its ignored ``data/`` folder."""
    p = path.resolve()
    return not p.is_relative_to(REPO) or p.is_relative_to(REPO / "data")


def write_sheet(path: Path, pairs: Sequence[tuple[str, str]], items: dict[str, dict]) -> None:
    if not outside_repo(path):
        raise ValueError(f"{path}: the sheet has the feeds' texts; write it outside the "
                         "repository (or in its ignored data/ folder)")  # fmt: skip
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(SHEET_COLUMNS)
        for a, b in pairs:
            row = [a, b]
            for k in (a, b):
                it = items[k]
                when = it.get("published")
                row += [it["lang"], it.get("outlet") or "",
                        when.isoformat() if hasattr(when, "isoformat") else (when or ""),
                        it["title"], it["summary"]]  # fmt: skip
            w.writerow([*row, ""])


def to_gold(sheet: Path, out: Path) -> int:
    """The labelled sheet as ``key_a,key_b,same`` (sorted); refused while a row has no
    yes/no. Returns the number of pairs."""
    with sheet.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    blank = [f"{r['key_a']} / {r['key_b']}" for r in rows
             if (r.get("same") or "").strip().lower() not in ("yes", "no")]  # fmt: skip
    if blank:
        raise ValueError(f"{len(blank)} pairs without yes/no, e.g. {blank[0]}")
    gold = sorted((r["key_a"], r["key_b"], r["same"].strip().lower()) for r in rows)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(PAIR_COLUMNS)
        w.writerows(gold)
    return len(gold)
