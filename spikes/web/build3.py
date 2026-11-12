"""Third round of web mock-ups (SCOPE v78): Sofía's sketch of the home page, one continuous
scroll: header with search, «your neuroscience hub» hero, six section cards, «Today» (lead,
three headlines, fact of the day) and topics carousel; the glossary has its own page, and its
terms are marked in the summaries and titles (``glossary.py``, from Paleo Atlas). No Cajal
drawings (Sofía did not like them): our own line illustrations and the captures of our S3 viewer.

Style: N «Noche» (dark by default), chosen by Aday and Sofía in v79. Same data and rules as
before (``build.py``, ``build2.py``).

    uv run python spikes/web/build3.py
"""

from __future__ import annotations

import functools
import html
import json
import re
import shutil
from pathlib import Path
from typing import Any

from build import LANGS, TYPES, T, fmt_date, licence_lines, short_journal, signals, slug
from build2 import ATLAS_URL, FACT, FONTS, LIC_NAMES, STYLES, T2, figure_label, gaps
from glossary import Glossary, load_rows
from markupsafe import Markup

HERE = Path(__file__).parent
V3 = HERE / "v3"
ROUTES = {
    "es": {"index": "index.html", "news": "noticias.html", "study": "estudio/{}.html",
           "method": "como-evaluamos.html", "week": "semana.html",
           "about": "sobre-nosotros.html", "search": "buscar.html", "topic": "temas/{}.html",
           "glossary": "glosario.html", "search_index": "buscar.json"},
    "en": {"index": "index.html", "news": "news.html", "study": "study/{}.html",
           "method": "how-we-evaluate.html", "week": "week.html", "about": "about.html",
           "search": "search.html", "topic": "topics/{}.html", "glossary": "glossary.html",
           "search_index": "search.json"},
}  # fmt: skip

# Sofía's six sections, in her order; the phase each arrives in comes from SCOPE §4.
SECTIONS = [
    {"key": "atlas", "name": "Neuro Atlas", "phase": 2, "art": "atlas",
     "es": "Explora el cerebro", "en": "Explore the brain"},
    {"key": "lab", "name": "Neuro Lab", "phase": 2, "art": "lab",
     "es": "Explora el laboratorio", "en": "Explore the lab"},
    {"key": "learn", "name": "Neuro Learn", "phase": 3, "art": "learn",
     "es": "Aprende sobre neurociencia", "en": "Learn about neuroscience"},
    {"key": "diseases", "name": "Neuro Diseases", "phase": 3, "art": "diseases",
     "es": "Enfermedades neurológicas y sus estudios",
     "en": "Neurological diseases and their studies"},
    {"key": "history", "name": "Neuro History", "phase": 4, "art": "history",
     "es": "De Ramón y Cajal a hoy, con los Nobel", "en": "From Ramón y Cajal to today, with the "
     "Nobel prizes"},
    {"key": "experiments", "name": "Neuro Experiments", "phase": 4, "art": "experiments",
     "es": "Ilusiones y pruebas para ponerte a prueba",
     "en": "Illusions and tests to try yourself"},
]  # fmt: skip

# Topics from Sofía's sketch. Mock-up rule (a proposal): words in the title. The real one
# would use MeSH terms and the classifier.
TOPICS = {
    "memory": {"es": "Memoria", "en": "Memory", "slug_es": "memoria",
               "rx": r"memor|hippocamp|learning|recall|amnes"},
    "addiction": {"es": "Adicción", "en": "Addiction", "slug_es": "adiccion",
                  "rx": r"addict|substance use|alcohol|opioid|cocaine|nicotine|smok|cannabis"},
    "neurodegeneration": {"es": "Neurodegeneración", "en": "Neurodegeneration",
                          "slug_es": "neurodegeneracion",
                          "rx": r"alzheimer|parkinson|dementia|neurodegener|huntington|"
                                r"amyotrophic|\btau\b|amyloid|synuclein"},
    "neuroinflammation": {"es": "Neuroinflamación", "en": "Neuroinflammation",
                          "slug_es": "neuroinflamacion",
                          "rx": r"neuroinflam|microglia|astrocyt|cytokine|inflamm"},
    "sleep": {"es": "Sueño", "en": "Sleep", "slug_es": "sueno",
              "rx": r"sleep|insomnia|circadian|apnea|narcolep"},
    "emotion": {"es": "Emoción", "en": "Emotion", "slug_es": "emocion",
                "rx": r"emotion|fear|anxiety|amygdala|mood|depress|affective"},
}  # fmt: skip

T3: dict[str, dict[str, str]] = {
    "es": {
        "hub": "Tu portal de neurociencia",
        "hub_sub": "Neurociencia, cada día, comprobada: estudios nuevos con sus señales a la "
                   "vista y secciones para entender el cerebro.",
        "jump_today": "Noticias de hoy",
        "about": "Sobre nosotros", "search": "Buscar", "search_ph": "Buscar estudios, temas, "
                                                                    "siglas…",
        "search_title": "Buscar", "search_none": "Nada coincide con «{q}».",
        "search_hint": "Escribe al menos dos letras.", "search_all": "Ver todos los resultados",
        "search_n": "{n} resultados para «{q}»",
        "kind_study": "Estudio", "kind_news": "Noticia", "kind_section": "Sección",
        "kind_topic": "Tema", "kind_term": "Glosario", "kind_page": "Página",
        "soon_phase": "Fase {n}", "soon_word": "próximamente", "preview": "Avance · prototipo",
        "topics": "Explora por temas", "topic_n": "{n} hoy", "topic_none": "Hoy no hay "
                                                                          "estudios de este tema.",
        "topic_intro": "Estudios y noticias de hoy sobre {t}.",
        "glossary": "Glosario",
        "gl_intro": "Neuro Glossary llega en la Fase 2. Estos son los {n} términos de ejemplo "
                    "de la propuesta, con sus definiciones por revisar. En los resúmenes y "
                    "títulos de la web, los términos del glosario aparecen subrayados: "
                    "pasa el ratón o tócalos para leer su definición.",
        "gl_search": "Buscar en el glosario", "gl_review": "Definición de ejemplo, por revisar "
                                                         "(Sofía)",
        "gl_pending": "Definición pendiente.", "gl_see": "Ver en el glosario",
        "gl_also": "aquí:",
        "prev": "Anterior", "next": "Siguiente",
        "atlas_hero_credit": "Cerebro: captura de nuestro visor · {atlas} · {lic}",
        "art_credit": "Ilustraciones: SYNAPTICA, CC BY-SA 4.0.",
        "week_link": "Resumen de la semana",
        "gap_topics": "Temas: en la maqueta, palabras del título (por ejemplo «hippocamp» "
                      "para Memoria). La versión real usaría los términos MeSH de PubMed y el "
                      "clasificador. «Emoción» roza lo que se dejó fuera en v13 («sistemas "
                      "emocionales como función principal»): como tema de noticias parece "
                      "válido, pero lo confirma Sofía.",
        "gap_glossary": "Glosario: los 17 términos de ejemplo de la propuesta, con sus "
                        "definiciones por revisar (Sofía). En inglés aún no existen: el término "
                        "se marca igual y su definición queda vacía. Las formas que se buscan "
                        "en los textos (la sigla, en mayúsculas exactas, y su nombre completo "
                        "en español o inglés, en cualquier caja) están en "
                        "data/glossary_forms.csv. Marcado copiado de Paleo Atlas: solo la "
                        "primera aparición de cada término en la página, y nunca dentro de un "
                        "enlace.",
        "gap_about": "Borrador: Aday y Sofía escriben su presentación. Aquí solo va lo que "
                     "ya dicen SCOPE y la propuesta.",
        "gap_search": "Buscador: busca en lo que hay en la web hoy (estudios, noticias, "
                      "secciones, temas y siglas), en el navegador y sin servicios externos. "
                      "Adaptado del de Paleo Atlas.",
        "gap_illus": "Ilustraciones: dibujos propios en SVG, provisionales. Se pueden "
                     "cambiar por fotos de Commons con licencia o por capturas de cada sección "
                     "cuando exista.",
        "footer_images": "Imágenes: ilustraciones propias (CC BY-SA 4.0); capturas de nuestro "
                         "visor, una por atlas: Waxholm (CC BY 4.0) y Julich-Brain (CC "
                         "BY-NC-SA 4.0); figuras de estudios de acceso abierto de PMC, cada una "
                         "con su licencia.",
        "about_title": "Sobre nosotros",
        "draft": "Borrador",
    },
    "en": {
        "hub": "Your neuroscience hub",
        "hub_sub": "Neuroscience, every day, checked: new studies with their signals in plain "
                   "sight and sections to understand the brain.",
        "jump_today": "Today's news",
        "about": "About us", "search": "Search", "search_ph": "Search studies, topics, "
                                                             "acronyms…",
        "search_title": "Search", "search_none": "Nothing matches «{q}».",
        "search_hint": "Type at least two letters.", "search_all": "See all results",
        "search_n": "{n} results for «{q}»",
        "kind_study": "Study", "kind_news": "News", "kind_section": "Section",
        "kind_topic": "Topic", "kind_term": "Glossary", "kind_page": "Page",
        "soon_phase": "Phase {n}", "soon_word": "coming soon", "preview": "Preview · prototype",
        "topics": "Explore by topic", "topic_n": "{n} today", "topic_none": "No studies on "
                                                                          "this topic today.",
        "topic_intro": "Today's studies and news about {t}.",
        "glossary": "Glossary",
        "gl_intro": "Neuro Glossary arrives in Phase 2. These are the {n} sample terms of the "
                    "proposal. Their definitions exist only in Spanish and are still under "
                    "review, so here they are left empty. In the site's summaries and titles, "
                    "glossary terms are underlined: hover or tap them.",
        "gl_search": "Search the glossary", "gl_review": "Sample definition, to be reviewed "
                                                       "(Sofía)",
        "gl_pending": "Definition pending: for now the glossary exists only in Spanish, under "
                      "review.", "gl_see": "See in the glossary",
        "gl_also": "here:",
        "prev": "Previous", "next": "Next",
        "atlas_hero_credit": "Brain: capture of our viewer · {atlas} · {lic}",
        "art_credit": "Illustrations: SYNAPTICA, CC BY-SA 4.0.",
        "week_link": "This week's summary",
        "gap_topics": "Topics: in the mock-up, words in the title (for example «hippocamp» "
                      "for Memory). The real version would use PubMed's MeSH terms and the "
                      "classifier. «Emotion» brushes against what v13 left out («emotional "
                      "systems as a main feature»): as a news topic it looks fine, but Sofía "
                      "confirms.",
        "gap_glossary": "Glossary: the 17 sample terms of the proposal exist only in Spanish, "
                        "with definitions still to review (Sofía). In English the term is "
                        "marked all the same and its definition is left empty. The forms "
                        "searched in the texts (the acronym, in its exact case, and its full "
                        "name in Spanish or English, in any case) are in "
                        "data/glossary_forms.csv. Marking copied from Paleo Atlas: only the "
                        "first appearance of each term on the page, and never inside a link.",
        "gap_about": "Draft: Aday and Sofía write their own introduction. Only what SCOPE and "
                     "the proposal already say is here.",
        "gap_search": "Search: over what the site has today (studies, news, sections, topics "
                      "and acronyms), in the browser, with no outside service. Adapted from "
                      "Paleo Atlas.",
        "gap_illus": "Illustrations: our own SVG drawings, provisional. They can become "
                     "licensed Commons photos, or captures of each section once it exists.",
        "footer_images": "Images: our own illustrations (CC BY-SA 4.0); captures of our "
                         "viewer, one per atlas: Waxholm (CC BY 4.0) and Julich-Brain (CC "
                         "BY-NC-SA 4.0); figures from PMC open-access studies, each with its "
                         "licence.",
        "about_title": "About us",
        "draft": "Draft",
    },
}  # fmt: skip


def topic_items(rx: str, latest: list, nsc: list, news: list) -> dict[str, list]:
    hit = lambda s: re.search(rx, s.get("title") or "", re.I)  # noqa: E731
    return {"studies": [s for s in latest + nsc if hit(s)], "news": [n for n in news if hit(n)]}


def search_index(lang: str, ctx: dict[str, Any], url: Any) -> list[list[str]]:
    """[kind, text, extra words, url] for the browser search; URLs relative to the lang
    folder."""
    t = T[lang] | T2[lang] | T3[lang]
    # Pages, sections, topics and acronyms first: on a tie (stable sort) they win.
    out = [[t["kind_page"], t[k], "", url(k)] for k in ("news", "week", "method", "about")]
    out += [[t["kind_section"], s["name"], s[lang], ATLAS_URL if s["key"] == "atlas" else ""]
            for s in SECTIONS]  # fmt: skip
    out += [[t["kind_topic"], v[lang], k, url("topic", tslug(k, lang))] for k, v in TOPICS.items()]
    out += [[t["kind_term"], r["term"], " ".join([r[f"meaning_{lang}"], *r["forms_any_case"]]),
             url("glossary") + "#" + r["term_id"]] for r in ctx["terms"]]  # fmt: skip
    out += [[t["kind_study"], s["title"], f"{s.get('journal') or ''} {s.get('type') or ''}",
             url("study", slug(s["study_id"]))] for s in ctx["by_id"].values()]  # fmt: skip
    out += [[t["kind_news"], n["title"], n["outlet"], n["url"]] for n in ctx["data"]["news"]]
    return out


def tslug(key: str, lang: str) -> str:
    return TOPICS[key]["slug_es"] if lang == "es" else key


def render(env: Any, x: str, lang: str, template: str, kind: str, arg: str | None,
           **ctx: Any) -> None:  # fmt: skip
    other = "en" if lang == "es" else "es"
    rel = ROUTES[lang][kind].format(arg) if arg else ROUTES[lang][kind]
    other_arg = arg
    if kind == "topic" and arg:
        key = next(k for k in TOPICS if tslug(k, lang) == arg)
        other_arg = tslug(key, other)
    other_rel = ROUTES[other][kind].format(other_arg) if arg else ROUTES[other][kind]
    up = "../" * rel.count("/")

    def url(k: str, a: str | None = None) -> str:
        return up + (ROUTES[lang][k].format(a) if a else ROUTES[lang][k])

    g = gaps(lang, x)
    g |= {"topics": ("proposal", T3[lang]["gap_topics"]),
          "glossary": ("gap", T3[lang]["gap_glossary"]),
          "about": ("gap", T3[lang]["gap_about"]),
          "search": ("proposal", T3[lang]["gap_search"]),
          "illus": ("proposal", T3[lang]["gap_illus"])}  # fmt: skip
    gl, used = Glossary(ctx["terms"], lang, url("glossary")), set()

    def mark(text: str) -> Markup:
        """Glossary terms in a text of the page (escaped here), first appearance only."""
        return Markup(gl.mark(html.escape(text, quote=False), used))

    def gl_data(extra: set[str] = frozenset()) -> Markup:
        """The popovers' JSON (empty when the page marks no term)."""
        ids = used | set(extra)
        if not ids:
            return Markup("")
        tt = T3[lang]
        labels = {k: tt[k] for k in ("gl_also", "gl_see", "gl_review", "gl_pending")}
        doc = json.dumps({"glossary": gl.page_data(ids), "labels": labels},
                         ensure_ascii=False, separators=(",", ":"))  # fmt: skip
        doc = doc.replace("</", "<\\/")
        return Markup(f'<script type="application/json" id="page-data">{doc}</script>')

    page = env.get_template(template).render(
        lang=lang, t=T[lang] | T2[lang] | T3[lang], x=x, style=STYLES[x], up=up,
        root=up + "../", fonts_root=up + "../../../", img=up + "../../../img/",
        other_lang=other, other_url=up + "../" + other + "/" + other_rel, url=url, slug=slug,
        page_kind=kind, date=lambda v, long=False: fmt_date(v, lang, long), sj=short_journal,
        signals=functools.partial(signals, lang=lang),
        licence=functools.partial(licence_lines, lang=lang), types=TYPES, fonts=FONTS[lang][x],
        gaps=g, fact_kind=FACT[x], atlas_url=ATLAS_URL,
        lic_name=lambda v: LIC_NAMES[lang].get(v, v),
        figure_label=functools.partial(figure_label, lang=lang), sections=SECTIONS,
        topics=TOPICS, tslug=functools.partial(tslug, lang=lang), gl=mark, gl_data=gl_data,
        gl_entries=gl.entries, **ctx,
    )  # fmt: skip
    path = V3 / x / lang / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(page, encoding="utf-8")


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
    topic_hits = {k: topic_items(v["rx"], latest, data["nsc"], data["news"])
                  for k, v in TOPICS.items()}  # fmt: skip
    common = {
        "data": data, "by_id": studies, "latest": latest, "lead": lead,
        "today": [s for s in latest if s["study_id"] != lead["study_id"]][:3],
        "type_counts": {k: sum(s["type"] == k for s in latest) for k in TYPES},
        "figs": images["figures"], "atlas": images["atlas"], "topic_hits": topic_hits,
        "terms": load_rows(),
    }  # fmt: skip
    from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

    for x in STYLES:
        out = V3 / x
        for lang in LANGS:
            shutil.rmtree(out / lang, ignore_errors=True)
        (out / "static").mkdir(parents=True, exist_ok=True)
        css = "".join((V3 / "styles" / n).read_text(encoding="utf-8")
                      for n in (f"{x}.css", "base.css"))  # fmt: skip
        (out / "static" / f"{x}.css").write_text(css, encoding="utf-8")
        for name in ("site.js", "search.js", "glossary.js"):
            shutil.copy(V3 / "styles" / name, out / "static" / name)
        shutil.copy(V3 / "styles/favicon.svg", out / "static" / "favicon.svg")
        env = Environment(
            loader=FileSystemLoader([V3 / "templates", HERE / "shared"]),
            autoescape=select_autoescape(["html", "j2"]),
            undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True,
        )  # fmt: skip
        for lang in LANGS:
            for kind in ("index", "news", "method", "week", "about", "search", "glossary"):
                render(env, x, lang, f"{kind}.html.j2", kind, None, **common)
            for sid, s in studies.items():
                render(env, x, lang, "study.html.j2", "study", slug(sid), s=s, **common)
            for key in TOPICS:
                render(env, x, lang, "topic.html.j2", "topic", tslug(key, lang), topic=key,
                       **common)  # fmt: skip
            idx = search_index(lang, common, lambda k, a=None, lang=lang: (
                ROUTES[lang][k].format(a) if a else ROUTES[lang][k]))  # fmt: skip
            (out / lang / ROUTES[lang]["search_index"]).write_text(
                json.dumps(idx, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
            )
        print(f"{x}: {sum(1 for _ in out.rglob('*.html'))} pages")


if __name__ == "__main__":
    main()
