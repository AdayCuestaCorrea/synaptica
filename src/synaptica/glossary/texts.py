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
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
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
