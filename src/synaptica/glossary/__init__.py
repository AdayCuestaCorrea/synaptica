"""Neuro Glossary (Phase 2): terms and acronyms, each defined by Sofía's approved text.

The terms are in ``terms.csv``: the 17 samples of ``docs/propuesta.md`` and the 7 she
proposed in her review (``review/decisions.jsonl`` on the data branch, action
``propose``). Each row names the English Wikipedia article that is its source (the
Spanish one is found through its language links, see :mod:`synaptica.glossary.sources`)
and the forms that mark the term in a text:

* ``forms_exact``: acronyms, matched only in their exact case (``DA`` is dopamine, «da»
  is a Spanish verb), the rule of the Phase 1 mock-up (v80);
* ``forms_any_case``: full names in either language, matched in any case.

A definition is published only with her approval recorded in the data (SCOPE §7).
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

TERMS = Path(__file__).with_name("terms.csv")
ORIGINS = ("proposal", "sofia")  # docs/propuesta.md, or proposed by her in her review


@dataclass(frozen=True)
class Term:
    term_id: str
    term: str
    origin: str
    source_en: str  # English Wikipedia article (redirects are followed)
    forms_exact: tuple[str, ...]
    forms_any_case: tuple[str, ...]

    @property
    def pattern(self) -> re.Pattern[str]:
        return form_pattern(self.forms_exact, self.forms_any_case)


def load_terms(path: Path | None = None) -> list[Term]:
    """The terms, in file order; fails on a repeated id or an unknown origin."""
    with (path or TERMS).open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    terms = []
    for r in rows:
        if r["origin"] not in ORIGINS:
            raise ValueError(f"{r['term_id']}: unknown origin {r['origin']!r}")
        terms.append(Term(
            term_id=r["term_id"], term=r["term"], origin=r["origin"], source_en=r["source_en"],
            forms_exact=tuple(x for x in r["forms_exact"].split("|") if x),
            forms_any_case=tuple(x for x in r["forms_any_case"].split("|") if x),
        ))  # fmt: skip
    ids = [t.term_id for t in terms]
    if len(ids) != len(set(ids)):
        raise ValueError(f"repeated term ids: {sorted({i for i in ids if ids.count(i) > 1})}")
    return terms


def form_pattern(exact: tuple[str, ...], any_case: tuple[str, ...]) -> re.Pattern[str]:
    """One alternation of every form (longest first), whole words; acronyms in their case,
    names in any case. Copied and adapted from ``spikes/web/glossary.py`` (v80), itself
    from Paleo Atlas ``src/paleo/site/glossary.py``: here on plain text, not HTML."""
    forms = [(f, False) for f in exact] + [(f, True) for f in any_case]
    alternatives = "|".join(
        ("(?i:{})" if ci else "{}").format(re.escape(f))
        for f, ci in sorted(forms, key=lambda x: len(x[0]), reverse=True)
    )
    return re.compile(rf"(?<![\w-])(?:{alternatives})(?![\w-])")
