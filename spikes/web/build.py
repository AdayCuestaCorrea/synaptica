"""Shared rules and strings of the web mock-ups: what a study shows (its three signals, its
text and its licence), dates and every visible string in Spanish and English. Used by
``build3.py``; the round-one pages that this file rendered were removed in SCOPE v79.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
LANGS = ("es", "en")
MONTHS = {
    "es": ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sept", "oct", "nov", "dic"],
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
}
LONG_MONTHS = {
    "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
           "septiembre", "octubre", "noviembre", "diciembre"],
    "en": ["January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December"],
}  # fmt: skip
WEEKDAYS = {"es": ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"],
            "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
                   "Sunday"]}  # fmt: skip
TYPES = ("healthy_brain", "disease", "clinical_trial", "technique")

# Every visible string, in both languages. «journal» is provisional on purpose (Sofía).
T: dict[str, dict[str, str]] = {
    "es": {
        "tagline": "Neurociencia, cada día, comprobada",
        "news": "Neuro News", "method": "Cómo evaluamos", "week": "Resumen semanal",
        "latest": "Última hora", "nsc": "Nature · Science · Cell", "classics": "Clásicos",
        "media": "En los medios", "fact": "Dato curioso del día",
        "disclaimer": "Información divulgativa: no es consejo médico. Ante cualquier duda de "
                      "salud, consulta a un profesional sanitario.",
        "classics_empty": "Todavía no hay Clásicos. Cada semana la web propone estudios muy "
                          "citados de años anteriores, y solo se publican los que aprueba "
                          "Sofía. Esta semana aún no ha aprobado ninguno.",
        "filter_all": "Todos", "filter_label": "Filtrar por tipo",
        "type_healthy_brain": "Cerebro sano", "type_disease": "Enfermedad",
        "type_clinical_trial": "Ensayo clínico", "type_technique": "Técnica",
        "type_none": "Sin clasificar",
        "filter_empty": "No hay estudios de este tipo hoy.",
        "sig_review": "Revisión", "sig_subject": "Sujetos", "sig_integrity": "Avisos",
        "rev_preprint": "Preprint · sin revisión por pares",
        "rev_preprint_short": "Preprint",
        "rev_journal": "Publicado en revista", "rev_journal_short": "Revista",
        "rev_unknown": "Sin dato",
        "provisional": "provisional",
        "provisional_long": "Texto provisional: «publicado en revista» no prueba la revisión "
                            "por pares. El nombre de esta señal lo decide Sofía.",
        "sp_humans": "Humanos", "sp_animals": "Animales", "sp_both": "Humanos y animales",
        "sp_unknown": "Sin dato",
        "int_none": "Sin avisos", "int_retracted": "Retractado",
        "int_partially_retracted": "Retractado en parte",
        "int_concern": "Nota de preocupación", "int_corrected": "Corregido",
        "verified": "Resumen verificado",
        "verified_note": "Cada frase se ha comprobado contra el estudio (cita, cifras, nombres, "
                         "sin copiar 8 palabras seguidas) y la ha aprobado un juez de otra "
                         "familia de modelos.",
        "fallback": "Texto de respaldo",
        "fallback_note": "Aún no hay un resumen que haya pasado las comprobaciones, así que "
                         "solo se muestra lo que dicen los datos.",
        "fallback_judge": "El resumen escrito no se publica: lo rechazó el juez",
        "fallback_failed": "El resumen escrito no se publica: no pasó las comprobaciones",
        "original": "Leer el estudio original", "license": "Licencias",
        "lic_text_verified": "Resumen: texto propio de SYNAPTICA, CC BY-SA 4.0. Redactado por "
                             "{gen}, verificado y aprobado por el juez {judge}.",
        "lic_text_fallback": "Texto: construido solo con los datos, CC BY-SA 4.0.",
        "lic_meta": "Metadatos: {src}.",
        "lic_original": "Original: {lic}.", "lic_original_none": "Original: licencia sin dato.",
        "cite": "Fuente de esta frase: el resumen (abstract) del estudio, que no se reproduce.",
        "title_original": "Título original en inglés",
        "gap": "Hueco", "proposal": "Propuesta",
        "gap_title_es": "traducción del título pendiente (la hace el LLM, paso 16)",
        "gap_types": "Tipo de cada pieza: lo decide el clasificador (paso 14a), que aún no se "
                     "ha ejecutado. Solo «Ensayo clínico» sale ya del tipo de publicación de "
                     "PubMed.",
        "gap_groups": "Agrupación: «la misma historia en varios medios» la decide el LLM (paso "
                      "15), que aún no se ha ejecutado. Cada noticia sale sola, en el mismo "
                      "componente que mostrará el grupo.",
        "sources_n": "{n} medio", "sources_n_pl": "{n} medios",
        "week_cta": "Lee el resumen de la semana", "week_of": "Semana",
        "week_gap": "El resumen semanal verificado no existe aún (requiere el LLM): se "
                    "muestra su texto de respaldo, construido con los datos.",
        "week_studies": "Estudios de la semana",
        "more": "Ver todos", "authors": "Autores", "journal": "Revista", "date": "Fecha",
        "doi": "DOI", "pmid": "PMID", "et_al": "y otros", "back": "Volver a Neuro News",
        "footer_credits": "Créditos y licencias",
        "footer_text": "Textos propios: CC BY-SA 4.0. Código: AGPL-3.0. Cada estudio y cada "
                       "noticia enlazan a su original y muestran su licencia.",
        "footer_sources": "Datos: PubMed y PMC (NLM), Europe PMC, bioRxiv y medRxiv, Crossref, "
                          "OpenAlex (CC0), Wikidata (CC0); metadatos y enlaces de los RSS de "
                          "Nature, Science y Cell; titulares de SINC, The Conversation (CC "
                          "BY-ND 4.0) y ScienceDaily.",
        "footer_fonts": "Fuentes tipográficas: {fonts}.",
        "footer_by": "Hecho por Aday y Sofía.",
        "theme": "Tema", "theme_auto": "Automático", "theme_light": "Claro",
        "theme_dark": "Oscuro",
        "lang_switch": "English", "lang_code": "EN",
        "mock": "Maqueta {x} · datos reales del 12 nov 2026 · los huecos están marcados",
        "skip": "Saltar al contenido",
        "fact_a_note": "Propuesta para el paso 26: una frase de un resumen verificado del día, "
                       "con su estudio.",
        "fact_b_note": "Propuesta para el paso 26: una cifra calculada del almacén, sin LLM.",
        "fact_c_note": "Propuesta para el paso 26: una efeméride de Wikidata (CC0), sin LLM.",
        "fact_b": "Hoy han entrado {total} estudios candidatos: {humans} incluyen humanos, "
                  "{animals} incluyen animales y en {unknown} no consta. {preprints} son "
                  "preprints.",
        "fact_b_caveat": "Incluye ruido aún sin filtrar (paso 14a).",
        "fact_c": "Tal día como hoy, en {year}, nació {name}.",
        "fact_c_gap": "descripción en español: Wikidata no la tiene",
        "fact_source": "Fuente",
        "s5_note": "Los resúmenes verificados son los de S5 (estudios del 2 al 8 de noviembre); "
                   "la cadena nueva aún no se ha ejecutado.",
        "tab_label": "Bloques de noticias", "nsc_note": "Todo lo que publican de neuro, sin "
                                                         "elegir a mano.",
        "lead": "Destacado", "examples": "Así se ven las señales",
        "read_more": "Seguir leyendo",
        "of": "de", "count_today": "hoy",
    },
    "en": {
        "tagline": "Neuroscience, every day, checked",
        "news": "Neuro News", "method": "How we evaluate", "week": "Weekly summary",
        "latest": "Latest", "nsc": "Nature · Science · Cell", "classics": "Classics",
        "media": "In the media", "fact": "Fact of the day",
        "disclaimer": "General information, not medical advice. For any health question, "
                      "ask a health professional.",
        "classics_empty": "No Classics yet. Every week the site proposes highly cited studies "
                          "from past years, and only those Sofía approves are published. She "
                          "has not approved any this week yet.",
        "filter_all": "All", "filter_label": "Filter by type",
        "type_healthy_brain": "Healthy brain", "type_disease": "Disease",
        "type_clinical_trial": "Clinical trial", "type_technique": "Technique",
        "type_none": "Unclassified",
        "filter_empty": "No studies of this type today.",
        "sig_review": "Review", "sig_subject": "Subjects", "sig_integrity": "Notices",
        "rev_preprint": "Preprint · not peer reviewed",
        "rev_preprint_short": "Preprint",
        "rev_journal": "Published in a journal", "rev_journal_short": "Journal",
        "rev_unknown": "No data",
        "provisional": "provisional",
        "provisional_long": "Provisional wording: «published in a journal» does not prove peer "
                            "review. Sofía decides what this signal is called.",
        "sp_humans": "Humans", "sp_animals": "Animals", "sp_both": "Humans and animals",
        "sp_unknown": "No data",
        "int_none": "No notices", "int_retracted": "Retracted",
        "int_partially_retracted": "Partly retracted",
        "int_concern": "Expression of concern", "int_corrected": "Corrected",
        "verified": "Verified summary",
        "verified_note": "Each sentence was checked against the study (citation, figures, "
                         "names, no 8 words in a row copied) and approved by a judge from "
                         "another model family.",
        "fallback": "Fallback text",
        "fallback_note": "No summary has passed the checks yet, so only what the data says is "
                         "shown.",
        "fallback_judge": "The written summary is not published: the judge rejected it",
        "fallback_failed": "The written summary is not published: it failed the checks",
        "original": "Read the original study", "license": "Licences",
        "lic_text_verified": "Summary: SYNAPTICA's own text, CC BY-SA 4.0. Written by {gen}, "
                             "checked and approved by the judge {judge}.",
        "lic_text_fallback": "Text: built only from the data, CC BY-SA 4.0.",
        "lic_meta": "Metadata: {src}.",
        "lic_original": "Original: {lic}.", "lic_original_none": "Original: licence unknown.",
        "cite": "Source of this sentence: the study's abstract, which is not reproduced.",
        "title_original": "Original title",
        "gap": "Gap", "proposal": "Proposal",
        "gap_title_es": "",
        "gap_types": "Type of each item: set by the classifier (step 14a), not run yet. Only "
                     "«Clinical trial» already comes from PubMed's publication type.",
        "gap_groups": "Grouping: «the same story in several outlets» is decided by the LLM "
                      "(step 15), not run yet. Each item appears alone, in the same component "
                      "that will show the group.",
        "sources_n": "{n} outlet", "sources_n_pl": "{n} outlets",
        "week_cta": "Read this week's summary", "week_of": "Week",
        "week_gap": "The verified weekly summary does not exist yet (it needs the LLM): its "
                    "fallback text, built from the data, is shown.",
        "week_studies": "Studies of the week",
        "more": "See all", "authors": "Authors", "journal": "Journal", "date": "Date",
        "doi": "DOI", "pmid": "PMID", "et_al": "et al.", "back": "Back to Neuro News",
        "footer_credits": "Credits and licences",
        "footer_text": "Our texts: CC BY-SA 4.0. Code: AGPL-3.0. Every study and news item "
                       "links to its original and shows its licence.",
        "footer_sources": "Data: PubMed and PMC (NLM), Europe PMC, bioRxiv and medRxiv, "
                          "Crossref, OpenAlex (CC0), Wikidata (CC0); metadata and links from "
                          "the Nature, Science and Cell RSS feeds; headlines from SINC, The "
                          "Conversation (CC BY-ND 4.0) and ScienceDaily.",
        "footer_fonts": "Typefaces: {fonts}.",
        "footer_by": "Made by Aday and Sofía.",
        "theme": "Theme", "theme_auto": "Automatic", "theme_light": "Light",
        "theme_dark": "Dark",
        "lang_switch": "Español", "lang_code": "ES",
        "mock": "Mock-up {x} · real data from 12 Nov 2026 · gaps are marked",
        "skip": "Skip to content",
        "fact_a_note": "Proposal for step 26: one sentence of a verified summary of the day, "
                       "with its study.",
        "fact_b_note": "Proposal for step 26: a number computed from the warehouse, no LLM.",
        "fact_c_note": "Proposal for step 26: an anniversary from Wikidata (CC0), no LLM.",
        "fact_b": "{total} candidate studies came in today: {humans} include humans, "
                  "{animals} include animals and {unknown} do not say. {preprints} are "
                  "preprints.",
        "fact_b_caveat": "Includes noise not filtered yet (step 14a).",
        "fact_c": "On this day in {year}, {name} was born.",
        "fact_c_gap": "",
        "fact_source": "Source",
        "s5_note": "The verified summaries are those from S5 (studies of 2 to 8 November); the "
                   "new chain has not run yet.",
        "tab_label": "News blocks", "nsc_note": "Everything they publish on neuroscience, not "
                                                "hand-picked.",
        "lead": "Featured", "examples": "What the signals look like",
        "read_more": "Read more",
        "of": "of", "count_today": "today",
    },
}  # fmt: skip
META_SOURCES = {"pubmed": "PubMed (NLM)", "europepmc": "Europe PMC", "biorxiv": "bioRxiv",
                "medrxiv": "medRxiv", "journals": "RSS de la revista / journal RSS",
                "crossref": "Crossref"}  # fmt: skip
LICENSES = {"cc_by": "CC BY", "cc by": "CC BY", "cc_by_nc": "CC BY-NC", "cc by-nc": "CC BY-NC",
            "cc_by_nc_nd": "CC BY-NC-ND", "cc by-nc-nd": "CC BY-NC-ND",
            "cc_by_nc_sa": "CC BY-NC-SA", "cc by-nc-sa": "CC BY-NC-SA", "cc_by_sa": "CC BY-SA",
            "cc by-sa": "CC BY-SA", "cc_by_nd": "CC BY-ND", "cc by-nd": "CC BY-ND",
            "cc0": "CC0", "cc_no": None}  # fmt: skip


def slug(study_id: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", study_id.lower()).strip("-")


def fmt_date(value: str | None, lang: str, long: bool = False) -> str | None:
    if not value:
        return None
    d = dt.date.fromisoformat(value[:10])
    if long:
        m = LONG_MONTHS[lang][d.month - 1]
        if lang == "es":
            return f"{WEEKDAYS[lang][d.weekday()]}, {d.day} de {m} de {d.year}"
        return f"{WEEKDAYS[lang][d.weekday()]}, {d.day} {m} {d.year}"
    return f"{d.day} {MONTHS[lang][d.month - 1]} {d.year}"


def short_journal(name: str | None) -> str | None:
    """PubMed's long titles («Journal of clinical sleep medicine : JCSM : official…») cut at
    the first colon or parenthesis; the full name stays on the study page."""
    if not name:
        return None
    return re.split(r" ?[:(]", name, maxsplit=1)[0].strip()


def signals(study: dict[str, Any], lang: str) -> list[dict[str, Any]]:
    """The three signals, each with a state (for colour and icon) and its words."""
    t = T[lang]
    review = study.get("review_status") or "unknown"
    species = study.get("species") or "unknown"
    integrity = study.get("integrity") or "none"
    return [
        {"key": "review", "label": t["sig_review"], "state": review,
         "text": t[f"rev_{review}"], "short": t.get(f"rev_{review}_short", t[f"rev_{review}"]),
         "provisional": review == "journal", "notices": []},
        {"key": "subject", "label": t["sig_subject"], "state": species,
         "text": t[f"sp_{species}"], "short": t[f"sp_{species}"], "provisional": False,
         "notices": []},
        {"key": "integrity", "label": t["sig_integrity"], "state": integrity,
         "text": t[f"int_{integrity}"], "short": t[f"int_{integrity}"],
         "provisional": False, "notices": study.get("integrity_notices") or []},
    ]  # fmt: skip


def licence_lines(study: dict[str, Any], lang: str) -> list[str]:
    t, s = T[lang], study["summary"][lang]
    if s["kind"] == "verified":
        gen = s["generator"].split("/", 1)[1] + " (Groq)"
        judge = s["judge"].split("/", 1)[1] + " (Groq)"
        lines = [t["lic_text_verified"].format(gen=gen, judge=judge)]
    else:
        lines = [t["lic_text_fallback"]]
    src = ", ".join(META_SOURCES.get(x, x) for x in study.get("sources") or [])
    lines.append(t["lic_meta"].format(src=src))
    lic = LICENSES.get((study.get("license") or "").lower())
    lines.append(t["lic_original"].format(lic=lic) if lic else t["lic_original_none"])
    return lines
