"""Glossary texts: their checks against the Wikipedia sources and the items of Sofía's
review queue.

``texts.csv`` has one row per term: meaning and definition in Spanish and English, and
where each comes from. Spanish: the sample table of ``docs/propuesta.md`` (unreviewed) or
her own text, proposed in her review (``issue#N``). English: a draft written with an LLM
(``llm-draft:<model>:<date>``, Aday's OK on 2026-11-15, v179), which she approves with the
Spanish one.

Each text cites its Wikipedia source in the same language; a term without an accepted
Spanish lead cites the English one in Spanish too (Aday's option a, v179). A text goes to
her queue only if it passes the checks her edits pass (``review.intake.edit_warnings``):
no 8 words copied from the source, and every number and name is in the source or in the
text of the other language. None of this publishes anything: a definition reaches the
site only with her approval recorded in ``review/decisions.jsonl``.

**Her Spanish-only correction** (sheet row 34, Aday's option b): the English is redrafted
in a Claude Code session from her Spanish, with Aday's OK on each draft. ``awaiting_en``
lists the terms waiting for it; ``with_english_draft`` writes her Spanish (origin: her
Issue) and the draft (``llm-draft``) to ``texts.csv`` only if both pass the checks. The
text changed, so the item is back in her queue for her yes on the English; until then the
site keeps her Spanish and the English gap (``published``, the same «her exact words»
rule as her proposals).
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from synaptica.glossary import Term
from synaptica.glossary.sources import LANGS
from synaptica.narrative import checks
from synaptica.review.models import ItemType, ReviewItem, Sentence, Source, TextContent

TEXTS = Path(__file__).with_name("texts.csv")
_ORIGIN = re.compile(r"^(docs/propuesta\.md|issue#\d+|llm-draft:[\w.-]+:\d{4}-\d{2}-\d{2})$")


@dataclass(frozen=True)
class Text:
    term_id: str
    meaning: dict[str, str]
    definition: dict[str, str]
    origin: dict[str, str]

    def sentence(self, term: Term, lang: str) -> str:
        """One line, the shape the review page reads a term from («NMDA (…): …»)."""
        return f"{term.term} ({self.meaning[lang]}): {self.definition[lang]}"


def load_texts(path: Path | None = None) -> dict[str, Text]:
    with (path or TEXTS).open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    out = {}
    for r in rows:
        for lang in LANGS:
            if not (r[f"meaning_{lang}"] and r[f"definition_{lang}"]):
                raise ValueError(f"{r['term_id']}: empty text in {lang}")
            if not _ORIGIN.match(r[f"{lang}_from"]):
                raise ValueError(f"{r['term_id']}: unknown origin {r[f'{lang}_from']!r}")
        out[r["term_id"]] = Text(
            term_id=r["term_id"],
            meaning={lang: r[f"meaning_{lang}"] for lang in LANGS},
            definition={lang: r[f"definition_{lang}"] for lang in LANGS},
            origin={lang: r[f"{lang}_from"] for lang in LANGS},
        )
    return out


def cited(source: dict[str, Any], lang: str) -> tuple[str, dict[str, Any]] | None:
    """(source lang, source) a text in ``lang`` cites: its own language, else English."""
    for src_lang in (lang, "en"):
        entry = (source or {}).get(src_lang) or {}
        if entry.get("accepted"):
            return src_lang, entry
    return None


def problems(term: Term, text: Text, source: dict[str, Any]) -> list[str]:
    """What fails in a term's texts (empty: both pass), in Spanish, as her warnings."""
    out = []
    for lang in LANGS:
        label = "español" if lang == "es" else "inglés"
        found = cited(source, lang)
        if found is None:
            out.append(f"({label}) Sin fuente de Wikipedia aceptada.")
            continue
        lead = found[1]["lead"]
        mine = text.sentence(term, lang)
        other = text.sentence(term, "en" if lang == "es" else "es")
        known_numbers = checks.numbers(lead) | checks.numbers(other)
        known_names = {n.lower() for n in checks.names(lead) | checks.names(other)}
        known_names |= {w.lower() for w in re.findall(r"[\w-]+", lead + " " + other)}
        known_names |= {f.lower() for f in term.forms_exact + term.forms_any_case}
        for n in sorted(checks.numbers(mine) - known_numbers):
            out.append(f"({label}) La cifra {n} no está en la fuente ni en el otro idioma.")
        # Meaning and definition apart: each opens with a capital, which is not a name
        # (the same reason her edits are checked sentence by sentence).
        parts = (text.meaning[lang], text.definition[lang])
        for name in sorted(set().union(*map(checks.names, parts))):
            if name.lower() not in known_names:
                out.append(f"({label}) «{name}» no aparece en la fuente ni en el otro idioma.")
        for run in checks.copied_runs(mine, checks.ngrams(checks.words(lead))):
            out.append(f"({label}) Copia 8 palabras seguidas de la fuente: «{run}».")
    return out


def _source(term_id: str, lang: str, entry: dict[str, Any]) -> Source:
    name = "Wikipedia en inglés" if lang == "en" else "Wikipedia en español"
    return Source(id=f"wikipedia-{lang}-{term_id}", url=entry["url"],
                  label=f"{name}: «{entry['title']}» (revisión {entry['revid']})")  # fmt: skip


def queue_item(term: Term, text: Text, source: dict[str, Any]) -> ReviewItem | None:
    """Her review item for a term, or None if its texts fail a check or lack a source."""
    if problems(term, text, source):
        return None
    sentences, sources = {}, {}
    for lang in LANGS:
        src_lang, entry = cited(source, lang)  # type: ignore[misc]  # problems() checked it
        s = _source(term.term_id, src_lang, entry)
        sources[s.id] = s
        sentences[lang] = [Sentence(text=text.sentence(term, lang), cites=[s.id])]
    content = TextContent(es=sentences["es"], en=sentences["en"],
                          sources=sorted(sources.values(), key=lambda s: s.id))  # fmt: skip
    return ReviewItem(item_type=ItemType.GLOSSARY, item_id=term.term_id, title_es=term.term,
                      content=content)  # fmt: skip


def review_items() -> list[ReviewItem]:
    """Her review items for every term whose texts pass, in the order of ``terms.csv``."""
    from synaptica.glossary import load_terms
    from synaptica.glossary.sources import load_sources

    texts, sources = load_texts(), load_sources()
    items = [queue_item(t, texts[t.term_id], sources.get(t.term_id, {})) for t in load_terms()]
    return [i for i in items if i is not None]


# ---- what the site shows -------------------------------------------------------------

PUBLISHED = ("approved", "edited")  # her approval, or her correction that passed (or kept)


@dataclass(frozen=True)
class Entry:
    """A term the site shows: approved or corrected by her, at the current version."""

    term: Term
    meaning: dict[str, str | None]  # None: her text has no «TERM (meaning):» opening
    definition: dict[str, str | None]  # None in English: her Spanish edit awaits its English
    sources: list[Source]
    reviewed_at: str
    mark: str  # approved | edited | kept


def _split(term: Term, text: str) -> tuple[str | None, str]:
    """«NMDA (N-metil-D-aspartato): Tipo de receptor…» -> meaning, definition. Greedy, so
    a meaning with brackets inside («5-hidroxitriptamina (serotonina)») stays whole."""
    m = re.match(rf"{re.escape(term.term)} \((.+)\):\s*(.+)", text, re.S)
    return (m.group(1), m.group(2)) if m else (None, text)


def published(review_dir: Path | None) -> list[Entry]:
    """The terms she approved or corrected, in the version on the table today. Pending,
    rejected or held terms are left out, and so is a decision on an older version (its
    text, source or draft changed since: the hash, as everywhere in the review). Unlike
    the summaries (``apply.publishable``, already public), nothing shows before her yes.

    One more way in (Aday's option B, v183): a term she proposed herself in her review
    (action ``propose``) shows her Spanish, as she wrote it, before she sees its item:
    only if ``texts.csv`` carries her words exactly and they pass the checks (the item
    exists). Its English is a draft she has not seen, so the English page shows the gap
    until she approves the item; her rejection of the item takes the term off."""
    from synaptica.review.apply import read_log, state

    events = read_log(review_dir) if review_dir is not None and review_dir.exists() else []
    proposed, edits = _proposed(events), _her_edits(events)
    texts = load_texts()
    out = []
    for item in review_items():
        st = state(item, events)
        term = next(t for t in _terms() if t.term_id == item.item_id)
        if st.status not in PUBLISHED or st.reviewed_by is None or st.reviewed_at is None:
            entry = _her_proposal(term, texts[term.term_id], item, st.status, proposed, edits)
            if entry is not None:
                out.append(entry)
            continue
        content = st.text or item.content
        assert isinstance(content, TextContent)
        meaning: dict[str, str | None] = {}
        definition: dict[str, str | None] = {}
        for lang in LANGS:
            if lang == "en" and st.awaiting_en:
                meaning[lang] = definition[lang] = None
                continue
            text = " ".join(s.text for s in getattr(content, lang))
            meaning[lang], definition[lang] = _split(term, text)
        mark = "kept" if st.kept_reason else st.status
        out.append(Entry(term=term, meaning=meaning, definition=definition,
                         sources=list(content.sources),
                         reviewed_at=st.reviewed_at.date().isoformat(), mark=mark))  # fmt: skip
    return out


def _her_edits(events: list[Any]) -> dict[str, Any]:
    """Her latest applied Spanish-only correction of each term (not held), by term id."""
    from synaptica.review.models import Action

    out = {}
    for e in events:
        d = e.decision
        if (d.item_type is ItemType.GLOSSARY and d.action is Action.EDIT and not e.held
                and d.payload.get("es") and not d.payload.get("en")):  # fmt: skip
            out[d.item_id] = d
    return out


def _proposed(events: list[Any]) -> dict[str, Any]:
    """Her latest proposal of each term, by the term as she wrote it."""
    from synaptica.review.models import Action

    out = {}
    for e in events:
        d = e.decision
        if d.item_type is ItemType.GLOSSARY and d.action is Action.PROPOSE and not e.held:
            out[str(d.payload.get("term", ""))] = d
    return out


def _her_proposal(term: Term, text: Text, item: ReviewItem, status: str,
                  proposed: dict[str, Any], edits: dict[str, Any]) -> Entry | None:  # fmt: skip
    """Her own Spanish while its item waits for her: a term she proposed (option B, v183)
    or one whose English was redrafted after her Spanish-only correction (row 34). Only
    when ``texts.csv`` carries her words exactly, from that very Issue; None otherwise."""
    if status == "rejected" or not text.origin["es"].startswith("issue#"):
        return None
    mine = (text.meaning["es"], text.definition["es"])
    d, mark = proposed.get(term.term), "proposed"
    if d is None or (d.payload.get("meaning_es"), d.payload.get("explanation_es")) != mine:
        d, mark = edits.get(term.term_id), "edited"
        if d is None or d.source != text.origin["es"]:
            return None
        if _split(term, d.payload["es"].strip()) != mine:
            return None  # not her words: never shown as hers
    return Entry(term=term, meaning={"es": text.meaning["es"], "en": None},
                 definition={"es": text.definition["es"], "en": None},
                 sources=list(item.content.sources),
                 reviewed_at=d.reviewed_at.date().isoformat(), mark=mark)  # fmt: skip


# ---- the English after her Spanish-only correction (row 34) -------------------------


@dataclass(frozen=True)
class Awaiting:
    term: Term
    meaning_es: str | None  # None: her text lost the «TERM (meaning):» opening
    definition_es: str
    source: str  # her Issue
    english_now: str  # the draft she corrected the Spanish of, for reference


def awaiting_en(review_dir: Path | None) -> list[Awaiting]:
    """Terms whose Spanish she corrected alone, still waiting for their English."""
    from synaptica.review.apply import read_log, state

    events = read_log(review_dir) if review_dir is not None and review_dir.exists() else []
    edits, texts = _her_edits(events), load_texts()
    out = []
    for item in review_items():
        st = state(item, events)
        if st.status != "edited" or not st.awaiting_en or item.item_id not in edits:
            continue
        term = next(t for t in _terms() if t.term_id == item.item_id)
        meaning, definition = _split(term, edits[item.item_id].payload["es"].strip())
        out.append(Awaiting(term, meaning, definition, edits[item.item_id].source,
                            texts[term.term_id].sentence(term, "en")))  # fmt: skip
    return out


COLUMNS = ("term_id", "meaning_es", "definition_es", "es_from",
           "meaning_en", "definition_en", "en_from")  # fmt: skip


def with_english_draft(
    waiting: Awaiting, meaning_en: str, definition_en: str, model: str,
    today: dt.date, path: Path | None = None,
) -> list[str]:  # fmt: skip
    """Write her Spanish and the English draft to ``texts.csv``: the problems found
    (nothing written) or [] (written). Her text must keep «TERM (meaning):»."""
    if waiting.meaning_es is None:
        return ["Su texto no empieza por «SIGLA (significado):»: hay que separarlo a mano."]
    from synaptica.glossary.sources import load_sources

    path = path or TEXTS
    term = waiting.term
    texts = load_texts(path)
    new = replace(texts[term.term_id],
                  meaning={"es": waiting.meaning_es, "en": meaning_en.strip()},
                  definition={"es": waiting.definition_es, "en": definition_en.strip()},
                  origin={"es": waiting.source,
                          "en": f"llm-draft:{model}:{today.isoformat()}"})  # fmt: skip
    found = problems(term, new, load_sources().get(term.term_id, {}))
    if found:
        return found
    texts[term.term_id] = new
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(COLUMNS)
    for t in texts.values():
        writer.writerow([t.term_id, t.meaning["es"], t.definition["es"], t.origin["es"],
                         t.meaning["en"], t.definition["en"], t.origin["en"]])  # fmt: skip
    path.write_text(buf.getvalue(), encoding="utf-8")
    return []


def _terms() -> list[Term]:
    from synaptica.glossary import load_terms

    return load_terms()
