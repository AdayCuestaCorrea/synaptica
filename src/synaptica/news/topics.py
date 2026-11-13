"""Topics of Neuro News: «Explora por temas» on the home page and one page per topic
(decision of Aday, 2026-11-13, option B: back from the backlog of v101, without Emotion,
and Sofía can switch each topic off from her review page).

Adapted from the mock-up's ``spikes/web/topics.py`` (SCOPE v81):

* Each topic is a set of MeSH branches (:data:`TOPICS`). Their descriptors and entry terms
  (MeSH synonyms) are in ``mesh/``, copied from the mock-up's cache of NLM's SPARQL.
* A study indexed with MeSH (PubMed, or Europe PMC's MeSH names) gets the topics of its
  descriptors: basis ``mesh``.
* Otherwise (new PubMed records are not indexed yet, preprints never are) the entry terms
  are searched in the title and the author keywords (one mention) or the abstract (at
  least :data:`MIN_MENTIONS`): basis ``text``. The abstract is read from the private cache
  only to tag; nothing of it is written anywhere.
* Media news only have a title: basis ``text``.

Measured in the mock-up (v81), on 178 indexed studies: the text rule agreed with MeSH in
100 % of the Memory and Sleep tags and 95 % of Neurodegeneration; Addiction and
Neuroinflammation had too few cases. Emotion (60 %) is left out until Sofía confirms it.

A topic is shown when it has at least :data:`MIN_ITEMS` studies and news today and she has
not switched it off (``news_topic`` items of her queue; ADR 0005).
"""

from __future__ import annotations

import functools
import json
import re
from collections.abc import Callable
from importlib import resources
from pathlib import Path
from typing import Any

import duckdb

from synaptica.narrative.sources import abstract_for
from synaptica.review.apply import read_log
from synaptica.review.models import Action, ItemType, ReviewItem, ToggleContent

# Topic -> MeSH tree numbers (each with everything under it), names and the art.
TOPICS: dict[str, dict[str, Any]] = {
    "memory": {"trees": ["F02.463.425.540"], "es": "Memoria", "en": "Memory"},
    # Substance-Related Disorders; Behavior, Addictive
    "addiction": {"trees": ["F03.900", "F01.145.527.100.120"], "es": "Adicción",
                  "en": "Addiction"},
    "neurodegeneration": {"trees": ["C10.574"], "es": "Neurodegeneración",
                          "en": "Neurodegeneration"},
    "neuroinflammation": {"trees": ["C10.586"], "es": "Neuroinflamación",
                          "en": "Neuroinflammation"},
    "sleep": {"trees": ["F02.830.855", "F03.870"], "es": "Sueño", "en": "Sleep"},
}  # fmt: skip
# The root descriptor of each branch (added to mesh/ on 2026-11-13; the mock-up's cache
# lacked them): Memory, Substance-Related Disorders, Behavior Addictive, Neurodegenerative
# Diseases, Neuroinflammatory Diseases, Sleep, Sleep Wake Disorders.
ROOTS = {"D008568", "D019966", "D016739", "D019636", "D000090862", "D012890", "D012893"}
MIN_ITEMS = 3  # fewer, and the topic is not shown: an empty carousel card says nothing

# Text matches that are not the topic: immune memory is not Memory.
EXCLUDE = re.compile(r"memory (?:[tb][ -]?cells?|lymphocytes?)|immun\w* memory", re.I)
MIN_TERM = 4  # shorter entry terms are acronyms that collide with other words
COMMON = {"affect"}  # entry terms that are also common English words (measured, v81)
# One passing mention in an abstract is not the topic (measured: every Neurodegeneration
# tag with one mention was false; with two or more, none).
MIN_MENTIONS = 2


@functools.cache
def vocabulary() -> dict[str, dict[str, Any]]:
    folder = resources.files("synaptica.news") / "mesh"
    out = {}
    for topic, spec in TOPICS.items():
        rows = [r for tree in spec["trees"]
                for r in json.loads((folder / f"{tree}.json").read_text("utf-8"))]  # fmt: skip
        out[topic] = {
            "uis": {r["ui"] for r in rows},
            "names": {r["name"].lower() for r in rows},
            # Inverted («Memory, Long-Term») and qualified («Recognition (Psychology)»)
            # forms never appear in prose.
            # The text rule leaves out the root descriptor of each branch («Sleep»,
            # «Memory»): the bare word tags far too much (measured on 711 indexed studies,
            # v118: Memory 39 % right with it). Its MeSH UI still counts above.
            "terms": sorted(
                {
                    r["term"]
                    for r in rows
                    if r["ui"] not in ROOTS
                    and len(r["term"]) >= MIN_TERM
                    and ", " not in r["term"]
                    and "(" not in r["term"]
                    and r["term"].lower() not in COMMON
                }
            ),
        }
    return out


@functools.cache
def _patterns() -> dict[str, re.Pattern[str]]:
    rx = {}
    for topic, v in vocabulary().items():
        alt = "|".join(re.escape(t) for t in sorted(v["terms"], key=len, reverse=True))
        rx[topic] = re.compile(rf"(?<![\w-])(?:{alt})(?:s|es)?(?![\w-])", re.I)
    return rx


def text_topics(head: str, body: str = "") -> set[str]:
    """Topics of a text: one mention in ``head`` (title, keywords) or :data:`MIN_MENTIONS`
    in all of it (``body`` is the abstract)."""
    head, body = EXCLUDE.sub(" ", head), EXCLUDE.sub(" ", body)
    return {t for t, r in _patterns().items()
            if r.search(head) or len(r.findall(head + " " + body)) >= MIN_MENTIONS}  # fmt: skip


def mesh_topics(uis: list[str], names: list[str]) -> set[str]:
    out = set()
    for topic, v in vocabulary().items():
        if v["uis"] & set(uis) or v["names"] & {n.lower() for n in names}:
            out.add(topic)
    return out


def tag_studies(
    warehouse: Path, studies: list[dict[str, Any]], cache_root: Path | None = None,
    abstract: Callable[..., Any] = abstract_for,
) -> dict[str, dict[str, str]]:  # fmt: skip
    """study_id -> {topic: basis} for the given studies (rows of the site)."""
    ids = [s["study_id"] for s in studies]
    if not ids:
        return {}
    with duckdb.connect(str(warehouse), read_only=True) as con:
        tables = con.execute("select table_name from information_schema.tables").fetchall()
        have = {r[0] for r in tables}
        # Without these models (a test warehouse) every study goes by its text.
        pubmed = "int_pubmed__records" in have
        epmc = "stg_europepmc__records" in have
        empty = "[]::varchar[]"
        uis_col = "coalesce(p.mesh_uis, [])" if pubmed else empty
        kw_col = "coalesce(p.keywords, [])" if pubmed else empty
        names_col = "coalesce(e.mesh_names, [])" if epmc else empty
        join_p = "left join int_pubmed__records p on p.pmid = s.pmid" if pubmed else ""
        join_e = (
            "left join (select doi, flatten(list(mesh_names)) as mesh_names "
            "from stg_europepmc__records where doi is not null group by doi) e "
            "on e.doi = s.doi"
            if epmc
            else ""
        )
        rows = con.execute(
            f"select s.study_id, s.title, s.pmid, s.doi, s.pmcid, s.sources, {uis_col}, "
            f"{kw_col}, {names_col} from dim_study s {join_p} {join_e} "
            "where s.study_id in (select unnest(?))",
            [ids],
        ).fetchall()
    out: dict[str, dict[str, str]] = {}
    for sid, title, pmid, doi, pmcid, sources, uis, keywords, names in rows:
        if uis or names:
            found, basis = mesh_topics(uis, names), "mesh"
        else:
            study = {"pmid": pmid, "doi": doi, "pmcid": pmcid, "sources": list(sources or [])}
            text = abstract(study, cache_root=cache_root)
            found = text_topics(" ".join([title or "", *keywords]), text[0] if text else "")
            basis = "text"
        if found:
            out[sid] = dict.fromkeys(sorted(found), basis)
    return out


def switched_off(review_dir: Path) -> set[str]:
    """Topics Sofía switched off (her last decision on each ``news_topic`` item)."""
    last: dict[str, Action] = {}
    for e in read_log(review_dir):
        d = e.decision
        if d.item_type is ItemType.NEWS_TOPIC and d.action in (Action.ENABLE, Action.DISABLE):
            last[d.item_id.removeprefix("topic-")] = d.action
    return {t for t, a in last.items() if a is Action.DISABLE}


def queue_items() -> list[ReviewItem]:
    """One switch per topic for her queue; a decided one leaves it (``next_queue``)."""
    return [ReviewItem(item_type=ItemType.NEWS_TOPIC, item_id=f"topic-{k}",
                       title_es=f"Tema «{v['es']}» en Neuro News",
                       content=ToggleContent(label_es=v["es"], label_en=v["en"]))
            for k, v in TOPICS.items()]  # fmt: skip


def hits(
    studies: list[dict[str, Any]], news: list[dict[str, Any]], tags: dict[str, dict[str, str]],
    off: set[str],
) -> dict[str, dict[str, Any]]:  # fmt: skip
    """topic -> {"studies", "basis", "news"} of the topics shown today, in TOPICS order."""
    out = {}
    for topic in TOPICS:
        if topic in off:
            continue
        mine = [s for s in studies if topic in tags.get(s["study_id"], {})]
        items = [n for n in news if topic in text_topics(n["title"] or "")]
        if len(mine) + len(items) >= MIN_ITEMS:
            out[topic] = {
                "studies": mine,
                "news": items,
                "basis": {s["study_id"]: tags[s["study_id"]][topic] for s in mine},
            }
    return out
