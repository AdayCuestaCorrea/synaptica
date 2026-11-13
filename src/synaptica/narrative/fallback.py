"""What the site shows for a study: its verified summary, or a fallback sentence built
only from the data (plan, step 16; CLAUDE.md: "un texto que no pasa no se publica").

The fallback follows paleo-atlas ``src/paleo/site/fallback.py``: no LLM, every word comes
from the ``dim_study`` fields, and each part is left out when its field is missing (a
missing signal is never guessed). For example: "Estudio en animales publicado en Neuron
el 5 de noviembre de 2026."
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from synaptica.narrative.write import text_path

_MONTHS_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
              "septiembre", "octubre", "noviembre", "diciembre"]  # fmt: skip
_MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July", "August",
              "September", "October", "November", "December"]  # fmt: skip
_SUBJECT = {
    "en": {"humans": "in humans", "animals": "in animals", "both": "in humans and animals"},
    "es": {"humans": "en humanos", "animals": "en animales", "both": "en humanos y animales"},
}
_INTEGRITY = {
    "en": {
        "retracted": "It has been retracted.",
        "partially_retracted": "It has been partly retracted.",
        "withdrawn": "Its authors have withdrawn it from the preprint server.",
        "concern": "The journal has published an expression of concern about it.",
        "corrected": "A correction has been published.",
    },
    "es": {
        "retracted": "Se ha retractado.",
        "partially_retracted": "Se ha retractado en parte.",
        "withdrawn": "Sus autores lo han retirado del servidor de preprints.",
        "concern": "La revista ha publicado una nota de preocupación sobre él.",
        "corrected": "Se ha publicado una corrección.",
    },
}


def _date(value: Any, lang: str) -> str | None:
    if value is None:
        return None
    day = value if isinstance(value, dt.date) else dt.date.fromisoformat(str(value)[:10])
    if lang == "es":
        return f"{day.day} de {_MONTHS_ES[day.month - 1]} de {day.year}"
    return f"{day.day} {_MONTHS_EN[day.month - 1]} {day.year}"


def _day(value: Any) -> dt.date | None:
    if value is None:
        return None
    return value if isinstance(value, dt.date) else dt.date.fromisoformat(str(value)[:10])


def print_issue(study: dict[str, Any]) -> dt.date | None:
    """The publication date when it is after the day the study entered: the date of a print
    issue still to come (PubMed), not a day already passed (Aday, SCOPE v102)."""
    published, entered = _day(study.get("published_on")), _day(study.get("entered_on"))
    return published if published and entered and published > entered else None


def _issue(day: dt.date, lang: str) -> str:
    if lang == "es":
        return f"en el número de {_MONTHS_ES[day.month - 1]} de {day.year}"
    return f"in the {_MONTHS_EN[day.month - 1]} {day.year} issue"


def fallback_text(study: dict[str, Any], lang: str) -> str:
    preprint = study.get("review_status") == "preprint"
    subject = _SUBJECT[lang].get(study.get("species") or "unknown")
    issue = print_issue(study)
    journal, date = study.get("journal"), _date(study.get("published_on"), lang)
    when = _issue(issue, lang) if issue else None
    if lang == "es":
        parts = ["Preprint" if preprint else "Estudio", subject, "publicado"]
        parts += [f"en {journal}" if journal else None]
        parts += [when or (f"el {date}" if date else None)]
        sentence = " ".join(p for p in parts if p) + "."
        if preprint:
            sentence += " Aún no ha pasado la revisión por pares."
    else:
        parts = ["Preprint" if preprint else "Study", subject, "published"]
        parts += [f"in {journal}" if journal else None]
        parts += [when or (f"on {date}" if date else None)]
        sentence = " ".join(p for p in parts if p) + "."
        if preprint:
            sentence += " It has not been peer reviewed yet."
    if note := _INTEGRITY[lang].get(study.get("integrity") or "none"):
        sentence += " " + note
    return sentence


def summary_for(
    study: dict[str, Any], lang: str, *, derived_root: Path | None = None
) -> dict[str, Any]:
    """``{"kind": "verified", "sentences": [...], "generator": …}`` when the text of that
    language passed its checks and the judge (step 19), else ``{"kind": "fallback",
    "text": …}``. A text waiting for the judge is not shown yet."""
    record = verified_record(study["study_id"], lang, derived_root=derived_root)
    if record:
        return {"kind": "verified", "sentences": record["sentences"],
                "generator": record["generator"],
                "judge": record["judge"]["generator"]}  # fmt: skip
    return {"kind": "fallback", "text": fallback_text(study, lang)}


def verified_record(
    study_id: str, lang: str, *, derived_root: Path | None = None
) -> dict[str, Any] | None:
    """The text record of that language when it passed its checks and the judge."""
    path = text_path(study_id, lang, verified=True, derived_root=derived_root)
    if not path.exists():
        return None
    record = json.loads(path.read_text(encoding="utf-8"))
    judged = (record.get("judge") or {}).get("passed") is True
    return record if record["status"] == "verified" and record["sentences"] and judged else None
