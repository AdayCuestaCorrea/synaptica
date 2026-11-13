"""Which studies get a summary, and the two commands ``syn facts`` and ``syn write``
(plan, step 16).

The chain is the one of spike S5 (``spikes/s5/pipeline.py``), split as in paleo-atlas
(``syn facts``, then ``syn write``) so each step can be re-run alone and a quota cut
mid-way loses nothing: both skip what is already up to date for the same abstract,
facts and prompts.

What is summarized: the studies of ``dim_study`` that pass the prefilter
(``news_candidate``) and that step 14a typed as something other than ``noise``, entered
in the last :data:`WINDOW_DAYS` days. S5 measured 40 to 60 summaries a day per Groq model,
against ~470 prefiltered studies a day, so ``--limit`` caps each run and the order of the
list is the daily quota (Aday, SCOPE §8, v98): by tiers, and newest first in each one.

1. Neuroscience of Nature · Science · Cell and their sister journals (the journal feeds).
2. Studies linked to a story in the media. The grouping of step 15 links news items to
   each other, never a study to a news item, and the feeds carry no DOI (measured, v103),
   so this tier is empty until such a link exists (:func:`media_linked`).
3. The rest of what was published in a journal.
4. Preprints, and the rare study whose review status is unknown (none in 7 days of real
   data; not knowing it was published in a journal never puts it ahead of one that was).

A study whose summary is up to date costs no call, so the quota moves on to the next.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb
import httpx

from synaptica.llm import LLM, LLMOutputError
from synaptica.narrative import facts as facts_mod
from synaptica.narrative import judge as judge_mod
from synaptica.narrative import write as write_mod
from synaptica.narrative.sources import abstract_for
from synaptica.news.classify import warehouse_path
from synaptica.store import utc_today

WINDOW_DAYS = 7
COLUMNS = ("study_id", "doi", "pmid", "pmcid", "title", "journal", "published_on",
           "entered_on", "sources", "review_status", "species", "integrity")  # fmt: skip


@dataclass
class RunResult:
    total: int = 0
    done: int = 0
    up_to_date: int = 0
    counts: dict[str, int] = field(default_factory=dict)  # outcome -> studies

    def add(self, outcome: str) -> None:
        self.counts[outcome] = self.counts.get(outcome, 0) + 1


def media_linked(con: duckdb.DuckDBPyConnection) -> list[str]:
    """Studies that a story in the media is about (tier 2). Empty: nothing links a study to
    a news item yet (SCOPE v103; the study-news pairs are in the backlog)."""
    return []


def tier_sql() -> str:
    """The quota tier of a row of ``dim_study`` (1 first); ``?`` is :func:`media_linked`."""
    return ("case when list_contains(sources, 'journals') then 1 "
            "when list_contains(?, study_id) then 2 "
            "when review_status = 'journal' then 3 else 4 end")  # fmt: skip


def studies_to_summarize(
    today: dt.date, warehouse: Path | None = None, *, study_ids: list[str] | None = None
) -> list[dict[str, Any]]:
    """Rows of ``dim_study`` to summarize in quota order (or exactly ``study_ids``)."""
    with duckdb.connect(str(warehouse or warehouse_path()), read_only=True) as con:
        sql = f"select {', '.join(COLUMNS)} from dim_study where "
        if study_ids:
            sql += f"study_id in ({', '.join('?' * len(study_ids))})"
            params: list[Any] = list(study_ids)
        else:
            sql += ("news_candidate and news_type is not null and news_type != 'noise' "
                    "and title is not null and entered_on > ?")  # fmt: skip
            params = [today - dt.timedelta(days=WINDOW_DAYS)]
        sql += (f" order by {tier_sql()}, entered_on desc, "
                "least(published_on, entered_on) desc nulls last, study_id")  # fmt: skip
        rows = con.execute(sql, [*params, media_linked(con)]).fetchall()
    return [dict(zip(COLUMNS, row, strict=True)) for row in rows]


def run_facts(
    llm: LLM,
    studies: list[dict[str, Any]],
    *,
    client: httpx.Client | None = None,
    limit: int | None = None,
    derived_root: Path | None = None,
    cache_root: Path | None = None,
    now: dt.datetime | None = None,
) -> RunResult:
    """Facts of each study with an abstract; ``limit`` counts model calls, not studies."""
    result = RunResult(total=len(studies))
    for study in studies:
        if limit is not None and result.done >= limit:
            break
        found = abstract_for(study, cache_root=cache_root, client=client)
        if found is None:
            result.add("no_abstract")
            continue
        abstract, origin = found
        if facts_mod.is_up_to_date(study["study_id"], abstract, derived_root):
            result.up_to_date += 1
            continue
        result.done += 1
        try:
            doc = facts_mod.extract_facts(llm, study, abstract, origin=origin,
                                          derived_root=derived_root, cache_root=cache_root,
                                          now=now)  # fmt: skip
        except LLMOutputError:
            result.add("model_error")  # nothing saved: asked again next run
            continue
        result.add(doc["status"])
    return result


def run_write(
    llm: LLM,
    studies: list[dict[str, Any]],
    *,
    limit: int | None = None,
    derived_root: Path | None = None,
    cache_root: Path | None = None,
    now: dt.datetime | None = None,
) -> RunResult:
    """English and Spanish texts of each study whose facts are ``ok``."""
    result = RunResult(total=len(studies))
    for study in studies:
        if limit is not None and result.done >= limit:
            break
        key = study["study_id"]
        doc = facts_mod.load(facts_mod.facts_path(key, derived_root))
        if doc is None or doc["status"] != "ok":
            result.add("no_facts")
            continue
        if write_mod.is_up_to_date(doc, derived_root):
            result.up_to_date += 1
            continue
        quotes_file = facts_mod.quotes_path(key, cache_root)
        found = abstract_for(study, cache_root=cache_root)
        if not quotes_file.exists() or found is None:
            result.add("no_cache")  # the facts were made on another machine or run
            continue
        if facts_mod.abstract_hash(found[0]) != doc["abstract_hash"]:
            result.add("stale_facts")  # the abstract changed: `syn facts` first
            continue
        result.done += 1
        quotes = json.loads(quotes_file.read_text(encoding="utf-8"))
        try:
            status = write_mod.write_study(llm, doc, quotes, found[0],
                                           derived_root=derived_root, now=now)  # fmt: skip
        except LLMOutputError:
            result.add("model_error")
            continue
        result.add("en_" + status["en"])
        if "es" in status:
            result.add("es_" + status["es"])
    return result


def run_judge(
    judge: LLM,
    studies: list[dict[str, Any]],
    *,
    limit: int | None = None,
    derived_root: Path | None = None,
    cache_root: Path | None = None,
    now: dt.datetime | None = None,
) -> RunResult:
    """Verdict of the judge on each study whose texts are verified and not judged yet."""
    result = RunResult(total=len(studies))
    for study in studies:
        if limit is not None and result.done >= limit:
            break
        texts = judge_mod.pending(study["study_id"], derived_root)
        if texts is None:
            continue
        found = abstract_for(study, cache_root=cache_root)
        if found is None:
            result.add("no_cache")
            continue
        result.done += 1
        try:
            verdict = judge_mod.judge_study(judge, study, found[0], texts,
                                            derived_root=derived_root, now=now)  # fmt: skip
        except LLMOutputError:
            result.add("model_error")
            continue
        result.add("passed" if verdict.passed else "rejected")
    return result


def select(today: dt.date | None = None, study_ids: list[str] | None = None) -> list[dict]:
    return studies_to_summarize(today or utc_today(), study_ids=study_ids)
