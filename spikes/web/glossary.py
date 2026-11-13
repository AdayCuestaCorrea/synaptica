"""The glossary in the mock-up: terms marked in the texts of the site, their definitions
(with the glossary terms they use, marked too) and the glossary page.

Copied and adapted from Paleo Atlas, ``src/paleo/site/glossary.py`` (same author, AGPL).
Changes:

* the terms are the 17 samples of ``docs/propuesta.md`` (definitions in Spanish only, still
  to review by Sofía); their forms are in ``data/glossary_forms.csv``;
* acronyms match only in their exact case (``DA`` is dopamine, «da» is a Spanish verb);
  full names match in any case. Paleo matches every form in any case;
* forms are shared by both languages (an English title on a Spanish page still has
  «prefrontal cortex»), because the titles are the original English ones;
* a term without a definition in a language is not dropped (Paleo drops it): it is marked
  and its popover and entry say the definition is pending. That is the mock-up's rule for
  gaps: visible and labelled, never filled in;
* no categories and no Wikipedia source: the source is the proposal Sofía approved.

A term is marked the first time it appears on a page, as a link to its entry in the
glossary page, so it works without JavaScript; glossary.js turns it into a popover.
"""

from __future__ import annotations

import csv
import html
import re
import unicodedata
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent


def load_rows() -> list[dict[str, Any]]:
    """The sample terms: meaning and definition from docs/propuesta.md (Spanish), forms
    from data/glossary_forms.csv. English definitions do not exist yet: left empty."""
    text = (HERE.parent.parent / "docs/propuesta.md").read_text(encoding="utf-8")
    block = text.split("## Neuro Glossary: primeros términos", 1)[1].split("\n## ", 1)[0]
    rx = r"^\| (?!Término|---)(.+?) \| (.+?) \| (.+?) \|$"
    table = {a: (b, c) for a, b, c in re.findall(rx, block, re.M)}
    rows = []
    with (HERE / "data/glossary_forms.csv").open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            meaning, what = table.pop(r["term"])
            rows.append({
                "term_id": r["term_id"], "term": r["term"],
                "forms_exact": [x for x in r["forms_exact"].split("|") if x],
                "forms_any_case": [x for x in r["forms_any_case"].split("|") if x],
                "meaning_es": meaning, "definition_es": what,
                "meaning_en": "", "definition_en": "",
            })  # fmt: skip
    if table:
        raise SystemExit(f"terms of the proposal without forms: {sorted(table)}")
    return rows


def _pattern(exact: list[str], any_case: list[str]) -> re.Pattern[str] | None:
    """One alternation of every form (longest first), whole words; acronyms in their case,
    names in any case. Forms are matched on escaped HTML text, so they are escaped too."""
    forms = [(f, False) for f in exact] + [(f, True) for f in any_case]
    if not forms:
        return None
    alternatives = "|".join(
        ("(?i:{})" if ci else "{}").format(re.escape(html.escape(f, quote=False)))
        for f, ci in sorted(forms, key=lambda x: len(x[0]), reverse=True)
    )
    return re.compile(rf"(?<![\w-])(?:{alternatives})(?![\w-])", re.U)


def sort_key(text: str) -> str:
    return unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode().lower()


class Glossary:
    """The glossary in one language."""

    def __init__(self, rows: list[dict[str, Any]], lang: str, page_url: str) -> None:
        self.lang = lang
        self.page_url = page_url
        self.terms = {r["term_id"]: r for r in rows}
        self._exact: dict[str, str] = {}
        self._any: dict[str, str] = {}
        for r in rows:
            for form in r["forms_exact"]:
                self._exact.setdefault(form, r["term_id"])
            for form in r["forms_any_case"]:
                self._any.setdefault(form.lower(), r["term_id"])
        self._pattern = _pattern(list(self._exact), list(self._any))

    def key_of(self, written: str) -> str | None:
        written = html.unescape(written)
        return self._exact.get(written) or self._any.get(written.lower())

    def mark(self, escaped: str, used: set[str], skip: str | None = None,
             page_url: str | None = None) -> str:  # fmt: skip
        """Mark in already-escaped text the first appearance of each term not in
        ``used`` (which is updated), except ``skip`` (a definition never marks its own
        term)."""
        if self._pattern is None:
            return escaped
        base = self.page_url if page_url is None else page_url

        def repl(m: re.Match[str]) -> str:
            key = self.key_of(m.group(0))
            if key is None or key in used or key == skip:
                return m.group(0)
            used.add(key)
            return f'<a class="gl" href="{base}#{key}" data-gl="{key}">{m.group(0)}</a>'

        return self._pattern.sub(repl, escaped)

    def pending(self, term_id: str) -> bool:
        return not self.terms[term_id][f"definition_{self.lang}"]

    def definition_html(self, term_id: str, page_url: str | None = None) -> str:
        """The definition, escaped, with the other glossary terms it uses marked; empty
        when it does not exist in this language."""
        r = self.terms[term_id]
        if self.pending(term_id):
            return ""
        text = html.escape(f"{r[f'meaning_{self.lang}']}. {r[f'definition_{self.lang}']}.",
                           quote=False)  # fmt: skip
        return self.mark(text, set(), skip=term_id, page_url=page_url)

    def closure(self, ids: set[str]) -> list[str]:
        """The terms a page needs: those it marks and, recursively, those their
        definitions mark (a popover can open the definition of a term inside another)."""
        todo, seen = list(ids), set(ids)
        while todo:
            for key in re.findall(r'data-gl="([^"]+)"', self.definition_html(todo.pop())):
                if key not in seen:
                    seen.add(key)
                    todo.append(key)
        return sorted(seen)

    def page_data(self, ids: set[str]) -> dict[str, dict[str, Any]]:
        """What the popovers of a page show, for the terms it marks."""
        return {
            key: {"term": self.terms[key]["term"], "html": self.definition_html(key),
                  "pending": self.pending(key)}
            for key in self.closure(ids)
        }  # fmt: skip

    def entries(self) -> list[dict[str, Any]]:
        """The glossary page: every term, alphabetical, with its letter. Terms inside a
        definition link to their entry on the same page."""
        out = []
        for key, r in self.terms.items():
            term = r["term"]
            out.append({
                "id": key, "term": term, "pending": self.pending(key),
                "html": self.definition_html(key, page_url=""),
                "letter": sort_key(term)[:1].upper(),
                "search": " ".join([term, r[f"meaning_{self.lang}"], r[f"definition_{self.lang}"],
                                    *r["forms_exact"], *r["forms_any_case"]]).lower(),
            })  # fmt: skip
        return sorted(out, key=lambda e: sort_key(e["term"]))
