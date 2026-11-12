"""Second round of web mock-ups (SCOPE v77): Aday chose the mixed option, a hub as the home
page with today's news in the first screen and Neuro News on its own page, and asked for
several styles of it. One set of templates (``v2/templates``), three stylesheets:

- G «Gaceta»: mock-up A tidied up (light, Newsreader, Prussian blue), Cajal printed as ink.
- N «Noche»: dark by default (light on request), Atkinson Hyperlegible, Cajal as light lines.
- L «Lámina»: an atlas plate: tinted tiles, system fonts, the calm palette of the S3 viewer.

Same data, strings and rules as round one (``build.py``); images from ``images.py``.

    uv run python spikes/web/build2.py
"""

from __future__ import annotations

import functools
import json
import re
import shutil
from pathlib import Path
from typing import Any

from build import LANGS, TYPES, T, fmt_date, licence_lines, short_journal, signals, slug
from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

HERE = Path(__file__).parent
V2 = HERE / "v2"
STYLES = {"g": "Gaceta", "n": "Noche", "l": "Lámina"}
FACT = {"g": "a", "n": "b", "l": "c"}  # each style carries one proposal for step 26
ROUTES = {
    "es": {"index": "index.html", "news": "noticias.html", "study": "estudio/{}.html",
           "method": "como-evaluamos.html", "week": "semana.html"},
    "en": {"index": "index.html", "news": "news.html", "study": "study/{}.html",
           "method": "how-we-evaluate.html", "week": "week.html"},
}  # fmt: skip
ATLAS_URL = "https://adaycuestacorrea.github.io/synaptica/spikes/s3/c/"
FONTS = {
    "es": {"g": "Newsreader (Production Type, SIL OFL 1.1) y la sans del sistema",
           "n": "Atkinson Hyperlegible (Braille Institute, SIL OFL 1.1)",
           "l": "las del sistema"},
    "en": {"g": "Newsreader (Production Type, SIL OFL 1.1) and the system sans",
           "n": "Atkinson Hyperlegible (Braille Institute, SIL OFL 1.1)",
           "l": "the system's own"},
}  # fmt: skip

# Strings new in round two; the rest come from build.T.
T2: dict[str, dict[str, str]] = {
    "es": {
        "home": "Inicio",
        "hero_text": "Estudios nuevos cada día, con sus señales a la vista y resúmenes "
                     "comprobados frase a frase.",
        "today": "Hoy", "all_news": "Todas las noticias de hoy", "explore": "Explora",
        "sec_news": "Última hora, Nature · Science · Cell, Clásicos y lo que cuentan los "
                    "medios.",
        "sec_news_n": "{latest} estudios en Última hora · {nsc} de Nature · Science · Cell · "
                      "{media} en los medios",
        "sec_week": "La semana en un vistazo.",
        "sec_atlas": "El cerebro de la rata y el del humano en 3D, lado a lado. Hoy es un "
                     "prototipo; llega en la Fase 2.",
        "atlas_tag": "Avance", "atlas_cta": "Abrir el prototipo",
        "sec_method": "Qué significa cada señal y cómo se comprueba cada resumen.",
        "coming": "Más adelante",
        "fig": "Imagen del estudio",
        "fig_credit": "{label} del artículo · {lic} · vía PMC",
        "cajal_credit": "Dibujo de Santiago Ramón y Cajal · {lic}",
        "atlas_credit": "Captura de nuestro visor · {atlas} · {lic}",
        "gaps_title": "Huecos y propuestas de esta maqueta",
        "gaps_intro": "Lo que aún falta o está por decidir. En la página se marca con una "
                      "etiqueta que enlaza aquí.",
        "more_n": "Ver más", "tabs": "Bloques de Neuro News",
        "gap_figs": "Imágenes de las noticias: la figura 1 (o el resumen gráfico) de los "
                    "artículos de acceso abierto de PMC con licencia CC, redimensionada y sin "
                    "recortar. Muchas son gráficas: está por decidir si se elige otra o la "
                    "elige Sofía. Nature, Science y Cell y los medios van sin imagen.",
        "lic_image": "Imagen: {label} del artículo, {lic}, vía PMC (NLM); redimensionada, sin "
                     "recortes.",
        "footer_images": "Imágenes: dibujos de Santiago Ramón y Cajal (dominio público, vía "
                         "Wikimedia Commons); figuras de estudios de acceso abierto de PMC, "
                         "cada una con su licencia; capturas de nuestro visor, una por atlas: "
                         "Waxholm (CC BY 4.0) y Julich-Brain (CC BY-NC-SA 4.0).",
        "theme_dark_default": "Oscuro (por defecto)",
        "mock2": "Maqueta 2 · {x} · datos reales del 12 nov 2026",
        "see_gaps": "ver huecos",
    },
    "en": {
        "home": "Home",
        "hero_text": "New studies every day, with their signals in plain sight and summaries "
                     "checked sentence by sentence.",
        "today": "Today", "all_news": "All of today's news", "explore": "Explore",
        "sec_news": "Latest, Nature · Science · Cell, Classics and what the media say.",
        "sec_news_n": "{latest} studies in Latest · {nsc} from Nature · Science · Cell · "
                      "{media} in the media",
        "sec_week": "The week at a glance.",
        "sec_atlas": "The rat brain and the human brain in 3D, side by side. A prototype "
                     "for now; it arrives in Phase 2.",
        "atlas_tag": "Preview", "atlas_cta": "Open the prototype",
        "sec_method": "What each signal means and how every summary is checked.",
        "coming": "Coming later",
        "fig": "Image from the study",
        "fig_credit": "{label} of the article · {lic} · via PMC",
        "cajal_credit": "Drawing by Santiago Ramón y Cajal · {lic}",
        "atlas_credit": "Capture of our viewer · {atlas} · {lic}",
        "gaps_title": "Gaps and proposals in this mock-up",
        "gaps_intro": "What is still missing or undecided. On the page it carries a tag that "
                      "links here.",
        "more_n": "Show more", "tabs": "Neuro News blocks",
        "gap_figs": "News images: figure 1 (or the graphical abstract) of PMC open-access "
                    "articles with a CC licence, resized and never cropped. Many are charts: "
                    "whether to pick another one, or let Sofía pick, is undecided. Nature, "
                    "Science, Cell and the media have no image.",
        "lic_image": "Image: {label} of the article, {lic}, via PMC (NLM); resized, not "
                     "cropped.",
        "footer_images": "Images: drawings by Santiago Ramón y Cajal (public domain, via "
                         "Wikimedia Commons); figures from PMC open-access studies, each with "
                         "its licence; captures of our viewer, one per atlas: Waxholm (CC BY "
                         "4.0) and Julich-Brain (CC BY-NC-SA 4.0).",
        "theme_dark_default": "Dark (default)",
        "mock2": "Mock-up 2 · {x} · real data from 12 Nov 2026",
        "see_gaps": "see gaps",
    },
}  # fmt: skip
COMING = ["Neuro Lab", "Neuro Glossary", "Neuro Learn", "Neuro Diseases", "Neuro History",
          "Neuro Experiments"]  # fmt: skip


LIC_NAMES = {"es": {"Public domain": "dominio público"}, "en": {}}


def figure_label(label: str | None, lang: str) -> str | None:
    """«Figure 1.», «Fig. 1», «FIGURE 2» → «Figura 1» / «Figure 1»; anything else as is."""
    if not label:
        return None
    if found := re.fullmatch(r"(?i)fig(?:ure|\.)?\s*(\w+)\.?", label.strip()):
        return ("Figura " if lang == "es" else "Figure ") + found.group(1)
    if label == "graphical abstract":
        return "Resumen gráfico" if lang == "es" else "Graphical abstract"
    return label


def gaps(lang: str, x: str) -> dict[str, tuple[str, str]]:
    """Every gap and proposal of the mock-up: key → (kind, text)."""
    t, t2 = T[lang], T2[lang]
    out = {
        "types": ("gap", t["gap_types"]),
        "groups": ("gap", t["gap_groups"]),
        "s5": ("gap", t["s5_note"]),
        "week": ("gap", t["week_gap"]),
        "figs": ("proposal", t2["gap_figs"]),
        "fact": ("proposal", t[f"fact_{FACT[x]}_note"]),
        "journal": ("gap", t["provisional_long"]),
    }
    if lang == "es":
        out["title_es"] = ("gap", "Títulos: " + t["gap_title_es"] + ".")
    if FACT[x] == "c" and lang == "es":
        out["fact_desc"] = ("gap", "Efeméride: " + t["fact_c_gap"] + ".")
    if FACT[x] == "b":
        out["fact_noise"] = ("gap", t["fact_b_caveat"])
    return out


def render(env: Environment, x: str, lang: str, template: str, kind: str, arg: str | None,
           **ctx: Any) -> None:  # fmt: skip
    other = "en" if lang == "es" else "es"
    rel = ROUTES[lang][kind].format(arg) if arg else ROUTES[lang][kind]
    other_rel = ROUTES[other][kind].format(arg) if arg else ROUTES[other][kind]
    up = "../" * rel.count("/")

    def url(k: str, a: str | None = None) -> str:
        return up + (ROUTES[lang][k].format(a) if a else ROUTES[lang][k])

    html = env.get_template(template).render(
        lang=lang, t=T[lang] | T2[lang], x=x, style=STYLES[x], up=up, root=up + "../",
        fonts_root=up + "../../../", img=up + "../../img/", other_lang=other,
        other_url=up + "../" + other + "/" + other_rel, url=url, slug=slug, page_kind=kind,
        date=lambda v, long=False: fmt_date(v, lang, long), sj=short_journal,
        signals=functools.partial(signals, lang=lang),
        licence=functools.partial(licence_lines, lang=lang), types=TYPES,
        fonts=FONTS[lang][x], gaps=gaps(lang, x), fact_kind=FACT[x], atlas_url=ATLAS_URL,
        coming=COMING, lic_name=lambda v: LIC_NAMES[lang].get(v, v),
        figure_label=functools.partial(figure_label, lang=lang), **ctx,
    )  # fmt: skip
    path = V2 / x / lang / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


def main() -> None:
    data = json.loads((HERE / "data/mockup.json").read_text(encoding="utf-8"))
    images = json.loads((HERE / "data/images.json").read_text(encoding="utf-8"))
    studies = {s["study_id"]: s for s in data["latest"] + data["s5"] + data["nsc"]}
    studies |= {s["study_id"]: s for s in data["examples"].values()}
    latest = sorted(data["latest"] + data["s5"],
                    key=lambda s: (s["entered_on"] or "", s["published_on"] or ""),
                    reverse=True)  # fmt: skip
    lead = next(s for s in data["s5"] if s["summary"]["en"]["kind"] == "verified"
                and s["species"] != "unknown" and s["study_id"] in images["figures"])  # fmt: skip
    common = {
        "data": data, "by_id": studies, "latest": latest, "lead": lead,
        "today": [s for s in latest if s["study_id"] != lead["study_id"]][:4],
        "type_counts": {k: sum(s["type"] == k for s in latest) for k in TYPES},
        "figs": images["figures"], "cajal": images["cajal"], "atlas": images["atlas"],
    }  # fmt: skip
    for x in STYLES:
        out = V2 / x
        for lang in LANGS:
            shutil.rmtree(out / lang, ignore_errors=True)
        (out / "static").mkdir(parents=True, exist_ok=True)
        css = (V2 / "styles" / f"{x}.css").read_text() + (V2 / "styles/base.css").read_text()
        (out / "static" / f"{x}.css").write_text(css, encoding="utf-8")
        shutil.copy(V2 / "styles" / "site.js", out / "static" / "site.js")
        shutil.copy(HERE / "a/static/favicon.svg", out / "static" / "favicon.svg")
        env = Environment(
            loader=FileSystemLoader([V2 / "templates", HERE / "shared"]),
            autoescape=select_autoescape(["html", "j2"]),
            undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True,
        )  # fmt: skip
        for lang in LANGS:
            for kind in ("index", "news", "method", "week"):
                render(env, x, lang, f"{kind}.html.j2", kind, None, **common)
            for sid, s in studies.items():
                render(env, x, lang, "study.html.j2", "study", slug(sid), s=s, **common)
        print(f"{x}: {sum(1 for _ in out.rglob('*.html'))} pages")


if __name__ == "__main__":
    main()
