"""What Neuro News shows (plan, step 23): studies and media stories read from the warehouse.

Adapted from the «Noche» mock-up (``spikes/web/collect.py``: ``latest``,
``nature_science_cell``, ``outlet_news``, ``original_url``, ``news_type``; and
``spikes/web/build.py``: ``signals``, ``licence_lines``, ``short_journal``, ``fmt_date``),
without its mock-up shortcuts: no title regex stands in for the classifier (step 14a), so
until it runs the unclassified studies are shown and the page says so with a gap.

Everything is read-only: ``dim_study`` and ``fct_news_item`` (the warehouse), the verified
texts in ``derived/`` through ``narrative.fallback.summary_for`` and
``narrative.weekly.weekly_for``. No abstract is ever read here (they live in ``cache/``).

"Today" is the newest ``entered_on`` in the warehouse, not the clock: the same data always
builds the same site (``syn`` commands are idempotent).
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import duckdb

from synaptica.narrative import weekly
from synaptica.narrative.fallback import print_issue, summary_for
from synaptica.narrative.write import slug
from synaptica.review.apply import Event, read_log
from synaptica.review.collect import reviewed

# How much each block shows (Aday, step 23, option 1A).
LATEST_DAYS = 7  # «Latest»: studies that entered in the last 7 days…
LATEST_MAX = 200  # …at most this many, newest first
PAGE = 30  # shown at first; «See more» shows the next 30 (all of them without JavaScript)
NSC_DAYS = 30  # Nature · Science · Cell: few a day, so a month
MEDIA_DAYS = 7
MEDIA_MAX = 60
TODAY_HEADLINES = 3

TRIAL_TYPES = {
    "Clinical Trial", "Randomized Controlled Trial", "Clinical Trial, Phase I",
    "Clinical Trial, Phase II", "Clinical Trial, Phase III", "Clinical Trial, Phase IV",
    "Controlled Clinical Trial",
}  # fmt: skip
TYPES = ("healthy_brain", "disease", "clinical_trial", "technique")
EXAMPLE_STATES = ("retracted", "corrected", "preprint")  # «How we evaluate» (option 7A)

STUDY_COLUMNS = (
    "study_id", "doi", "pmid", "pmcid", "title", "journal", "published_on", "entered_on",
    "authors", "sources", "review_status", "species", "integrity", "integrity_notices",
    "license", "publication_types", "news_type",
)  # fmt: skip
SOURCE_NAMES = {
    "pubmed": "PubMed (NLM)", "europepmc": "Europe PMC", "biorxiv": "bioRxiv",
    "medrxiv": "medRxiv", "journals": "RSS", "crossref": "Crossref",
}  # fmt: skip
LICENCE_NAMES = {
    "cc by": "CC BY", "cc-by": "CC BY", "cc_by": "CC BY",
    "cc by-sa": "CC BY-SA", "cc-by-sa": "CC BY-SA", "cc_by_sa": "CC BY-SA",
    "cc by-nd": "CC BY-ND", "cc-by-nd": "CC BY-ND", "cc_by_nd": "CC BY-ND",
    "cc by-nc": "CC BY-NC", "cc-by-nc": "CC BY-NC", "cc_by_nc": "CC BY-NC",
    "cc by-nc-sa": "CC BY-NC-SA", "cc-by-nc-sa": "CC BY-NC-SA", "cc_by_nc_sa": "CC BY-NC-SA",
    "cc by-nc-nd": "CC BY-NC-ND", "cc-by-nc-nd": "CC BY-NC-ND", "cc_by_nc_nd": "CC BY-NC-ND",
    "cc0": "CC0", "cc-0": "CC0", "cc0_ng": "CC0",
}  # fmt: skip
MONTHS = {
    "es": ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sept", "oct", "nov", "dic"],
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sept", "Oct", "Nov", "Dec"],
}  # fmt: skip
LONG_MONTHS = {
    "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
           "septiembre", "octubre", "noviembre", "diciembre"],
    "en": ["January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December"],
}  # fmt: skip
WEEKDAYS = {
    "es": ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"],
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
}


@dataclass
class NewsData:
    """Everything the news blocks need, already in display order."""

    as_of: dt.date
    latest: list[dict[str, Any]]
    nsc: list[dict[str, Any]]
    stories: list[list[dict[str, Any]]]  # each story: its items, newest first
    examples: dict[str, dict[str, Any] | None]
    week: str
    week_studies: list[dict[str, Any]]
    week_text: dict[str, dict[str, Any]]  # lang -> weekly_for(...)
    by_id: dict[str, dict[str, Any]] = field(default_factory=dict)  # every study with a page

    @property
    def lead(self) -> dict[str, Any] | None:
        """The featured study of «Today»: the newest with a verified summary in both
        languages; without any, the newest study (shown with its fallback text)."""
        pool = self.nsc + self.latest
        pool = sorted(pool, key=lambda s: (s["entered_on"] or "", s["study_id"]), reverse=True)
        verified = [s for s in pool if all(v["kind"] == "verified"
                                           for v in s["summary"].values())]  # fmt: skip
        return (verified or self.latest or self.nsc or [None])[0]

    @property
    def fact(self) -> dict[str, Any] | None:
        """The fact of the day (plan, step 26; Aday, 2026-11-13: a fact already verified,
        with its source). One sentence of a summary verified in both languages and passed
        by the judge, from a study other than the lead: its second sentence (where the
        summaries give the result) or the only one. Which study changes with the day and
        is the same on every rebuild of that day. None without such a summary."""
        lead = self.lead
        pool = sorted((s for s in self.nsc + self.latest if s is not lead
                       and all(v["kind"] == "verified" and v.get("sentences")
                               for v in s["summary"].values())),
                      key=lambda s: s["study_id"])  # fmt: skip
        if not pool:
            return None
        study = pool[self.as_of.toordinal() % len(pool)]
        text = {}
        for lang, summary in study["summary"].items():
            sentences = summary["sentences"]
            text[lang] = sentences[min(1, len(sentences) - 1)]["text"]
        return {"study": study, "text": text}

    @property
    def headlines(self) -> list[dict[str, Any]]:
        lead = self.lead
        return [s for s in self.latest if s is not lead][:TODAY_HEADLINES]


# -- one study -------------------------------------------------------------------------------


def iso(value: Any) -> Any:
    return value.isoformat() if isinstance(value, dt.date | dt.datetime) else value


def original_url(row: dict[str, Any]) -> str | None:
    if row.get("doi"):
        return f"https://doi.org/{row['doi']}"
    if row.get("pmid"):
        return f"https://pubmed.ncbi.nlm.nih.gov/{row['pmid']}/"
    if row.get("pmcid"):
        return f"https://europepmc.org/article/PMC/{row['pmcid'].removeprefix('PMC')}"
    return None


def study_type(row: dict[str, Any]) -> str | None:
    """Clinical trial is known from PubMed's publication type; the rest comes from the
    classifier (step 14a) and is None until it runs. Noise is never shown."""
    if TRIAL_TYPES & set(row.get("publication_types") or []):
        return "clinical_trial"
    kind = row.get("news_type")
    return kind if kind in TYPES else None


def study_record(
    row: dict[str, Any], derived_root: Path | None, events: list[Event] | None = None
) -> dict[str, Any]:
    row = {k: iso(v) for k, v in row.items()}
    summary = {lang: summary_for(row, lang, derived_root=derived_root) for lang in ("es", "en")}
    summary = reviewed(row, summary, events or [], derived_root)  # Sofía's spot-check (step R)
    issue = print_issue(row)
    # The card's date: the publication day, or the day it entered when the publication date
    # is a print issue still to come (shown apart, as «issue of January 2027»; SCOPE v102).
    shown_on = row["entered_on"] if issue else row["published_on"]
    return {**row, "slug": slug(row["study_id"]), "type": study_type(row),
            "url": original_url(row), "summary": summary, "shown_on": shown_on,
            "issue_on": iso(issue)}  # fmt: skip


def licence_name(value: str | None) -> str | None:
    if not value:
        return None
    return LICENCE_NAMES.get(value.strip().lower())


def model_name(generator: str) -> str:
    """``groq/qwen3.8-27b`` → ``qwen3.8-27b (groq)``."""
    provider, _, model = generator.partition("/")
    return f"{model} ({provider})" if model else generator


def licence_lines(study: dict[str, Any], lang: str, t: dict[str, str]) -> list[str]:
    s = study["summary"][lang]
    if s["kind"] == "verified":
        lines = [t["lic_text_verified"].format(gen=model_name(s["generator"]),
                                               judge=model_name(s["judge"]))]  # fmt: skip
    else:
        lines = [t["lic_text_fallback"]]
    src = ", ".join(SOURCE_NAMES.get(x, x) for x in study.get("sources") or [])
    lines.append(t["lic_meta"].format(src=src))
    lic = licence_name(study.get("license"))
    if (study.get("license") or "").lower() == "cc_no":  # bioRxiv: no reuse without permission
        lines.append(t["lic_original_closed"])
    else:
        lines.append(t["lic_original"].format(lic=lic) if lic else t["lic_original_none"])
    return lines


def signals(study: dict[str, Any], t: dict[str, str]) -> list[dict[str, Any]]:
    """The three signals, each with a state (colour) and its words; never left empty."""
    review = study.get("review_status") or "unknown"
    species = study.get("species") or "unknown"
    integrity = study.get("integrity") or "none"
    return [
        {"key": "review", "label": t["sig_review"], "state": review,
         "text": t[f"rev_{review}"], "short": t.get(f"rev_{review}_short", t[f"rev_{review}"]),
         "provisional": review == "journal", "notices": []},
        {"key": "subject", "label": t["sig_subject"], "state": species,
         "text": t[f"sp_{species}"], "short": t[f"sp_{species}"], "provisional": False,
         "notices": []},
        {"key": "integrity", "label": t["sig_integrity"], "state": integrity,
         "text": t[f"int_{integrity}"], "short": t[f"int_{integrity}"], "provisional": False,
         "notices": study.get("integrity_notices") or []},
    ]  # fmt: skip


def short_journal(name: str | None) -> str | None:
    """PubMed's long titles («Journal of clinical sleep medicine : JCSM : official…») cut at
    the first colon or parenthesis; the full name stays on the study page."""
    if not name:
        return None
    return re.split(r" ?[:(]", name, maxsplit=1)[0].strip()


def fmt_month(value: Any, lang: str) -> str | None:
    """«enero de 2027» / «January 2027», for a print issue."""
    if not value:
        return None
    d = dt.date.fromisoformat(str(iso(value))[:10])
    m = LONG_MONTHS[lang][d.month - 1]
    return f"{m} de {d.year}" if lang == "es" else f"{m} {d.year}"


def fmt_date(value: Any, lang: str, long: bool = False) -> str | None:
    if not value:
        return None
    d = dt.date.fromisoformat(str(iso(value))[:10])
    if long:
        m = LONG_MONTHS[lang][d.month - 1]
        if lang == "es":
            return f"{WEEKDAYS[lang][d.weekday()]}, {d.day} de {m} de {d.year}"
        return f"{WEEKDAYS[lang][d.weekday()]}, {d.day} {m} {d.year}"
    return f"{d.day} {MONTHS[lang][d.month - 1]} {d.year}"


# -- the warehouse ---------------------------------------------------------------------------


def _rows(con: duckdb.DuckDBPyConnection, sql: str, params: list[Any]) -> list[dict[str, Any]]:
    cur = con.execute(sql, params)
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r, strict=True)) for r in cur.fetchall()]


_SELECT = f"select {', '.join(STUDY_COLUMNS)} from main.dim_study"
_NOT_NOISE = "coalesce(news_type, '') != 'noise'"
# Newest first; a journal's issue date can be months ahead of today (PubMed's print date),
# so a date after the day it entered does not push a study to the top.
_NEWEST = "order by entered_on desc, least(published_on, entered_on) desc nulls last, study_id"


def latest(con: duckdb.DuckDBPyConnection, as_of: dt.date) -> list[dict[str, Any]]:
    """Candidates of the last days, not from the general journals (their own block)."""
    return _rows(con, f"""
        {_SELECT} where news_candidate and not list_contains(sources, 'journals')
          and {_NOT_NOISE} and entered_on > ? {_NEWEST} limit ?
    """, [as_of - dt.timedelta(days=LATEST_DAYS), LATEST_MAX])  # fmt: skip


def nature_science_cell(con: duckdb.DuckDBPyConnection, as_of: dt.date) -> list[dict]:
    """Every neuroscience paper of their feeds, not hand-picked."""
    return _rows(con, f"""
        {_SELECT} where list_contains(sources, 'journals') and is_neuro and {_NOT_NOISE}
          and entered_on > ? {_NEWEST}
    """, [as_of - dt.timedelta(days=NSC_DAYS)])  # fmt: skip


def media_stories(con: duckdb.DuckDBPyConnection, as_of: dt.date) -> list[list[dict]]:
    """Headline, outlet, language, date, link and licence of each outlet item, grouped by
    story (step 15). The feed summary is never shown: only our own texts are published."""
    rows = _rows(con, """
        select n.news_item_id, n.story_id, n.outlet, n.lang, n.url, n.title,
               coalesce(n.published_at, n.entered_on) as published_at, f.license
        from main.fct_news_item as n left join main.news_feeds as f using (feed)
        where n.origin = 'outlet' and n.is_neuro
          and coalesce(n.published_at, n.entered_on) > ?
        order by coalesce(n.published_at, n.entered_on) desc, n.news_item_id limit ?
    """, [as_of - dt.timedelta(days=MEDIA_DAYS), MEDIA_MAX])  # fmt: skip
    stories: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        stories.setdefault(r["story_id"], []).append({k: iso(v) for k, v in r.items()})
    return list(stories.values())


def examples(con: duckdb.DuckDBPyConnection) -> dict[str, dict[str, Any] | None]:
    """One real study per state for «How we evaluate»; None (a gap) when there is none."""
    where = {
        "retracted": "integrity in ('retracted', 'partially_retracted')",
        "corrected": "integrity = 'corrected'",
        "preprint": "review_status = 'preprint' and integrity = 'none' and news_candidate",
    }
    out: dict[str, dict[str, Any] | None] = {}
    for state in EXAMPLE_STATES:
        rows = _rows(con, f"{_SELECT} where {where[state]} and is_neuro and title is not null "
                          f"{_NEWEST} limit 1", [])  # fmt: skip
        out[state] = rows[0] if rows else None
    return out


def week_rows(con: duckdb.DuckDBPyConnection, ids: list[str]) -> list[dict[str, Any]]:
    if not ids:
        return []
    rows = {r["study_id"]: r for r in _rows(con, f"{_SELECT} where list_contains(?, study_id)",
                                            [ids])}  # fmt: skip
    return [rows[i] for i in ids if i in rows]


def load(
    warehouse: Path, derived_root: Path | None = None, review_dir: Path | None = None
) -> NewsData | None:
    """The news data, or None when there is no warehouse (``syn build`` has not run).
    ``review_dir``: Sofía's decision log, applied to the summaries shown."""
    if not warehouse.exists():
        return None
    events = read_log(review_dir) if review_dir else []
    with duckdb.connect(str(warehouse), read_only=True) as con:
        con.execute("set TimeZone = 'UTC'")  # dates in UTC, whatever the machine's zone
        (as_of,) = con.execute("select max(entered_on) from main.dim_study").fetchone()
        if as_of is None:
            return None

        def records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
            return [study_record(r, derived_root, events) for r in rows]

        key = weekly.last_week(as_of)
        chosen = weekly.choose(weekly.candidates(key, warehouse), derived_root)
        week_text = {lang: weekly.weekly_for(key, chosen, lang, derived_root=derived_root)
                     for lang in ("es", "en")}  # fmt: skip
        ids = week_text["en"].get("studies") or [s["study_id"] for s in chosen]
        data = NewsData(
            as_of=as_of,
            latest=records(latest(con, as_of)),
            nsc=records(nature_science_cell(con, as_of)),
            stories=media_stories(con, as_of),
            examples={
                k: (study_record(v, derived_root, events) if v else None)
                for k, v in examples(con).items()
            },
            week=key,
            week_studies=records(week_rows(con, ids)),
            week_text=week_text,
        )
    for s in [*data.latest, *data.nsc, *data.week_studies,
              *(e for e in data.examples.values() if e)]:  # fmt: skip
        data.by_id.setdefault(s["study_id"], s)
    return data
