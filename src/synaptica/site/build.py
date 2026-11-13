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

import csv
import hashlib
import json
import posixpath
import shutil
import tomllib
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from synaptica import report
from synaptica.config import project_root
from synaptica.site import news as news_mod

LANGS = ("es", "en")
HERE = Path(__file__).parent
I18N_DIR = HERE / "i18n"
SITE_DIR = project_root() / "site"
SEEDS_DIR = project_root() / "dbt" / "seeds"
MARKER = ".synaptica-site"  # marks a folder this module may wipe and rebuild

PATHS = {
    "es": {
        "home": "es/index.html", "news": "es/noticias.html", "study": "es/estudio/{key}.html",
        "week": "es/semana.html", "method": "es/como-evaluamos.html",
        "sources": "es/fuentes.html", "status": "es/estado.html",
        "about": "es/sobre-nosotros.html", "glossary": "es/glosario.html",
        "search": "es/buscar.html", "search_index": "es/buscar.json",
    },
    "en": {
        "home": "en/index.html", "news": "en/news.html", "study": "en/study/{key}.html",
        "week": "en/week.html", "method": "en/how-we-evaluate.html",
        "sources": "en/sources.html", "status": "en/status.html", "about": "en/about.html",
        "glossary": "en/glossary.html", "search": "en/search.html",
        "search_index": "en/search.json",
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
SCRIPTS = ("site.js", "search.js")
# Pages built so far (steps 21 to 23); one study page per study shown comes on top.
KINDS = ("home", "news", "week", "method", "sources", "status", "about", "search")
RECENT_RUNS = 14  # rows of the run table on «Estado de los datos»


def load_i18n() -> dict[str, dict[str, str]]:
    return {lang: tomllib.loads((I18N_DIR / f"{lang}.toml").read_text("utf-8")) for lang in LANGS}


def load_images() -> dict[str, dict[str, Any]]:
    return tomllib.loads((HERE / "images.toml").read_text("utf-8"))


def load_seed(name: str, seeds_dir: Path = SEEDS_DIR) -> list[dict[str, str]]:
    """Rows of a dbt seed, read directly: the fixed pages do not need the warehouse."""
    with (seeds_dir / f"{name}.csv").open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def recent_runs(data_dir: Path | None, limit: int = RECENT_RUNS) -> list[dict[str, Any]]:
    """The last runs of the run log, newest first; none without a data folder."""
    if data_dir is None or not report.runs_dir(data_dir).exists():
        return []
    return list(reversed(report.all_runs(data_dir)))[:limit]


def other(lang: str) -> str:
    return "en" if lang == "es" else "es"


class SiteBuilder:
    """Renders the pages of ``kinds`` in both languages into ``out``."""

    def __init__(
        self,
        out: Path,
        *,
        kinds: Iterable[str] = KINDS,
        data_dir: Path | None = None,
        seeds_dir: Path = SEEDS_DIR,
        i18n: dict[str, dict[str, str]] | None = None,
        images: dict[str, dict[str, Any]] | None = None,
        site_dir: Path = SITE_DIR,
    ) -> None:
        self.out = out
        self.kinds = tuple(kinds)
        self.i18n = i18n or load_i18n()
        self.images = images or load_images()
        self.site_dir = site_dir
        self.data_dir = data_dir
        self.seeds_dir = seeds_dir
        self.env = Environment(
            loader=FileSystemLoader(site_dir / "templates"),
            autoescape=select_autoescape(["html", "j2"]),
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.asset_v = ""
        self.written: list[Path] = []
        self.news_data: news_mod.NewsData | None = None
        if data_dir is not None and {"home", "news", "week", "method"} & set(self.kinds):
            self.news_data = news_mod.load(data_dir / "warehouse.duckdb", data_dir / "derived")

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
        search = None
        if "search" in self.kinds:
            search = {"action": url("search"), "index": url("search_index"),
                      "base": posixpath.relpath(".", here) + "/"}  # fmt: skip
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
            gaps=gaps, search=search, news=self.news_data,
            date=lambda v, long=False: news_mod.fmt_date(v, lang, long),
            sj=news_mod.short_journal, signals=lambda s: news_mod.signals(s, t),
            licence=lambda s: news_mod.licence_lines(s, lang, t), types=news_mod.TYPES,
            page_size=news_mod.PAGE, **ctx,
        )  # fmt: skip
        path = self.out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(page, encoding="utf-8")
        self.written.append(path)
        return path

    # -- gaps shared by the pages that show studies ------------------------------------------

    def study_gaps(self, lang: str, studies: Iterable[dict[str, Any]]) -> dict[str, Any]:
        """The gaps a list of studies needs: the Spanish title (the LLM does not translate
        yet), the provisional name of the «journal» signal and the missing types."""
        t, studies = self.i18n[lang], list(studies)
        gaps: dict[str, tuple[str, str]] = {}
        if self.news_data is None:
            gaps["no_data"] = ("gap", t["gap_no_data"])
        if lang == "es" and studies:
            gaps["title_es"] = ("gap", t["gap_title_es"])
        if any(s["review_status"] == "journal" for s in studies):
            gaps["journal_name"] = ("gap", t["gap_journal_name"])
        if any(s["type"] is None for s in studies):
            gaps["types"] = ("gap", t["gap_types"])
        return gaps

    def home(self, lang: str) -> None:
        gaps = {}
        if not self.images["hero"]["licence"]:
            gaps["hero_licence"] = ("gap", self.i18n[lang]["gap_hero_licence"])
        n = self.news_data
        shown = ([n.lead] if n and n.lead else []) + (n.headlines if n else [])
        gaps |= self.study_gaps(lang, shown)
        self.render(lang, "home", "home.html.j2", gaps=gaps,
                    lead=n.lead if n else None, headlines=n.headlines if n else [])  # fmt: skip

    def news(self, lang: str) -> None:
        n, t = self.news_data, self.i18n[lang]
        gaps = self.study_gaps(lang, [*n.latest, *n.nsc] if n else [])
        if n and n.stories and all(len(story) == 1 for story in n.stories):
            gaps["groups"] = ("gap", t["gap_groups"])
        counts = {k: sum(s["type"] == k for s in n.latest) if n else 0 for k in news_mod.TYPES}
        self.render(lang, "news", "news.html.j2", gaps=gaps, type_counts=counts)

    def week(self, lang: str) -> None:
        n, t = self.news_data, self.i18n[lang]
        gaps = self.study_gaps(lang, n.week_studies if n else [])
        if n is None or n.week_text[lang]["kind"] != "verified":
            gaps["week"] = ("gap", t["gap_week"])
        self.render(lang, "week", "week.html.j2", gaps=gaps)

    def study(self, lang: str, s: dict[str, Any]) -> None:
        gaps = self.study_gaps(lang, [s])
        self.render(lang, "study", "study.html.j2", key=s["slug"], s=s, gaps=gaps)

    def method(self, lang: str) -> None:
        t = self.i18n[lang]
        gaps = {k: ("gap", t[f"gap_{k}"]) for k in ("method_review", "journal_name",
                                                     "retraction_watch")}  # fmt: skip
        found = self.news_data.examples if self.news_data else {}
        examples = [(k, found.get(k)) for k in news_mod.EXAMPLE_STATES]
        gaps |= {k: v for k, v in self.study_gaps(lang, [e for _, e in examples if e]).items()
                 if k != "journal_name"}  # fmt: skip
        for k, e in examples:
            if e is None:
                gaps[f"example_{k}"] = ("gap", t[f"gap_example_{k}"])
        self.render(lang, "method", "method.html.j2", gaps=gaps, examples=examples)

    def search(self, lang: str) -> None:
        self.render(lang, "search", "search.html.j2")

    def search_index(self, lang: str) -> None:
        """``[kind, text, extra words, url]`` per entry, for search.js (from the mock-up's
        ``search_index`` in ``spikes/web/build3.py``, without topics or glossary: those
        come in Phase 2). Local URLs are relative to the site root."""
        t = self.i18n[lang]
        out = [[t["kind_page"], t[k], "", self.path(lang, k)]
               for k in ("news", "week", "method", "sources", "status", "about")
               if k in self.kinds]  # fmt: skip
        out += [[t["kind_section"], sec["name"], t["sec_" + sec["key"]],
                 ATLAS_URL if sec["key"] == "atlas" else ""] for sec in SECTIONS]  # fmt: skip
        if self.news_data:
            out += [[t["kind_study"], s["title"],
                     " ".join(filter(None, [s["journal"], s["type"] and t["type_" + s["type"]]])),
                     self.path(lang, "study", s["slug"])]
                    for s in self.news_data.by_id.values()]  # fmt: skip
            out += [[t["kind_news"], i["title"], i["outlet"], i["url"]]
                    for story in self.news_data.stories for i in story]  # fmt: skip
        path = self.out / self.path(lang, "search_index")
        path.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), "utf-8")

    def sources(self, lang: str) -> None:
        self.render(lang, "sources", "sources.html.j2",
                    sources=load_seed("sources", self.seeds_dir),
                    journals=load_seed("journals", self.seeds_dir))  # fmt: skip

    def status(self, lang: str) -> None:
        self.render(lang, "status", "status.html.j2", runs=recent_runs(self.data_dir))

    def about(self, lang: str) -> None:
        t = self.i18n[lang]
        gaps = {k: ("gap", t[f"gap_{k}"]) for k in ("about_intro", "contact")}
        self.render(lang, "about", "about.html.j2", gaps=gaps)

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
            if self.news_data and "news" in self.kinds:
                for s in self.news_data.by_id.values():
                    self.study(lang, s)
            if "search" in self.kinds:
                self.search_index(lang)
        self.root()
        return {"pages": len(self.written), "kinds": list(self.kinds), "out": str(self.out)}


def build_site(out: Path, data_dir: Path | None = None) -> dict[str, Any]:
    return SiteBuilder(out, data_dir=data_dir).build()
