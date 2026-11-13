"""The static website, in Spanish and English (plan, step 21): ``syn site``.

Structure adapted from paleo-atlas ``src/paleo/site/build.py`` (a table of paths per language,
interface strings in ``i18n/{es,en}.toml``, Jinja2 templates in ``site/templates/`` and files
in ``site/static/``); design, templates and styles from the «Noche» mock-up
(``spikes/web/build3.py``, SCOPE v79 to v97), rewritten for the package.

Every URL is relative, so the same build works at the root of a domain or under
``/synaptica/`` on GitHub Pages, and nothing is loaded from another domain. The pages of later
steps (Neuro News, the fixed pages…) have their paths here already; the navigation and the
footer only link to the pages that were built, so ``syn site --check`` never meets a link to a
page that does not exist yet.
"""

from __future__ import annotations

import hashlib
import posixpath
import shutil
import tomllib
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from synaptica.config import project_root

LANGS = ("es", "en")
HERE = Path(__file__).parent
I18N_DIR = HERE / "i18n"
SITE_DIR = project_root() / "site"
MARKER = ".synaptica-site"  # marks a folder this module may wipe and rebuild

PATHS = {
    "es": {
        "home": "es/index.html", "news": "es/noticias.html", "study": "es/estudio/{key}.html",
        "week": "es/semana.html", "method": "es/como-evaluamos.html",
        "sources": "es/fuentes.html", "status": "es/estado.html",
        "about": "es/sobre-nosotros.html", "glossary": "es/glosario.html",
    },
    "en": {
        "home": "en/index.html", "news": "en/news.html", "study": "en/study/{key}.html",
        "week": "en/week.html", "method": "en/how-we-evaluate.html",
        "sources": "en/sources.html", "status": "en/status.html", "about": "en/about.html",
        "glossary": "en/glossary.html",
    },
}  # fmt: skip
NAV = ("home", "news", "method", "glossary", "about")  # header, in this order, when built
FOOTER_LINKS = ("method", "sources", "status", "about")

# Sofía's six sections, in her order; the phase each arrives in comes from SCOPE §4.
SECTIONS = [
    {"key": "atlas", "name": "Neuro Atlas", "phase": 2},
    {"key": "lab", "name": "Neuro Lab", "phase": 2},
    {"key": "learn", "name": "Neuro Learn", "phase": 3},
    {"key": "diseases", "name": "Neuro Diseases", "phase": 3},
    {"key": "history", "name": "Neuro History", "phase": 4},
    {"key": "experiments", "name": "Neuro Experiments", "phase": 4},
]
# Until Phase 2, the Neuro Atlas card opens the S3 prototype (ADR 0003, correction of v98).
ATLAS_URL = "https://adaycuestacorrea.github.io/synaptica/spikes/s3/c/"
STYLESHEETS = ("noche.css", "base.css")  # joined, in this order, into static/synaptica.css
SCRIPTS = ("site.js",)


def load_i18n() -> dict[str, dict[str, str]]:
    return {lang: tomllib.loads((I18N_DIR / f"{lang}.toml").read_text("utf-8")) for lang in LANGS}


def load_images() -> dict[str, dict[str, Any]]:
    return tomllib.loads((HERE / "images.toml").read_text("utf-8"))


def other(lang: str) -> str:
    return "en" if lang == "es" else "es"


class SiteBuilder:
    """Renders the pages of ``kinds`` in both languages into ``out``."""

    def __init__(
        self,
        out: Path,
        *,
        kinds: Iterable[str] = ("home",),
        i18n: dict[str, dict[str, str]] | None = None,
        images: dict[str, dict[str, Any]] | None = None,
        site_dir: Path = SITE_DIR,
    ) -> None:
        self.out = out
        self.kinds = tuple(kinds)
        self.i18n = i18n or load_i18n()
        self.images = images or load_images()
        self.site_dir = site_dir
        self.env = Environment(
            loader=FileSystemLoader(site_dir / "templates"),
            autoescape=select_autoescape(["html", "j2"]),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.asset_v = ""
        self.written: list[Path] = []

    # -- files ---------------------------------------------------------------------------

    def _clean(self) -> None:
        """Start from an empty folder, but never wipe one this module did not create."""
        if self.out.exists():
            if not (self.out / MARKER).exists() and any(self.out.iterdir()):
                raise RuntimeError(f"{self.out} is not empty and was not built by `syn site`")
            shutil.rmtree(self.out)
        self.out.mkdir(parents=True)
        (self.out / MARKER).write_text("Built by `syn site`; rebuilt from scratch each time.\n")

    def _static(self) -> None:
        src, dst = self.site_dir / "static", self.out / "static"
        dst.mkdir()
        css = "".join((src / name).read_text("utf-8") for name in STYLESHEETS)
        (dst / "synaptica.css").write_text(css, encoding="utf-8")
        for name in (*SCRIPTS, "favicon.svg"):
            shutil.copy(src / name, dst / name)
        for folder in ("fonts", "img"):
            shutil.copytree(src / folder, dst / folder)
        # A fingerprint of CSS and JS in their URLs: a browser never keeps an old copy.
        digest = hashlib.sha256()
        for name in ("synaptica.css", *SCRIPTS):
            digest.update((dst / name).read_bytes())
        self.asset_v = digest.hexdigest()[:10]

    # -- pages ---------------------------------------------------------------------------

    def path(self, lang: str, kind: str, key: str | None = None) -> str:
        p = PATHS[lang][kind]
        return p.format(key=key) if key is not None else p

    def render(self, lang: str, kind: str, template: str, key: str | None = None,
               **ctx: Any) -> Path:  # fmt: skip
        rel = self.path(lang, kind, key)
        here = posixpath.dirname(rel)

        def url(k: str, a: str | None = None) -> str:
            return posixpath.relpath(self.path(lang, k, a), here)

        def static(name: str) -> str:
            return posixpath.relpath(f"static/{name}", here)

        t = self.i18n[lang]
        nav = [(k, t[k], url(k)) for k in NAV if k in self.kinds]
        footer_links = [(t[k], url(k)) for k in FOOTER_LINKS if k in self.kinds]
        hero = self.images["hero"]
        gaps: dict[str, tuple[str, str]] = ctx.pop("gaps", {})
        page = self.env.get_template(template).render(
            lang=lang, t=t, page_kind=kind, url=url, static=static, asset_v=self.asset_v,
            other_lang=other(lang),
            other_url=posixpath.relpath(self.path(other(lang), kind, key), here),
            nav=nav, footer_links=footer_links, sections=SECTIONS, atlas_url=ATLAS_URL,
            hero_licence=hero["licence"] or t["licence_pending"], hero_author=hero["author"],
            gaps=gaps, **ctx,
        )  # fmt: skip
        path = self.out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(page, encoding="utf-8")
        self.written.append(path)
        return path

    def home(self, lang: str) -> None:
        gaps = {}
        if not self.images["hero"]["licence"]:
            gaps["hero_licence"] = ("gap", self.i18n[lang]["gap_hero_licence"])
        self.render(lang, "home", "home.html.j2", gaps=gaps)

    def root(self) -> None:
        """``index.html`` at the root: sends to the Spanish home page, links to both."""
        page = self.env.get_template("root.html.j2").render(
            t=self.i18n, homes={lang: self.path(lang, "home") for lang in LANGS},
            static=lambda name: f"static/{name}", asset_v=self.asset_v,
        )  # fmt: skip
        (self.out / "index.html").write_text(page, encoding="utf-8")
        self.written.append(self.out / "index.html")

    def build(self) -> dict[str, Any]:
        self._clean()
        self._static()
        for lang in LANGS:
            for kind in self.kinds:
                getattr(self, kind)(lang)
        self.root()
        return {"pages": len(self.written), "kinds": list(self.kinds), "out": str(self.out)}


def build_site(out: Path) -> dict[str, Any]:
    return SiteBuilder(out).build()
