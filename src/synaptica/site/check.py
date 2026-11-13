"""Checks on the built site, run before publishing (plan, step 21): ``syn site --check``.

Copied and adapted from paleo-atlas ``src/paleo/site/check.py``. Kept from Paleo:

* every internal link, image, stylesheet and script points to an existing file;
* every page in ``es/`` or ``en/`` declares its counterpart in the other language (hreflang
  link, which the broken-link check then follows);
* no study page is an orphan: some other page links to it;
* every image in a figure has a credit with its licence;
* HTML tags are balanced.

New in SYNAPTICA:

* every page shows the medical notice, word for word, in its language (CLAUDE.md, «Contenido
  de salud»);
* every study card or page (``data-study``) shows its three signals (``data-signal``:
  review, subject, integrity), each with a text, even if it is «no data»;
* an image outside a figure names its credit (``data-credit`` = the id of an element of the
  same page) and that credit carries a licence. A licence still pending fails on purpose.

Paleo's search-index count is left out until the site has a search.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

VOID = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
    "source", "track", "wbr",
}  # fmt: skip
SIGNALS = ("review", "subject", "integrity")
# Folders of pages that must be reachable from another page (not only from search).
LINKED_FOLDERS = ("es/estudio", "en/study")
I18N_DIR = Path(__file__).parent / "i18n"


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.refs: list[str] = []
        self.anchors: list[str] = []  # <a href> links, not to the same page in the other language
        self.alternates: list[str] = []
        self.redirect = False  # <meta http-equiv="refresh">: a moved page or the root page
        self.stack: list[str] = []
        self.unbalanced: list[str] = []
        self.figures: list[tuple[bool, str]] = []  # (has an image, caption text)
        self._figure: list[Any] | None = None
        self._in_figcaption = False
        # Text of chosen elements, collected until the element closes.
        self._open: list[dict[str, Any]] = []
        self.disclaimers: list[str] = []
        self.texts_by_id: dict[str, str] = {}
        self.credited_images: list[tuple[str, str]] = []  # (src, data-credit)
        self.loose_images: list[str] = []  # outside a figure and without data-credit
        self.studies: list[tuple[str, dict[str, str]]] = []  # (study id, signal -> text)
        self._studies: list[dict[str, Any]] = []

    def _capture(self, kind: str, key: str = "") -> None:
        self._open.append({"depth": len(self.stack), "kind": kind, "key": key, "text": ""})

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: v or "" for k, v in attrs}
        for name in ("href", "src"):
            if a.get(name):
                self.refs.append(a[name])
        if tag == "a" and a.get("href") and not a.get("hreflang"):
            self.anchors.append(a["href"])
        if tag == "link" and a.get("rel") == "alternate" and a.get("href"):
            self.alternates.append(a["href"])
        if tag == "meta" and a.get("http-equiv", "").lower() == "refresh":
            self.redirect = True
        if tag == "figcaption":
            self._in_figcaption = True
        if tag == "figure":
            self._figure = [False, ""]
        if tag == "img" and a.get("src"):
            if self._figure is not None:
                self._figure[0] = True
            elif a.get("data-credit"):
                self.credited_images.append((a["src"], a["data-credit"]))
            else:
                self.loose_images.append(a["src"])
        if tag in VOID:
            return
        self.stack.append(tag)
        if "disclaimer" in a.get("class", "").split():
            self._capture("disclaimer")
        if a.get("id"):
            self._capture("id", a["id"])
        if "data-study" in a:
            self._studies.append({"depth": len(self.stack), "id": a["data-study"], "signals": {}})
        if a.get("data-signal"):
            self._capture("signal", a["data-signal"])

    def handle_endtag(self, tag: str) -> None:
        if tag == "figcaption":
            self._in_figcaption = False
        if tag == "figure" and self._figure is not None:
            self.figures.append((self._figure[0], self._figure[1]))
            self._figure = None
        if tag in VOID:
            return
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        else:
            self.unbalanced.append(tag)
            return
        depth = len(self.stack)
        while self._open and self._open[-1]["depth"] > depth:
            self._close(self._open.pop())
        while self._studies and self._studies[-1]["depth"] > depth:
            s = self._studies.pop()
            self.studies.append((s["id"], s["signals"]))

    def _close(self, cap: dict[str, Any]) -> None:
        text = " ".join(cap["text"].split())
        if cap["kind"] == "disclaimer":
            self.disclaimers.append(text)
        elif cap["kind"] == "id":
            self.texts_by_id[cap["key"]] = text
        elif cap["kind"] == "signal" and self._studies:
            self._studies[-1]["signals"][cap["key"]] = text

    def handle_data(self, data: str) -> None:
        if self._in_figcaption and self._figure is not None:
            self._figure[1] += data
        for cap in self._open:
            cap["text"] += data


@dataclass
class CheckReport:
    pages: int = 0
    problems: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.problems


def _target(ref: str, root: Path, page: Path) -> Path | None:
    """Local file a reference points to, or None for external links. The site uses only
    relative URLs, so it works under any base path (``/synaptica/`` on GitHub Pages)."""
    parsed = urlparse(ref)
    if parsed.scheme or ref.startswith(("mailto:", "#", "//")):
        return None
    if not parsed.path:
        return None
    if parsed.path.startswith("/"):
        return root / "__absolute_path__" / parsed.path.lstrip("/")  # always reported
    return (page.parent / parsed.path).resolve()


def _licensed(caption: str) -> bool:
    lower = caption.lower()
    return "CC" in caption or "OFL" in caption or "domain" in lower or "dominio" in lower


def _disclaimers() -> dict[str, str]:
    out = {}
    for lang in ("es", "en"):
        text = tomllib.loads((I18N_DIR / f"{lang}.toml").read_text("utf-8"))["disclaimer"]
        out[lang] = " ".join(text.split())
    return out


def check_site(root: Path) -> CheckReport:
    report = CheckReport()
    disclaimer = _disclaimers()
    linked: set[Path] = set()  # every local page some other page links to
    redirects: set[Path] = set()
    for page in sorted(root.rglob("*.html")):
        report.pages += 1
        rel = page.relative_to(root)
        parser = _PageParser()
        parser.feed(page.read_text(encoding="utf-8"))
        parser.close()
        for ref in parser.refs:
            target = _target(ref, root, page)
            if target is not None and not target.exists():
                report.problems.append(f"{rel}: broken link {ref}")
        for ref in parser.anchors:
            target = _target(ref, root, page)
            if target is not None and target.resolve() != page.resolve():
                linked.add(target.resolve())
        if parser.redirect:
            redirects.add(page.resolve())
        lang = rel.parts[0] if len(rel.parts) > 1 else ""
        if lang in ("es", "en"):
            if not parser.alternates:
                report.problems.append(f"{rel}: no hreflang alternate")
            if disclaimer[lang] not in parser.disclaimers:
                report.problems.append(f"{rel}: no medical notice")
        unlicensed = [cap for has_img, cap in parser.figures if has_img and not _licensed(cap)]
        if unlicensed:
            report.problems.append(
                f"{rel}: {len(unlicensed)} image(s) without a licence in the credit"
            )
        for src, credit in parser.credited_images:
            if not _licensed(parser.texts_by_id.get(credit, "")):
                report.problems.append(f"{rel}: image {src} without a licence in #{credit}")
        for src in parser.loose_images:
            report.problems.append(f"{rel}: image {src} without a credit")
        for study, signals in parser.studies:
            missing = [s for s in SIGNALS if not signals.get(s)]
            if missing:
                report.problems.append(f"{rel}: study {study} without {', '.join(missing)}")
        if parser.unbalanced or parser.stack:
            unclosed = ", ".join(parser.stack[-3:])
            report.problems.append(
                f"{rel}: unbalanced tags (stray {parser.unbalanced[:3]}, unclosed [{unclosed}])"
            )
    for folder in LINKED_FOLDERS:
        for page in sorted((root / folder).glob("*.html")):
            if page.resolve() not in linked | redirects:
                report.problems.append(f"{page.relative_to(root)}: no page links to it")
    if report.pages == 0:
        report.problems.append(f"{root}: no pages (was the site built?)")
    return report
