"""Sofía's labels of Neuro News headlines: the gold of the classifier (plan, step 14b;
option C of Aday, 2026-11-15).

A label is one more kind of item in her review page (``ItemType.NEWS_LABEL``): the
headline, its journal or outlet, a link to the original and five buttons, one per type of
``classify.TYPES``. Her log keeps only the item and the type she chose; the headline and
the text the baselines learn from come from the warehouse (``label_texts``), as with the
pairs of step 15 (v151): the repository and her page are public, and the feeds'
summaries are copyrighted.

**Which headlines.** The items the LLM already classified (``derived/news/types.json``),
so every label is compared with an answer. A sample at random would bring about 4
clinical trials in 100 (151 of 4016 on 2026-11-17), too few to score that class; so the
sample is stratified by the LLM's type: a seeded shuffle inside each type, the types taken
in turns. Each day of her queue holds every type, and the order is the same every day for
the same items. Stratifying by the LLM's answer does not favour it: the gold is her type,
not the LLM's, and the baseline is scored on the same items (cross-validated).

**How many.** :data:`TARGET` labels in all, :data:`PER_WEEKDAY` a day (:data:`PER_WEEKEND`
at the weekend), from :data:`LABELS_FROM` (her page of 2026-11-18 was announced without
them). Once she has given :data:`TARGET`, no more come.

**The gold file.** ``syn eval labels-gold`` writes ``eval/news/labels.csv`` with the
columns ``key,type`` only, from her log.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from synaptica.narrative.facts import slug
from synaptica.news.classify import TYPES, model_input
from synaptica.review.models import Action, ItemType, LabelContent, ReviewItem

TARGET = 100
PER_WEEKDAY, PER_WEEKEND = 10, 3
LABELS_FROM = dt.date(2026, 11, 19)
SEED = "labels-v1"
GOLD_COLUMNS = ("key", "type")


def item_id(key: str) -> str:
    """Her item's id: the key, lower case, with anything unsafe as ``_``."""
    return slug(key)


def _rank(key: str) -> str:
    return hashlib.sha1(f"{SEED}:{key}".encode()).hexdigest()


def stratified(llm_types: dict[str, str]) -> list[str]:
    """Keys in the order they reach her: shuffled inside each LLM type (seeded), the
    types in turns (``classify.TYPES`` order) until all run out."""
    by_type = {t: sorted((k for k, v in llm_types.items() if v == t), key=_rank) for t in TYPES}
    out: list[str] = []
    for i in range(max((len(v) for v in by_type.values()), default=0)):
        out += [keys[i] for keys in by_type.values() if i < len(keys)]
    return out


def headlines(keys: Sequence[str], warehouse: Path) -> dict[str, dict[str, Any]]:
    """Key -> {title, summary, lang, source, url} from the warehouse: ``study:<id>`` from
    ``dim_study``, any other key from ``fct_news_item`` (as ``classify`` reads them)."""
    import duckdb

    studies = sorted(k.removeprefix("study:") for k in keys if k.startswith("study:"))
    news = sorted(k for k in keys if not k.startswith("study:"))
    out: dict[str, dict[str, Any]] = {}
    with duckdb.connect(str(warehouse), read_only=True) as con:
        if studies:
            rows = con.execute(
                "select study_id, title, journal, doi, pmid from dim_study "
                "where title is not null and study_id in (select unnest(?))",
                [studies],
            ).fetchall()
            for sid, title, journal, doi, pmid in rows:
                url = f"https://doi.org/{doi}" if doi else None
                if url is None and pmid:
                    url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
                out[f"study:{sid}"] = {"title": title, "summary": None, "lang": "en",
                                       "source": journal or "", "url": url}  # fmt: skip
        if news:
            rows = con.execute(
                "select news_item_id, title, feed_summary, lang, outlet, url from fct_news_item "
                "where title is not null and news_item_id in (select unnest(?))",
                [news],
            ).fetchall()
            for key, title, summary, lang, outlet, url in rows:
                out[key] = {"title": title, "summary": summary, "lang": lang,
                            "source": outlet or "", "url": url}  # fmt: skip
    return out


def label_texts(keys: Sequence[str], warehouse: Path) -> dict[str, str]:
    """What the classifier saw for each key (``classify.model_input``): the baseline
    learns from the same text."""
    return {k: model_input(v) for k, v in headlines(keys, warehouse).items()}


def labelled(events: Iterable[Any]) -> dict[str, str]:
    """Item id -> her last type, whatever version of the headline she saw."""
    out: dict[str, str] = {}
    for e in events:
        d = e.decision
        if d.item_type is ItemType.NEWS_LABEL and d.action is Action.LABEL:
            out[d.item_id] = d.payload["type"]
    return out


def review_items(
    llm_types: dict[str, str], warehouse: Path, events: Iterable[Any]
) -> list[ReviewItem]:
    """The headlines still to label, in order, as items of her queue (none once she has
    given :data:`TARGET` labels). ``collect`` takes a few a day."""
    done = labelled(events)
    if len(done) >= TARGET:
        return []
    order = [k for k in stratified(llm_types) if item_id(k) not in done]
    found = headlines(order, warehouse)
    items = []
    for key in order:
        h = found.get(key)
        if h is None:
            continue  # left the warehouse
        content = LabelContent(key=key, title=h["title"], lang=h["lang"],
                               source=h["source"], url=h["url"])  # fmt: skip
        items.append(ReviewItem(item_type=ItemType.NEWS_LABEL, item_id=item_id(key),
                                title_es=h["title"], content=content))  # fmt: skip
    return items


def gold_rows(events: Iterable[Any], keys: Iterable[str]) -> list[tuple[str, str]]:
    """``(key, type)`` of every label of hers, sorted; ``keys`` are the classifier's keys
    (``types.json``), to undo :func:`item_id`. Two keys with the same id are an error."""
    by_id: dict[str, str] = {}
    for key in keys:
        other = by_id.setdefault(item_id(key), key)
        if other != key:
            raise ValueError(f"two keys share the item id {item_id(key)}: {other}, {key}")
    rows, unknown = [], []
    for iid, kind in labelled(events).items():
        if iid in by_id:
            rows.append((by_id[iid], kind))
        else:
            unknown.append(iid)
    if unknown:
        raise ValueError(f"labels of items no longer classified: {sorted(unknown)[:5]}")
    return sorted(rows)


def gold_csv(rows: Sequence[tuple[str, str]]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(GOLD_COLUMNS)
    writer.writerows(rows)
    return buf.getvalue()
