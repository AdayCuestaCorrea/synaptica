"""What goes in Sofía's review queue, and what her decisions change on the site (plan,
step R; decision of Aday, 2026-11-13).

One function per source of items, and ``collect`` joins them in a single queue, so she
has one page to open. Each step adds its own source: for now only the optional
spot-check of published summaries (``ItemType.NEWS``); the ~100 headline labels come with
step 14b and the weekly Classics with step 24a.

**Spot-check.** The summaries that passed their checks and the judge in both languages,
worst Spanish first (the judge's ``spanish_natural``, 1-5, which does not block: ADR D4),
then the newest. Each sentence cites the abstract its facts were read from, so her edits
are checked against it (``intake.STUDY_SOURCES``). Her held edits go first: they are her
own work waiting for her. What she already decided on the current version is left out
(``apply.next_queue``). At most 40 items on a weekday and 10 at the weekend, as she asked
in S4.

**On the site** (``reviewed``): a summary she rejected, or whose English is still to be
rewritten from her Spanish, shows the fallback text instead; one she corrected in both
languages shows her text. The item is rebuilt from today's texts, so a decision on an
older version of a summary changes nothing (the hash, as everywhere in the review).
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import duckdb

from synaptica.narrative.facts import facts_path, load, slug
from synaptica.narrative.fallback import fallback_text, verified_record
from synaptica.review.apply import Event, next_queue, publishable, read_log, state, states
from synaptica.review.models import ItemType, Queue, ReviewItem, Sentence, Source, TextContent

CAP_WEEKDAY, CAP_WEEKEND = 40, 10
LANGS = ("es", "en")


def study_source(study: dict[str, Any], origin: str) -> Source | None:
    """The abstract a study's facts were read from (``abstract_from``), as a source."""
    pmid, doi, pmcid = study.get("pmid"), study.get("doi"), study.get("pmcid")
    if origin == "pubmed" and pmid:
        url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        return Source(id=f"pubmed-{pmid}", url=url, label="Estudio en PubMed")
    if origin in ("biorxiv", "medrxiv") and doi:
        name = {"biorxiv": "bioRxiv", "medrxiv": "medRxiv"}[origin]
        url = f"https://doi.org/{doi}"
        return Source(id=f"{origin}-{doi}", url=url, label=f"Preprint en {name}")
    if origin == "europepmc" and pmcid:
        url = f"https://europepmc.org/article/PMC/{pmcid}"
        return Source(id=f"pmc-{pmcid}", url=url, label="Estudio en Europe PMC")
    return None


def news_item(
    study: dict[str, Any], derived_root: Path | None = None
) -> tuple[ReviewItem, int] | None:
    """The spot-check item of a published summary and the judge's ``spanish_natural``, or
    None when the summary is not verified in both languages or has no source to check
    her edits against."""
    records = {lang: verified_record(study["study_id"], lang, derived_root=derived_root)
               for lang in LANGS}  # fmt: skip
    facts = load(facts_path(study["study_id"], derived_root))
    if not all(records.values()) or not facts:
        return None
    source = study_source(study, facts.get("abstract_from", ""))
    if source is None:
        return None
    lines = {lang: [Sentence(text=s["text"], cites=[source.id]) for s in records[lang]["sentences"]]
             for lang in LANGS}  # fmt: skip
    item = ReviewItem(
        item_type=ItemType.NEWS,
        item_id=slug(study["study_id"]),
        title_es=study["title"],
        content=TextContent(es=lines["es"], en=lines["en"], sources=[source]),
    )
    return item, records["es"]["judge"].get("spanish_natural", 5)


def summarized(derived_root: Path) -> list[str]:
    """Study ids with a verified Spanish text (the English is checked by ``news_item``)."""
    ids = set()
    for path in (derived_root / "texts").glob("*.es.json"):
        record = load(path)
        if record and record.get("study_id"):
            ids.add(record["study_id"])
    return sorted(ids)


def news_spot_checks(warehouse: Path, derived_root: Path) -> list[ReviewItem]:
    ids = summarized(derived_root)
    if not ids or not warehouse.exists():
        return []
    with duckdb.connect(str(warehouse), read_only=True) as con:
        cur = con.execute(
            "select study_id, title, pmid, pmcid, doi, entered_on from main.dim_study "
            "where study_id in (select unnest(?))",
            [ids],
        )
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]
    found = []
    for row in rows:
        built = news_item(row, derived_root)
        if built:
            item, score = built
            found.append(((score, -row["entered_on"].toordinal(), row["study_id"]), item))
    return [item for _, item in sorted(found, key=lambda x: x[0])]


def run_spot_checks(run_dir: Path) -> list[ReviewItem]:
    """Spot-check items of a past run kept outside ``derived/``: its ``derived/`` folder and
    the ``summary.json`` with each article's title (step 18, the S5 chain with the v2
    prompts; Aday, 2026-11-13, so she rates their Spanish, which the judge does not tell
    apart). The run's folder name goes in ``item_id``, so the texts of two writers on the
    same study are two items; her decisions on them change nothing on the site, which
    looks items up by ``slug(study_id)`` alone. Worst Spanish first, as the spot-check."""
    derived = run_dir / "derived"
    articles = json.loads((run_dir / "summary.json").read_text("utf-8"))["articles"]
    titles = {f"pmid:{a['pmid']}": a["title"] for a in articles}
    found = []
    for sid in summarized(derived):
        if sid not in titles:
            continue
        study = {"study_id": sid, "title": titles[sid], "pmid": sid.removeprefix("pmid:"),
                 "doi": None, "pmcid": None}  # fmt: skip
        built = news_item(study, derived)
        if built:
            item, score = built
            item = item.model_copy(update={"item_id": f"{item.item_id}-{slug(run_dir.name)}"})
            found.append(((score, item.item_id), item))
    return [item for _, item in sorted(found, key=lambda x: x[0])]


def collect(
    warehouse: Path,
    derived_root: Path,
    review_dir: Path,
    today: dt.date,
    extra: list[ReviewItem] | None = None,
) -> Queue:
    """Today's queue: every source, minus what she decided, her held edits first, capped.
    ``extra`` (``run_spot_checks``) goes before the day's spot-check."""
    items = [*(extra or []), *news_spot_checks(warehouse, derived_root)]
    # Midnight UTC of the day: the same inputs give the same file (``syn`` is idempotent).
    queue = Queue(generated_at=dt.datetime.combine(today, dt.time(), dt.UTC), items=items)
    waiting = next_queue(queue, states(queue, read_log(review_dir)))
    held = [i for i in waiting.items if i.warnings]
    rest = [i for i in waiting.items if not i.warnings]
    cap = CAP_WEEKEND if today.weekday() >= 5 else CAP_WEEKDAY
    return waiting.model_copy(update={"items": (held + rest)[:cap]})


def reviewed(
    study: dict[str, Any],
    summary: dict[str, dict[str, Any]],
    events: list[Event],
    derived_root: Path | None = None,
) -> dict[str, dict[str, Any]]:
    """The summary the site shows, after her decisions on it (see the module docstring)."""
    if not events or any(summary[lang]["kind"] != "verified" for lang in LANGS):
        return summary
    built = news_item(study, derived_root)
    if built is None:
        return summary
    st = state(built[0], events)
    if not publishable(st):
        return {lang: {"kind": "fallback", "text": fallback_text(study, lang)} for lang in LANGS}
    if st.status == "edited" and st.text is not None:
        mark = "kept" if st.kept_reason else "edited"
        return {lang: {**summary[lang], "reviewed": mark,
                       "sentences": [{"text": s.text, "fact_ids": []}
                                     for s in getattr(st.text, lang)]}
                for lang in LANGS}  # fmt: skip
    return summary
