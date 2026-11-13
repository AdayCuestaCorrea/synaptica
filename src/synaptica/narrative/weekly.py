"""Weekly summary of Neuro News (plan, step 25; SCOPE §7 "Resumen semanal"), without
its page yet (the web, steps 21 to 24, waits for Aday).

Same chain and checks as a study's summary (:mod:`synaptica.narrative.write` and
:mod:`synaptica.narrative.judge`): the writer only sees verified facts, now of several
studies grouped by study (ids ``s2-f3``); the English text passes the citation, number,
name, anti-copy and claim checks against the facts and the abstracts; the Spanish one
passes alignment, claims and spelling; and the judge of another family reads all the
abstracts and both texts. A text that fails goes to ``derived/weekly_review/`` and the
site will show :func:`weekly_fallback`, built only from the data.

Which studies: those entered in the ISO week whose own summary was published (checks
and judge passed), at most :data:`MAX_STUDIES`, taken in turns from each type of step
14a so one type does not fill the week, newest first within each type. Paleo Atlas's
weekly recap is a list of the week's items with no text; the text here is new.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

import duckdb

from synaptica.config import get_paths
from synaptica.llm import LLM, prompt
from synaptica.narrative import facts as facts_mod
from synaptica.narrative import judge as judge_mod
from synaptica.narrative import write as write_mod
from synaptica.narrative.checks import (
    check_alignment,
    check_claims_es,
    check_spelling_es,
    check_text,
)
from synaptica.narrative.fallback import _MONTHS_EN, _MONTHS_ES, summary_for
from synaptica.narrative.pipeline import COLUMNS
from synaptica.narrative.sources import abstract_for
from synaptica.news.classify import TYPES, warehouse_path
from synaptica.store import _atomic_write

MAX_STUDIES = 8
MIN_STUDIES = 2  # one study is not a week: the fallback says so
MIN_WORDS, MAX_WORDS = 80, 250


def week_key(day: dt.date) -> str:
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def week_days(key: str) -> tuple[dt.date, dt.date]:
    year, week = key.split("-W")
    monday = dt.date.fromisocalendar(int(year), int(week), 1)
    return monday, monday + dt.timedelta(days=6)


def last_week(today: dt.date) -> str:
    """The last complete ISO week before ``today``."""
    return week_key(today - dt.timedelta(days=7))


def weekly_path(key: str, lang: str, *, verified: bool, derived_root: Path | None = None) -> Path:
    root = derived_root if derived_root is not None else get_paths().derived
    return root / ("weekly" if verified else "weekly_review") / f"{key}.{lang}.json"


def candidates(key: str, warehouse: Path | None = None) -> list[dict[str, Any]]:
    """The week's studies that could get a summary (rows of ``dim_study``)."""
    monday, sunday = week_days(key)
    with duckdb.connect(str(warehouse or warehouse_path()), read_only=True) as con:
        rows = con.execute(
            f"select {', '.join(COLUMNS)}, news_type from dim_study where news_candidate "
            "and news_type is not null and news_type != 'noise' "
            "and entered_on between ? and ? order by entered_on desc, study_id",
            [monday, sunday],
        ).fetchall()
    return [dict(zip((*COLUMNS, "news_type"), row, strict=True)) for row in rows]


def choose(rows: list[dict[str, Any]], derived_root: Path | None = None) -> list[dict]:
    """Studies with a published summary, in turns by type, at most MAX_STUDIES."""

    def shown(row: dict[str, Any]) -> bool:
        return summary_for(row, "en", derived_root=derived_root)["kind"] == "verified"

    published = [r for r in rows if shown(r)]
    queues = {t: [r for r in published if r["news_type"] == t] for t in TYPES}
    chosen: list[dict[str, Any]] = []
    while len(chosen) < MAX_STUDIES and any(queues.values()):
        for t in TYPES:
            if queues[t] and len(chosen) < MAX_STUDIES:
                chosen.append(queues[t].pop(0))
    return chosen


def _inputs(
    chosen: list[dict[str, Any]], derived_root: Path | None, cache_root: Path | None
) -> tuple[list[str], dict[str, str], list[str], list[str]] | None:
    """(fact lines for the writer, support for the checks, abstracts, abstracts for the
    judge), or None when a study's facts or cache are missing."""
    lines, support, abstracts, for_judge = [], {}, [], []
    for n, study in enumerate(chosen, start=1):
        doc = facts_mod.load(facts_mod.facts_path(study["study_id"], derived_root))
        quotes_file = facts_mod.quotes_path(study["study_id"], cache_root)
        found = abstract_for(study, cache_root=cache_root)
        if doc is None or found is None or not quotes_file.exists():
            return None
        quotes = json.loads(quotes_file.read_text(encoding="utf-8"))
        kind = "preprint, not peer reviewed" if study["review_status"] == "preprint" else (
            "peer-reviewed journal")  # fmt: skip
        lines.append(f"Study s{n} ({study.get('journal') or 'unknown journal'}, {kind}):")
        for f in doc["facts"]:
            fid = f"s{n}-{f['id']}"
            lines.append(f"{fid} [{f['subject']}] {f['statement']}")
            support[fid] = f"{f['statement']} {quotes.get(f['id'], '')}"
        abstracts.append(found[0])
        for_judge.append(f"[Study s{n}] {study['title']}\n{found[0]}")
    return lines, support, abstracts, for_judge


def input_hash(chosen: list[dict[str, Any]], derived_root: Path | None = None) -> str:
    parts = []
    for study in chosen:
        doc = facts_mod.load(facts_mod.facts_path(study["study_id"], derived_root)) or {}
        parts.append([study["study_id"], write_mod.facts_hash(doc.get("facts", []))])
    return hashlib.sha256(json.dumps(parts).encode()).hexdigest()[:16]


def _versions() -> str:
    return "+".join(prompt(n)[1] for n in ("weekly_en", "adapt_es", "judge"))


def is_up_to_date(key: str, chosen: list[dict], derived_root: Path | None = None) -> bool:
    current = input_hash(chosen, derived_root)
    for verified in (True, False):
        path = weekly_path(key, "en", verified=verified, derived_root=derived_root)
        if path.exists():
            stored = json.loads(path.read_text(encoding="utf-8"))
            if stored["input_hash"] == current and stored["prompt_version"] == _versions():
                return True
    return False


def _save(key: str, lang: str, record: dict[str, Any], *, verified: bool,
          derived_root: Path | None) -> None:  # fmt: skip
    path = weekly_path(key, lang, verified=verified, derived_root=derived_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, json.dumps(record, ensure_ascii=False, indent=1) + "\n")
    weekly_path(key, lang, verified=not verified, derived_root=derived_root).unlink(missing_ok=True)


def write_weekly(
    llm: LLM,
    judge: LLM,
    key: str,
    chosen: list[dict[str, Any]],
    *,
    derived_root: Path | None = None,
    cache_root: Path | None = None,
    now: dt.datetime | None = None,
) -> str:
    """Write, check and judge the week's summary: ``published``, ``failed_en``,
    ``failed_es``, ``rejected_by_judge``, ``too_few`` or ``no_cache``."""
    if len(chosen) < MIN_STUDIES:
        return "too_few"
    inputs = _inputs(chosen, derived_root, cache_root)
    if inputs is None:
        return "no_cache"
    lines, support, abstracts, for_judge = inputs
    now = now or dt.datetime.now(dt.UTC)
    base = {"week": key, "studies": [s["study_id"] for s in chosen],
            "input_hash": input_hash(chosen, derived_root), "prompt_version": _versions(),
            "generator": llm.label,
            "generated_at": now.isoformat(timespec="seconds")}  # fmt: skip

    feedback: list[str] = []
    en: list[tuple[str, list[str]]] = []
    for _ in range(write_mod.ATTEMPTS):
        en = write_mod.write_en(llm, support, feedback, "weekly_en", fact_lines=lines)
        report = check_text(en, support, abstracts, min_words=MIN_WORDS, max_words=MAX_WORDS)
        feedback = report.summary()
        if report.passed:
            break

    def record(lang: str, status: str, sentences, problems) -> dict[str, Any]:
        copied = any("copies" in p for p in problems)
        return {**base, "lang": lang, "status": status,
                "problems": write_mod._public(problems),
                "sentences": [] if copied else [{"text": t, "fact_ids": f}
                                                 for t, f in sentences]}  # fmt: skip

    if feedback:
        _save(key, "en", record("en", "failed", en, feedback), verified=False,
              derived_root=derived_root)  # fmt: skip
        return "failed_en"
    en_texts = [t for t, _ in en]
    es: list[str] = []
    for _ in range(write_mod.ATTEMPTS):
        es = write_mod.adapt_es(llm, en_texts, feedback)
        feedback = [*check_alignment(en_texts, es), *check_claims_es(en_texts, es),
                    *check_spelling_es(en_texts, es)]  # fmt: skip
        if not feedback:
            break
    es_pairs = [(t, f) for t, (_, f) in zip(es, en, strict=True)]
    if feedback:
        _save(key, "en", record("en", "verified", en, []), verified=False,
              derived_root=derived_root)  # fmt: skip
        _save(key, "es", record("es", "failed", es_pairs, feedback), verified=False,
              derived_root=derived_root)  # fmt: skip
        return "failed_es"
    monday, sunday = week_days(key)
    verdict, judged = judge_mod.ask(
        judge, writer=llm.label, title=f"Weekly summary, {monday} to {sunday}",
        abstract="\n\n".join(for_judge), en=en_texts, es=es, now=now,
    )  # fmt: skip
    for lang, pairs in (("en", en), ("es", es_pairs)):
        if verdict.passed:
            _save(key, lang, {**record(lang, "verified", pairs, []), "judge": judged},
                  verified=True, derived_root=derived_root)  # fmt: skip
        else:
            rejected = record(lang, "rejected_by_judge", pairs, [judge_mod.public_reason(verdict)])
            _save(key, lang, {**rejected, "judge": judged}, verified=False,
                  derived_root=derived_root)  # fmt: skip
    return "published" if verdict.passed else "rejected_by_judge"


def weekly_fallback(key: str, chosen: list[dict[str, Any]], lang: str) -> str:
    """One sentence from the data: the week and how many studies, in whom, preprints."""
    monday, sunday = week_days(key)
    months = _MONTHS_ES if lang == "es" else _MONTHS_EN
    n = len(chosen)
    humans = sum(s.get("species") in ("humans", "both") for s in chosen)
    animals = sum(s.get("species") in ("animals", "both") for s in chosen)
    preprints = sum(s.get("review_status") == "preprint" for s in chosen)
    if lang == "es":
        head = (f"Semana del {monday.day} de {months[monday.month - 1]} al {sunday.day} de "
                f"{months[sunday.month - 1]} de {sunday.year}")  # fmt: skip
        if not n:
            return f"{head}: no hay estudios resumidos."
        parts = [f"{n} {'estudio resumido' if n == 1 else 'estudios resumidos'}"]
        parts += [f"{humans} en humanos"] if humans else []
        parts += [f"{animals} en animales"] if animals else []
        parts += [f"{preprints} sin revisión por pares (preprints)"] if preprints else []
    else:
        head = (f"Week of {monday.day} {months[monday.month - 1]} to {sunday.day} "
                f"{months[sunday.month - 1]} {sunday.year}")  # fmt: skip
        if not n:
            return f"{head}: no studies summarized."
        parts = [f"{n} {'study' if n == 1 else 'studies'} summarized"]
        parts += [f"{humans} in humans"] if humans else []
        parts += [f"{animals} in animals"] if animals else []
        parts += [f"{preprints} not yet peer reviewed (preprints)"] if preprints else []
    return f"{head}: {', '.join(parts)}."


def weekly_for(
    key: str, chosen: list[dict[str, Any]], lang: str, *, derived_root: Path | None = None
) -> dict[str, Any]:
    """The published weekly text of that language, or the fallback."""
    path = weekly_path(key, lang, verified=True, derived_root=derived_root)
    if path.exists():
        record = json.loads(path.read_text(encoding="utf-8"))
        if (record.get("judge") or {}).get("passed") and record["sentences"]:
            return {"kind": "verified", "sentences": record["sentences"],
                    "studies": record["studies"]}  # fmt: skip
    return {"kind": "fallback", "text": weekly_fallback(key, chosen, lang)}
