"""Neuro Glossary on the site: the glossary page and the popovers of the terms it marks.

Copied and adapted from the Phase 1 mock-up, ``spikes/web/glossary.py`` (v80), itself from
Paleo Atlas ``src/paleo/site/glossary.py`` (same author, AGPL). Changes:

* only the terms Sofía approved or corrected (``glossary.texts.published``); a term still
  in her queue is not on the site at all, not even as a gap;
* a term whose Spanish she corrected and whose English is still to be written shows the
  gap label on the English page (never one language filled in from the other);
* each entry cites its Wikipedia source (revision link, CC BY-SA 4.0) and says it was
  reviewed, with the date;
* forms come from ``glossary/terms.csv``: acronyms in their exact case, names in any case.

Inside a definition, the other published terms are marked (the first time each), as links
to their entry: that is the page's cross-linking. C2 (sheet row 36, v203): the same marking
on the summary of a study page and the excerpt of the featured study, with
:meth:`Glossary.mark_text`: only terms with a definition in that language, the first time
each per page, and the text itself never changes (stripped of the links it is the stored
text, escaped: checked on every call).
"""

from __future__ import annotations

import html
import re
import unicodedata
from typing import Any

from synaptica.glossary import form_pattern
from synaptica.glossary.texts import Entry


def sort_key(text: str) -> str:
    return unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode().lower()


class Glossary:
    """The published glossary in one language."""

    def __init__(self, entries: list[Entry], lang: str) -> None:
        self.lang = lang
        self.entries = {e.term.term_id: e for e in entries}
        self._exact: dict[str, str] = {}
        self._any: dict[str, str] = {}
        for e in entries:
            for form in e.term.forms_exact:
                self._exact.setdefault(html.escape(form, quote=False), e.term.term_id)
            for form in e.term.forms_any_case:
                self._any.setdefault(html.escape(form, quote=False).lower(), e.term.term_id)
        # Matched on escaped HTML text, so the forms are escaped too (Alzheimer's -> &#x27;).
        self._pattern = (form_pattern(tuple(self._exact), tuple(self._any))
                         if entries else None)  # fmt: skip

    def __bool__(self) -> bool:
        return bool(self.entries)

    def key_of(self, written: str) -> str | None:
        return self._exact.get(written) or self._any.get(written.lower())

    def mark(self, escaped: str, used: set[str], skip: str | None = None,
             page_url: str = "") -> str:  # fmt: skip
        """Mark in escaped text the first appearance of each term not in ``used`` (which
        is updated), except ``skip``: a definition never marks its own term."""
        if self._pattern is None:
            return escaped

        def repl(m: re.Match[str]) -> str:
            key = self.key_of(m.group(0))
            if key is None or key in used or key == skip:
                return m.group(0)
            used.add(key)
            return f'<a class="gl" href="{page_url}#{key}" data-gl="{key}">{m.group(0)}</a>'

        return self._pattern.sub(repl, escaped)

    def mark_text(self, text: str, used: set[str], page_url: str,
                  context: str | None = None) -> str:  # fmt: skip
        """Escape ``text`` and mark the first appearance on the page (``used``, updated) of
        each term with a definition in this language. An acronym of two letters or fewer
        (AD, DA) only counts when one of its full names is also in ``context`` (the whole
        summary; ``text`` by default): exact case already keeps the Spanish «da» out, but
        not every «AD» is Alzheimer's."""
        escaped = html.escape(text, quote=False)
        if self._pattern is None:
            return escaped
        ctx = html.escape(context if context is not None else text, quote=False).lower()

        def repl(m: re.Match[str]) -> str:
            written = m.group(0)
            key = self.key_of(written)
            if key is None or key in used or self.pending(key):
                return written
            term = self.entries[key].term
            short = len(written) <= 2 and written in self._exact
            names = (html.escape(f, quote=False).lower() for f in term.forms_any_case)
            if short and not any(n in ctx for n in names):
                return written
            used.add(key)
            meaning = html.escape(self.meaning(key) or term.term)
            return (f'<a class="gl" href="{page_url}#{key}" data-gl="{key}" '
                    f'title="{meaning}">{written}</a>')  # fmt: skip

        out = self._pattern.sub(repl, escaped)
        if re.sub(r"<[^>]+>", "", out) != escaped:  # the stored text, never changed
            raise RuntimeError(f"glossary marking changed a text: {text[:60]!r}")
        return out

    def pending(self, term_id: str) -> bool:
        return self.entries[term_id].definition[self.lang] is None

    def meaning(self, term_id: str) -> str | None:
        return self.entries[term_id].meaning[self.lang]

    def definition_html(self, term_id: str, page_url: str = "") -> str:
        """The definition, escaped, with the other terms it uses marked; empty when it
        does not exist in this language yet."""
        if self.pending(term_id):
            return ""
        text = html.escape(self.entries[term_id].definition[self.lang] or "", quote=False)
        return self.mark(text, set(), skip=term_id, page_url=page_url)

    def page_data(self) -> dict[str, dict[str, Any]]:
        """What the popovers of the glossary page show (every published term)."""
        return {
            key: {"term": e.term.term, "meaning": self.meaning(key),
                  "html": self.definition_html(key), "pending": self.pending(key)}
            for key, e in self.entries.items()
        }  # fmt: skip

    def page_entries(self) -> list[dict[str, Any]]:
        """Every published term, alphabetical, with its letter, sources and review."""
        out = []
        for key, e in self.entries.items():
            words = [e.term.term, self.meaning(key) or "", e.definition[self.lang] or "",
                     *e.term.forms_exact, *e.term.forms_any_case]  # fmt: skip
            out.append({
                "id": key, "term": e.term.term, "meaning": self.meaning(key),
                "pending": self.pending(key), "html": self.definition_html(key),
                "letter": sort_key(e.term.term)[:1].upper(),
                "search": " ".join(words).lower(),
                "sources": [{"lang": s.id.split("-")[1], "title": _title(s.label), "url": s.url}
                            for s in e.sources],
                "reviewed_at": e.reviewed_at, "mark": e.mark,
            })  # fmt: skip
        return sorted(out, key=lambda x: sort_key(x["term"]))


def _title(label: str) -> str:
    """The article title in a source label («Wikipedia en inglés: «Serotonin» (revisión N)»)."""
    m = re.search(r"«(.+)»", label)
    return m.group(1) if m else label
