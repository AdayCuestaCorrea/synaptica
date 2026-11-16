"""Group the news items that tell the same story, across outlets and languages (step 15).

Copied and adapted from paleo-atlas ``src/paleo/news/dedup.py`` (decision D2): every pair
of items published within :data:`WINDOW_DAYS` of each other is a candidate; the LLM says
whether each pair is the same story (answers kept in ``derived/news/pairs.json`` with
the hashes of both inputs and the prompt version, so a pair is asked once); groups are
the connected components of the "same" pairs (union-find) in
``derived/news/groups.json``. Paleo measured TF-IDF failing across languages (F1 0.31),
which is why the LLM decides; :func:`tfidf_similarity` stays for the evaluation.

"DOI exact" first (plan): studies are already one row per DOI in ``dim_study``, so
what is grouped here are the news items of ``fct_news_item`` that are neuroscience and
not ``noise`` (types from step 14a; unclassified items wait). Measured on 2026-11-12: 36
such items in 14 days, 322 pairs within 5 days (40 across languages); new pairs are
~30 a day, about 2 calls.

Time box (SCOPE v187): Groq's output cap (1000 tokens a minute) and ``max_tokens=600``
let one call of :data:`PAIR_BATCH` pairs through per minute, and the pipeline kills the
command at 5 minutes, which also lost ``groups.json`` (run of 2026-11-16, 174 pairs
pending). The command stops itself after :data:`BUDGET_SECONDS`, newest pairs first, and
still writes the groups from the answers it has; the rest waits for the next run.
"""

from __future__ import annotations

import datetime as dt
import json
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import duckdb
from pydantic import BaseModel

from synaptica.config import get_paths
from synaptica.llm import LLM, prompt
from synaptica.news.classify import input_hash, warehouse_path
from synaptica.store import _atomic_write, utc_today

WINDOW_DAYS = 5
LOOKBACK_DAYS = 30  # items considered on each run
PAIR_BATCH = 15
# Checked before each call. The pipeline's hard limit is 5 minutes; a call admitted at the
# end may still wait ~60 s for the per-minute budget and one 429 retry (run of 2026-11-16:
# one call every ~60 s, no 429), so the margin covers that call and the start-up.
BUDGET_SECONDS = 150.0
SUMMARY_CHARS = 300


class PairAnswer(BaseModel):
    index: int
    same: bool


class PairAnswers(BaseModel):
    pairs: list[PairAnswer]


def pairs_path(derived_root: Path | None = None) -> Path:
    return (
        (derived_root if derived_root is not None else get_paths().derived)
        / "news"
        / ("pairs.json")
    )


def groups_path(derived_root: Path | None = None) -> Path:
    return (
        (derived_root if derived_root is not None else get_paths().derived)
        / "news"
        / ("groups.json")
    )


def items_to_group(today: dt.date, warehouse: Path | None = None) -> dict[str, dict[str, Any]]:
    """Key -> {title, summary, lang, published} of the neuro news items, not noise,
    published in the last :data:`LOOKBACK_DAYS` days."""
    since = today - dt.timedelta(days=LOOKBACK_DAYS)
    with duckdb.connect(str(warehouse or warehouse_path()), read_only=True) as con:
        rows = con.execute(
            "select news_item_id, title, feed_summary, lang, published_at from fct_news_item "
            "where is_neuro and news_type is not null and news_type != 'noise' "
            "and published_at is not null and cast(published_at as date) > ?",
            [since],
        ).fetchall()
    return {
        key: {"title": title, "summary": summary, "lang": lang, "published": published}
        for key, title, summary, lang, published in rows
    }


def _short(item: dict[str, Any]) -> str:
    text = f"[{item['lang']}] {item['title']}"
    if item.get("summary"):
        text += " — " + item["summary"][:SUMMARY_CHARS]
    return text


def _when(item: dict[str, Any]) -> dt.datetime | None:
    value = item.get("published")
    if isinstance(value, str):
        value = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


def candidate_pairs(
    items: dict[str, dict[str, Any]], window_days: int = WINDOW_DAYS
) -> list[tuple[str, str]]:
    """Every pair of items published within the window (keys sorted)."""
    ordered = sorted(items)
    out = []
    for i, a in enumerate(ordered):
        for b in ordered[i + 1 :]:
            ta, tb = _when(items[a]), _when(items[b])
            if ta and tb and abs((ta - tb).total_seconds()) <= window_days * 86_400:
                out.append((a, b))
    return out


def judge_pairs(
    llm: LLM,
    items: dict[str, dict[str, Any]],
    pairs: Sequence[tuple[str, str]],
    path: Path,
    *,
    deadline: float | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> tuple[dict[tuple[str, str], bool], int]:
    """Ask the LLM about each pair not answered for the current inputs and prompt, newest
    pairs first, until ``deadline`` (a ``clock()`` value). Returns the answers and how many
    pairs are still pending."""
    system, version = prompt("same_story")
    rows = {}
    if path.exists():
        rows = {(r["key_a"], r["key_b"]): r for r in json.loads(path.read_text("utf-8"))}

    def current(a: str, b: str) -> bool:
        row = rows.get((a, b))
        return bool(row and row["prompt_version"] == version
                    and row["hash_a"] == input_hash(items[a])
                    and row["hash_b"] == input_hash(items[b]))  # fmt: skip

    def newest(pair: tuple[str, str]) -> tuple[float, tuple[str, str]]:
        times = [t.timestamp() for t in (_when(items[k]) for k in pair) if t]
        return (-max(times, default=0.0), pair)

    pending = sorted((p for p in pairs if not current(*p)), key=newest)
    asked = 0
    for start in range(0, len(pending), PAIR_BATCH):
        if deadline is not None and clock() >= deadline:
            break
        asked = start + PAIR_BATCH
        batch = pending[start : start + PAIR_BATCH]
        user = "PAIRS:\n" + "\n".join(
            f"{i}. A: {_short(items[a])}\n   B: {_short(items[b])}"
            for i, (a, b) in enumerate(batch, start=1)
        )
        answer = llm.complete_json(system, user, PairAnswers, max_tokens=600)
        by_index = {p.index: p.same for p in answer.pairs}
        for i, (a, b) in enumerate(batch, start=1):
            if i in by_index:
                rows[(a, b)] = {"key_a": a, "key_b": b, "same": by_index[i],
                                "hash_a": input_hash(items[a]), "hash_b": input_hash(items[b]),
                                "generator": llm.label, "prompt_version": version}  # fmt: skip
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(path, json.dumps([rows[k] for k in sorted(rows)], indent=1) + "\n")
    answers = {(a, b): rows[(a, b)]["same"] for a, b in pairs if (a, b) in rows}
    return answers, max(0, len(pending) - asked)


def groups(keys: Sequence[str], pairs: Sequence[tuple[str, str]]) -> dict[str, str]:
    """Key -> group id (the group's smallest key), by union-find over the pairs."""
    parent = {k: k for k in keys}

    def find(k: str) -> str:
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    for a, b in pairs:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    return {k: find(k) for k in keys}


def group_news(
    llm: LLM,
    items: dict[str, dict[str, Any]],
    *,
    derived_root: Path | None = None,
    budget: float | None = BUDGET_SECONDS,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, int]:
    """Judge the candidate pairs and save key -> group. Items that left the window keep
    their group from earlier runs; pairs not answered yet count as different stories."""
    deadline = None if budget is None else clock() + budget
    candidates = candidate_pairs(items)
    answers, pending = judge_pairs(llm, items, candidates, pairs_path(derived_root),
                                   deadline=deadline, clock=clock)  # fmt: skip
    same = [pair for pair, yes in answers.items() if yes]
    assigned = groups(sorted(items), same)
    path = groups_path(derived_root)
    old = {}
    if path.exists():
        old = {r["key"]: r for r in json.loads(path.read_text(encoding="utf-8"))}
    rows = {**{k: r for k, r in old.items() if k not in items},
            **{k: {"key": k, "group": g} for k, g in assigned.items()}}  # fmt: skip
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, json.dumps([rows[k] for k in sorted(rows)], indent=1) + "\n")
    sizes: dict[str, int] = {}
    for g in assigned.values():
        sizes[g] = sizes.get(g, 0) + 1
    return {"items": len(items), "candidates": len(candidates), "same": len(same),
            "groups": len(sizes), "grouped": sum(n for n in sizes.values() if n > 1),
            "pending": pending}  # fmt: skip


def run(
    llm: LLM,
    *,
    today: dt.date | None = None,
    warehouse: Path | None = None,
    derived_root: Path | None = None,
    budget: float | None = BUDGET_SECONDS,
) -> dict[str, int]:
    return group_news(llm, items_to_group(today or utc_today(), warehouse),
                      derived_root=derived_root, budget=budget)  # fmt: skip


def tfidf_similarity(texts: Sequence[str]):
    """Cosine similarity of TF-IDF vectors of character 3-5-grams (for the evaluation
    only: no model, weak across languages). Needs the ``eval`` group."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    vectors = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True,
                              lowercase=True).fit_transform(list(texts))  # fmt: skip
    return cosine_similarity(vectors)
