"""Spanish titles of the studies the website shows, with an LLM (plan, step 23c; option B
of Aday, SCOPE v122).

What is translated: every study of «Latest» and of Nature · Science · Cell, chosen by the
site's own selection (``site.news``), so both never disagree. Titles go in batches of
:data:`BATCH` to the writer model, with the prompt ``prompts/titles_es.md``. The answers
go to ``derived/titles/es.json`` (committed to the ``data`` branch): one row per study
with the hash of the English title and the prompt version, so a title is asked again only
when it or the prompt changes. Running it twice asks nothing the second time.

No judge (Aday): each Spanish title passes mechanical checks (:func:`check_title`)
against its English title instead, and a title that fails is kept as ``failed`` with its
problems. The site then shows the English original with the «Spanish title pending» gap,
as before this step. A few titles a day go to Sofía's queue (``review.collect``).

The checks, plain string logic so a failure names its reason:

* **numbers**: the same ones (``checks.numbers_match``; small numbers may be words);
* **identifiers**: gene, protein and acronym tokens (an upper-case letter with a digit or
  another upper-case letter: APOE4, TREM2, GLP-1, mGluR5) in both, or their standard
  Spanish form (:data:`ACRONYMS_ES`); none added;
* **names**: the capitalized words inside the English title (Drosophila, Alzheimer),
  without accents or case, unless the title capitalizes every word (Title Case);
* **drugs**: international names by their stem (-mab, -glutide, -oxetine…);
* **organisms**: the same ones (:data:`ORGANISMS`), and abbreviated species as written;
* **claims**: no cure, alarm, causal or predictive phrase the English title does not
  make, and its caution kept (``checks.claims``, the summaries' rule, ADR D4);
* **length**: between :data:`MIN_RATIO` and :data:`MAX_RATIO` of the English title.

The thresholds are a first guess, to be measured on the real test of ~40 titles.
Modelled on ``news/classify.py`` (batches, input hash, prompt version, progress saved).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
from pydantic import BaseModel

from synaptica.config import get_paths
from synaptica.llm import LLM, prompt
from synaptica.narrative import checks
from synaptica.store import _atomic_write

BATCH = 20
MIN_RATIO, MAX_RATIO = 0.6, 1.6
MAX_CHARS = 400

# Standard Spanish forms of English acronyms (the prompt lists the same ones).
ACRONYMS_ES = {
    "DNA": {"ADN"}, "RNA": {"ARN"}, "mRNA": {"ARNm"}, "AI": {"IA"}, "MRI": {"RM", "IRM"},
    "fMRI": {"RMf", "IRMf"}, "ADHD": {"TDAH"}, "ALS": {"ELA"}, "PTSD": {"TEPT"},
    "OCD": {"TOC"}, "ASD": {"TEA"}, "CNS": {"SNC"}, "CSF": {"LCR"}, "HIV": {"VIH"},
}  # fmt: skip
_ES_TO_EN = {es: en for en, forms in ACRONYMS_ES.items() for es in forms}

# Organisms: English pattern -> Spanish pattern. Either side naming one the other does not
# is a problem (a study in mice whose Spanish title says «en personas», or the reverse).
ORGANISMS = {
    "human": (r"\bhumans?\b|\bpeople\b|\bpersons?\b|\bpatients?\b|\badults?\b|\bchildren\b"
              r"|\bchild\b|\binfants?\b|\badolescents?\b|\bparticipants?\b|\bvolunteers?\b"
              r"|\bwomen\b|\bmen\b",
              r"\bhuman[oa]s?\b|\bpersonas?\b|\bpacientes?\b|\badult[oa]s?\b|\bniñ[oa]s?\b"
              r"|\bbeb[eé]s?\b|\blactantes?\b|\badolescentes?\b|\bparticipantes?\b"
              r"|\bvoluntari[oa]s?\b|\bmujeres\b|\bhombres\b"),
    "mouse": (r"\bmouse\b|\bmice\b|\bmurine\b", r"\brat[oó]n\w*|\bmurin[oa]s?\b"),
    "rat": (r"\brats?\b", r"\bratas?\b"),
    "zebrafish": (r"\bzebrafish\b", r"\bpez(?:es)? cebra\b|\bzebrafish\b"),
    "fly": (r"\bflies\b|\bfly\b|\bdrosophila\b", r"\bmoscas?\b|\bdrosophila\b"),
    "worm": (r"\bworms?\b|\belegans\b", r"\bgusanos?\b|\belegans\b"),
    "monkey": (r"\bmonkeys?\b|\bmacaques?\b|\bmarmosets?\b|\bprimates?\b",
               r"\bmonos?\b|\bmacacos?\b|\btit[ií]s?\b|\bprimates?\b"),
    "pig": (r"\bpigs?\b|\bporcine\b|\bswine\b", r"\bcerdos?\b|\bporcin[oa]s?\b"),
    "dog": (r"\bdogs?\b|\bcanine\b", r"\bperros?\b|\bcanin[oa]s?\b"),
    "bird": (r"\bbirds?\b|\bsongbirds?\b|\bzebra finch\w*",
             r"\baves?\b|\bp[aá]jaros?\b|\bdiamantes?\b"),
}  # fmt: skip

# An upper-case letter plus a digit or another upper-case letter: genes, proteins,
# acronyms (APOE4, TREM2, GLP-1, mGluR5, fMRI, SARS-CoV-2, CA1).
_IDENTIFIER = re.compile(r"(?<![\w-])(?=[\w-]*[A-Z])(?=[\w-]*(?:\d|[A-Z][\w-]*[A-Z]|[a-z][A-Z]))"
                         r"[A-Za-z0-9][\w-]*(?<!-)")  # fmt: skip
_ABBREVIATED_SPECIES = re.compile(r"\b[A-Z]\.\s?[a-z]{3,}\b")  # C. elegans, D. melanogaster
_DRUG = re.compile(
    r"\b[a-z]{3,}(?:mab|nib|glutide|zepam|zolam|setron|sartan|pril|statin"
    r"|vir|dopa|caine|oxetine|triptan|azole|profen|olol|ketamine|psilocybin)\b"
)


class ItemTitle(BaseModel):
    index: int
    title_es: str


class BatchTitles(BaseModel):
    items: list[ItemTitle]


@dataclass
class TitlesResult:
    total: int = 0
    up_to_date: int = 0
    translated: int = 0  # passed the checks
    failed: int = 0  # kept with their problems: the site shows the original
    missing: int = 0  # left out by the model (asked again next run)


def titles_path(derived_root: Path | None = None) -> Path:
    root = derived_root if derived_root is not None else get_paths().derived
    return root / "titles" / "es.json"


def warehouse_path() -> Path:
    return get_paths().data / "warehouse.duckdb"


# -- what is translated --------------------------------------------------------------


def titles_to_translate(warehouse: Path) -> dict[str, dict[str, Any]]:
    """study_id -> {title, entered_on} of the studies of «Latest» and of Nature · Science ·
    Cell, as the website selects them."""
    from synaptica.site import news  # the site's own selection, so both never disagree

    with duckdb.connect(str(warehouse), read_only=True) as con:
        con.execute("set TimeZone = 'UTC'")
        (as_of,) = con.execute("select max(entered_on) from main.dim_study").fetchone()
        if as_of is None:
            return {}
        rows = [*news.latest(con, as_of), *news.nature_science_cell(con, as_of)]
    return {r["study_id"]: {"title": r["title"], "entered_on": str(r["entered_on"])}
            for r in rows if r.get("title")}  # fmt: skip


def input_hash(title: str) -> str:
    return hashlib.sha1(title.encode()).hexdigest()[:12]


def load_titles(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    return {row["study_id"]: row for row in json.loads(path.read_text(encoding="utf-8"))}


def save_titles(path: Path, rows: dict[str, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps([rows[k] for k in sorted(rows)], ensure_ascii=False, indent=1)
    _atomic_write(path, text + "\n")


# -- checks --------------------------------------------------------------------------


def _fold(text: str) -> str:
    """Lower case without accents (alzhéimer = Alzheimer)."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def identifiers(text: str) -> set[str]:
    return set(_IDENTIFIER.findall(checks._typography(text)))


def _title_case(text: str) -> bool:
    long_words = [w for w in re.findall(r"[^\W\d_]{4,}", text)]
    return bool(long_words) and sum(w[0].isupper() for w in long_words) / len(long_words) > 0.6


def _organisms(text: str, side: int) -> set[str]:
    return {k for k, pats in ORGANISMS.items() if re.search(pats[side], text, re.IGNORECASE)}


def clean(title: str) -> str:
    """One line, no final full stop (the prompt asks for none; a stop is not a failure)."""
    title = " ".join(title.split())
    return title[:-1].rstrip() if title.endswith(".") and not title.endswith("..") else title


def check_title(en: str, es: str) -> list[str]:
    """Problems of a Spanish title against its English original (empty: it passes)."""
    if not es.strip():
        return ["empty"]
    problems = []
    ratio = len(es) / max(len(en), 1)
    if not MIN_RATIO <= ratio <= MAX_RATIO or len(es) > MAX_CHARS:
        problems.append(f"length {len(es)} for {len(en)} in English")
    if not checks.numbers_match(en, es):
        problems.append(
            f"numbers differ ({sorted(checks.numbers(en))} vs {sorted(checks.numbers(es))})"
        )
    ids_en, ids_es = identifiers(en), identifiers(es)
    for token in sorted(ids_en):
        if token not in ids_es and not ACRONYMS_ES.get(token, set()) & ids_es:
            problems.append(f"'{token}' is missing")
    for token in sorted(ids_es - ids_en):
        if _ES_TO_EN.get(token) not in ids_en:
            problems.append(f"'{token}' is not in the English title")
    folded_es = _fold(es)
    if not _title_case(en):
        for name in sorted(checks.names(en)):
            if _fold(name) not in folded_es:
                problems.append(f"name '{name}' is missing")
    for species in sorted(set(_ABBREVIATED_SPECIES.findall(en))):
        if " ".join(species.split()) not in " ".join(es.split()):
            problems.append(f"species '{species}' is missing")
    for drug in sorted(set(_DRUG.findall(en.lower()))):
        if _fold(drug[: max(5, len(drug) - 3)]) not in folded_es:
            problems.append(f"drug '{drug}' is missing")
    org_en, org_es = _organisms(en, 0), _organisms(es, 1)
    problems += [f"organism '{o}' is missing" for o in sorted(org_en - org_es)]
    problems += [f"organism '{o}' is not in the English title" for o in sorted(org_es - org_en)]
    for key in sorted(checks.claims(es, "es") - checks.claims(en, "en")):
        problems.append(f"says '{key}' and the English title does not")
    if checks._has(checks.HEDGES[0], en) and not checks._has(checks.HEDGES[1], es):
        problems.append("the English title is cautious and this is not")
    return problems


# -- translation ---------------------------------------------------------------------


def translate_batch(
    llm: LLM, system: str, batch: list[tuple[str, dict[str, Any]]]
) -> dict[str, str]:
    lines = [f"{i}. {item['title']}" for i, (_, item) in enumerate(batch, start=1)]
    answer = llm.complete_json(system, "TITLES:\n" + "\n".join(lines), BatchTitles,
                               max_tokens=4_000)  # fmt: skip
    by_index = {t.index: t.title_es for t in answer.items}
    return {key: by_index[i] for i, (key, _) in enumerate(batch, start=1) if i in by_index}


def translate(
    llm: LLM,
    items: dict[str, dict[str, Any]],
    *,
    derived_root: Path | None = None,
    limit: int | None = None,
    now: dt.datetime | None = None,
) -> TitlesResult:
    """Translate the titles that are new, changed or translated with an older prompt.
    Rows of studies no longer shown stay: their title is not asked again if it returns."""
    system, version = prompt("titles_es")
    path = titles_path(derived_root)
    rows = load_titles(path)
    if not path.exists():
        save_titles(path, rows)  # dbt reads the file even when nothing is translated
    result = TitlesResult(total=len(items))
    pending = []
    for sid, item in items.items():
        row = rows.get(sid)
        if (
            row
            and row["input_hash"] == input_hash(item["title"])
            and (row["prompt_version"] == version)
        ):
            result.up_to_date += 1
        else:
            pending.append((sid, item))
    pending.sort(key=lambda kv: (kv[1]["entered_on"], kv[0]), reverse=True)
    pending = pending[:limit] if limit is not None else pending
    stamp = (now or dt.datetime.now(dt.UTC)).isoformat(timespec="seconds")
    for start in range(0, len(pending), BATCH):
        batch = pending[start : start + BATCH]
        answers = translate_batch(llm, system, batch)
        result.missing += len(batch) - len(answers)
        for sid, answer in answers.items():
            en, es = items[sid]["title"], clean(answer)
            problems = check_title(en, es)
            rows[sid] = {
                "study_id": sid, "status": "failed" if problems else "ok",
                # A failed title is kept so it is not asked again, but never shown.
                "title_es": es, "problems": problems, "input_hash": input_hash(en),
                "prompt_version": version, "generator": llm.label, "translated_at": stamp,
            }  # fmt: skip
            if problems:
                result.failed += 1
            else:
                result.translated += 1
        save_titles(path, rows)  # keep progress if the quota runs out mid-way
    return result


def run(
    llm: LLM,
    *,
    warehouse: Path | None = None,
    derived_root: Path | None = None,
    limit: int | None = None,
) -> TitlesResult:
    return translate(
        llm, titles_to_translate(warehouse or warehouse_path()),
        derived_root=derived_root, limit=limit,
    )  # fmt: skip
