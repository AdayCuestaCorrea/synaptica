"""Strings, gaps and the fact-of-the-day choice added in round two of the mock-ups (SCOPE
v77), still used by ``build3.py``. Its pages were removed in SCOPE v79.
"""

from __future__ import annotations

import re
from pathlib import Path

from build import T

HERE = Path(__file__).parent
STYLES = {"n": "Noche"}  # chosen in v79; G «Gaceta» and L «Lámina» removed
FACT = {"g": "a", "n": "b", "l": "c"}  # each style carries one proposal for step 26
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
