"""Type of each Neuro News item, with an LLM (plan, step 14a).

Types (SCOPE §7, Phase 1): ``healthy_brain``, ``disease``, ``clinical_trial``,
``technique`` and ``noise``. What is classified (Aday, 2026-11-12): the studies that pass
the cheap prefilter of ``dim_study.news_candidate`` (spike S5: research in English with
an abstract, recent; preprints included) and the neuroscience news items of
``fct_news_item``, entered in the last :data:`WINDOW_DAYS` days. Measured on one real
day: ~470 studies a day, about 24 calls and 30 000 tokens of Groq's 200 000 a day.

The items come from the warehouse (``warehouse.duckdb``, read-only), because the merge by
DOI and the prefilter live in dbt; so the daily run builds once before this step and once
after it. Answers go to ``derived/news/types.json`` (committed to the ``data`` branch),
one row per item with the hash of what the model saw and the prompt version, so an item
is asked again only when its headline or summary or the prompt change.

Adapted from paleo-atlas ``src/paleo/news/classify.py`` (batches of 20, input hash,
prompt version, progress saved per batch, newest first when limited).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import duckdb
from pydantic import BaseModel

from synaptica.config import get_paths
from synaptica.llm import LLM, prompt
from synaptica.store import _atomic_write, utc_today

BATCH = 20
WINDOW_DAYS = 7
TYPES = ("healthy_brain", "disease", "clinical_trial", "technique", "noise")

NewsType = Literal["healthy_brain", "disease", "clinical_trial", "technique", "noise"]


class ItemType(BaseModel):
    index: int
    type: NewsType


class BatchTypes(BaseModel):
    items: list[ItemType]


@dataclass
class ClassifyResult:
    total: int = 0
    up_to_date: int = 0
    classified: int = 0
    missing: int = 0  # items the model left out (asked again next run)


def types_path(derived_root: Path | None = None) -> Path:
    root = derived_root if derived_root is not None else get_paths().derived
    return root / "news" / "types.json"


def warehouse_path() -> Path:
    return get_paths().data / "warehouse.duckdb"


def items_to_classify(today: dt.date, warehouse: Path | None = None) -> dict[str, dict[str, Any]]:
    """Key -> {title, summary, lang, entered_on} of the studies that pass the prefilter
    and the neuroscience news items entered in the window. Keys: ``study:<study_id>`` and
    the ``news_item_id`` of ``fct_news_item``."""
    since = today - dt.timedelta(days=WINDOW_DAYS)
    with duckdb.connect(str(warehouse or warehouse_path()), read_only=True) as con:
        studies = con.execute(
            "select 'study:' || study_id, title, null, 'en', entered_on from dim_study "
            "where news_candidate and title is not null and entered_on > ?",
            [since],
        ).fetchall()
        news = con.execute(
            "select news_item_id, title, feed_summary, lang, entered_on from fct_news_item "
            "where is_neuro and title is not null and entered_on > ?",
            [since],
        ).fetchall()
    return {
        key: {"title": title, "summary": summary, "lang": lang, "entered_on": str(entered)}
        for key, title, summary, lang, entered in [*studies, *news]
    }


def model_input(item: dict[str, Any]) -> str:
    text = item["title"]
    if item.get("summary"):
        text += " — " + item["summary"]
    return text


def input_hash(item: dict[str, Any]) -> str:
    return hashlib.sha1(model_input(item).encode()).hexdigest()[:12]


def load_types(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    return {row["key"]: row for row in json.loads(path.read_text(encoding="utf-8"))}


def save_types(path: Path, rows: dict[str, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps([rows[k] for k in sorted(rows)], ensure_ascii=False, indent=1)
    _atomic_write(path, text + "\n")


def classify_batch(
    llm: LLM, system: str, batch: list[tuple[str, dict[str, Any]]]
) -> dict[str, str]:
    lines = [f"{i}. [{item['lang']}] {model_input(item)}"
             for i, (_, item) in enumerate(batch, start=1)]  # fmt: skip
    answer = llm.complete_json(system, "ITEMS:\n" + "\n".join(lines), BatchTypes,
                               max_tokens=2_000)  # fmt: skip
    by_index = {t.index: t.type for t in answer.items}
    return {key: by_index[i] for i, (key, _) in enumerate(batch, start=1) if i in by_index}


def classify(
    llm: LLM,
    items: dict[str, dict[str, Any]],
    *,
    derived_root: Path | None = None,
    limit: int | None = None,
    now: dt.datetime | None = None,
) -> ClassifyResult:
    """Classify the items that are new, changed or typed with an older prompt."""
    system, version = prompt("classify_news")
    path = types_path(derived_root)
    rows = load_types(path)
    if not path.exists():
        save_types(path, rows)  # dbt reads the file even when nothing is classified
    result = ClassifyResult(total=len(items))
    pending = []
    for key, item in items.items():
        row = rows.get(key)
        if row and row["input_hash"] == input_hash(item) and row["prompt_version"] == version:
            result.up_to_date += 1
        else:
            pending.append((key, item))
    pending.sort(key=lambda kv: (kv[1]["entered_on"], kv[0]), reverse=True)
    pending = pending[:limit] if limit is not None else pending
    stamp = (now or dt.datetime.now(dt.UTC)).isoformat(timespec="seconds")
    for start in range(0, len(pending), BATCH):
        batch = pending[start : start + BATCH]
        answers = classify_batch(llm, system, batch)
        result.missing += len(batch) - len(answers)
        for key, news_type in answers.items():
            rows[key] = {
                "key": key, "type": news_type, "input_hash": input_hash(items[key]),
                "prompt_version": version, "generator": llm.label, "classified_at": stamp,
            }  # fmt: skip
            result.classified += 1
        save_types(path, rows)  # keep progress if the quota runs out mid-way
    return result


def run(
    llm: LLM,
    *,
    today: dt.date | None = None,
    warehouse: Path | None = None,
    derived_root: Path | None = None,
    limit: int | None = None,
) -> ClassifyResult:
    return classify(
        llm, items_to_classify(today or utc_today(), warehouse),
        derived_root=derived_root, limit=limit,
    )  # fmt: skip
