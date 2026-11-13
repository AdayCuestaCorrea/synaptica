"""Intake of Sofía's review Issues.

Moved from the spike ``spikes/s4/intake.py`` (plan, step R; ADR 0005).

The workflow ``spikes/s4/review-intake.yml`` (a draft, not active) will run it on every
``issues: opened`` event. Until the ``data`` branch exists (step 28) her Issues are read by
hand with ``syn review intake`` (decision of Aday, 2026-11-13); the workflow, and its
``REVIEWER_LOGIN`` variable, are switched on with step 28 and his OK. It never trusts
what the Issue says about who or when:

1. **Author**: only Issues by the reviewer's login (a repository *variable*, not a
   secret) are read; anything else is ignored without a word, so a stranger's Issue
   changes nothing.
2. **Block**: ``issue_block.decode``; a broken block is refused as a whole.
3. **Each decision**: the intake adds ``reviewed_by`` (the Issue's author),
   ``reviewed_at`` (its creation date, UTC) and ``source`` (``issue#N``), validates it with
   ``models.Decision`` and checks it against the current queue (unknown item, stale hash,
   picks outside the candidates, a private item sent from the public page).
4. **Her edits** of a text pass the mechanical checks again (decision of Aday,
   2026-11-11): numbers and names that are neither in the reviewed text nor in its
   sources, 8 words in a row copied from a source, and sentences that match no sentence
   of the reviewed text, so they cite nothing. If one fails, the edit is *held*: it goes
   back to her queue with the warning, and she fixes it or answers «lo mantengo».
5. **The judge** only advises: its remarks go in the reply, never block anything.

When she corrects only the Spanish, the English is rewritten from her version by the
LLM chain and checked like any generated text (decision of Aday, 2026-11-11); that is
the pipeline's job, not the intake's: the edit is applied with ``payload.en`` missing.

Outputs, in the data directory: ``decisions.jsonl`` (applied) and ``held.jsonl`` (edits
waiting for her), both append only, and the reply for the Issue. Running it twice on
the same Issue adds nothing. Command: ``syn review intake``.
"""

from __future__ import annotations

import datetime as dt
import difflib
import json
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from synaptica.config import get_paths
from synaptica.narrative import checks
from synaptica.narrative.sources import abstract_for
from synaptica.review.issue_block import BlockError, decode
from synaptica.review.models import Action, Decision, Queue, ReviewItem, TextContent, check_against

PUBMED = "pubmed-"
# The other sources of a study's abstract (step R: the spot-check of published summaries),
# named by where its facts were read: the abstract cache answers for each one.
STUDY_SOURCES = {
    PUBMED: lambda v: {"pmid": v},
    "biorxiv-": lambda v: {"doi": v, "sources": ["biorxiv"]},
    "medrxiv-": lambda v: {"doi": v, "sources": ["medrxiv"]},
    "pmc-": lambda v: {"pmcid": v},
}


def study_source(source_id: str) -> dict | None:
    """The ``dim_study`` fields ``abstract_for`` needs to read that source, or None."""
    for prefix, fields in STUDY_SOURCES.items():
        if source_id.startswith(prefix):
            return fields(source_id.removeprefix(prefix))
    return None


# A sentence of hers "is" a reviewed sentence (and keeps its citations) above this ratio.
SAME_SENTENCE = 0.5
_SPLIT = re.compile(r"\n+|(?<=[.!?…])\s+(?=[A-ZÁÉÍÓÚÑ¿¡«\"(])")

Judge = Callable[[ReviewItem, Decision], list[str]]


@dataclass
class Held:
    decision: Decision
    warnings: list[str]


@dataclass
class Outcome:
    status: str  # ignored | duplicate | refused | processed
    applied: list[Decision] = field(default_factory=list)
    held: list[Held] = field(default_factory=list)
    refused: list[tuple[str, str]] = field(default_factory=list)  # (what, why)
    repeated: list[str] = field(default_factory=list)  # identical to one already recorded
    advice: list[tuple[str, str]] = field(default_factory=list)  # (what, the judge's remark)
    reason: str = ""


# ---- checks of her edits -------------------------------------------------------------


def sentences(text: str) -> list[str]:
    return [s.strip() for s in _SPLIT.split(text) if s.strip()]


def _ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, checks.normalize(a), checks.normalize(b)).ratio()


def align(old: list[str], new: list[str]) -> list[int | None]:
    """For each sentence of hers, the reviewed sentence it corrects (None: she added it).

    The page gives her the text one sentence per line, so the two lists are aligned as
    sequences: unchanged sentences anchor the alignment, and in a replaced stretch the
    sentences pair up in order: a rewritten sentence is her correction of the one in its
    place, however much she changed it (a short fix scored below 0.5 when compared one by
    one; seen in the S4 dry run). Sentences left over in a stretch, or inserted, are hers
    and cite nothing, unless one still reads like a reviewed sentence of the stretch.
    """
    out: list[int | None] = [None] * len(new)
    norm_old, norm_new = [checks.normalize(x) for x in old], [checks.normalize(x) for x in new]
    sm = difflib.SequenceMatcher(None, norm_old, norm_new, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(j2 - j1):
                out[j1 + k] = i1 + k
        elif tag == "replace":
            pairs = min(i2 - i1, j2 - j1)
            for k in range(pairs):
                out[j1 + k] = i1 + k
            for j in range(j1 + pairs, j2):
                best = max(range(i1, i2), key=lambda i: _ratio(new[j], old[i]))
                if _ratio(new[j], old[best]) >= SAME_SENTENCE:
                    out[j] = best
    return out


def _short(text: str, n: int = 80) -> str:
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def edit_warnings(item: ReviewItem, payload: dict, source_texts: dict[str, str]) -> list[str]:
    """What fails in her edit of a text item (empty: it passes). In Spanish: she reads it.

    ``source_texts`` maps a source id to its text (the Wikipedia lead, the cached
    abstract); a source without text only skips the copy check.
    """
    content = item.base or item.content  # a held edit is checked against the original draft
    assert isinstance(content, TextContent)
    reviewed = " ".join(s.text for s in content.es + content.en)
    sources = [source_texts[s.id] for s in content.sources if s.id in source_texts]
    known_numbers = checks.numbers(reviewed).union(*map(checks.numbers, sources))
    known_names = {n.lower() for n in checks.names(reviewed).union(*map(checks.names, sources))}
    known_names |= {w.lower() for w in re.findall(r"\w+", reviewed)}  # the same word, anywhere
    source_grams = set().union(*(checks.ngrams(checks.words(s)) for s in sources))
    out = []
    for lang in ("es", "en"):
        text = payload.get(lang)
        if not text:
            continue
        label = "español" if lang == "es" else "inglés"
        for n in sorted(checks.numbers(text) - known_numbers):
            out.append(f"({label}) La cifra {n} no está en el texto revisado ni en su fuente.")
        # Per sentence: the first word of each one is capitalized anyway (seen in the test
        # with Sofía: «Mediante» opening her second paragraph was taken for a name).
        for name in sorted(set().union(*map(checks.names, sentences(text)))):
            if name.lower() not in known_names:
                out.append(f"({label}) «{name}» no aparece en el texto revisado ni en su fuente.")
        for run in checks.copied_runs(text, source_grams):
            out.append(f"({label}) Copia 8 palabras seguidas de la fuente: «{run}».")
        if content.sources:
            mine = sentences(text)
            matched = align([s.text for s in getattr(content, lang)], mine)
            for s, i in zip(mine, matched, strict=True):
                if i is None:
                    out.append(f"({label}) Frase nueva sin fuente: «{_short(s)}».")
    return out


def source_texts(queue: Queue, cache_root: Path, efetch: list[Path]) -> dict[str, str]:
    """The text of each study source of the queue (``STUDY_SOURCES``): the pipeline's
    abstract cache, else a PubMed efetch file (the S5 cache the test queue was built from).
    Read only to check her edits; never written anywhere."""
    ids = {s.id for i in queue.items if isinstance(i.content, TextContent)
           for s in i.content.sources if study_source(s.id)}  # fmt: skip
    pmids = {x.removeprefix(PUBMED) for x in ids if x.startswith(PUBMED)}
    out = {}
    for sid in sorted(ids):
        found = abstract_for(study_source(sid), cache_root=cache_root)
        if found:
            out[sid] = found[0]
    for path in efetch:
        for art in ET.parse(path).getroot().iter("PubmedArticle"):
            pmid = art.findtext(".//MedlineCitation/PMID") or ""
            text = "\n".join("".join(t.itertext()) for t in art.iter("AbstractText"))
            if pmid in pmids and text and PUBMED + pmid not in out:
                out[PUBMED + pmid] = text
    return out


def missing_sources(event: dict, queue: Queue, texts: dict[str, str]) -> list[str]:
    """Study sources without text of the items her Issue edits. Checking those edits
    without them would skip the copy check and flag the source's own numbers (seen in
    the test with Sofía), so the Issue waits until the cache has them."""
    try:
        block = decode(event["issue"].get("body") or "")
    except BlockError:
        return []
    items = {i.key: i for i in queue.items}
    out = set()
    for raw in block.decisions:
        item = items.get((raw.get("item_type"), raw.get("item_id")))
        if raw.get("action") == "edit" and item and isinstance(item.content, TextContent):
            out |= {s.id for s in item.content.sources
                    if study_source(s.id) and s.id not in texts}  # fmt: skip
    return sorted(out)


# ---- the Issue -----------------------------------------------------------------------


def _done_sources(data_dir: Path) -> set[str]:
    seen = set()
    for name in ("decisions.jsonl", "held.jsonl"):
        path = data_dir / name
        if path.exists():
            for line in path.read_text("utf-8").splitlines():
                row = json.loads(line)
                seen.add((row.get("decision") or row)["source"])
    return seen


def signature(d: dict) -> str:
    """What makes two decisions the same answer: item, version, action, payload and note
    (not who, when or which Issue)."""
    keys = ("item_type", "item_id", "content_sha256", "action", "payload", "note")
    return json.dumps({k: d.get(k) for k in keys}, ensure_ascii=False, sort_keys=True)


def _recorded(data_dir: Path) -> set[str]:
    """Signatures of every decision already applied or held. Seen in round 2 of the test:
    she opened the round-1 page again and sent all its answers a second time."""
    out = set()
    for name in ("decisions.jsonl", "held.jsonl"):
        path = data_dir / name
        if path.exists():
            for line in path.read_text("utf-8").splitlines():
                row = json.loads(line)
                out.add(signature(row.get("decision") or row))
    return out


def process(
    event: dict,
    queue: Queue,
    reviewer: str,
    *,
    done: set[str] = frozenset(),
    recorded: set[str] = frozenset(),
    source_texts: dict[str, str] | None = None,
    judge: Judge | None = None,
) -> Outcome:
    issue = event["issue"]
    author = issue["user"]["login"]
    if event.get("action") != "opened" or author.lower() != reviewer.lower():
        return Outcome("ignored", reason=f"not an opened Issue by the reviewer ({author})")
    source = f"issue#{issue['number']}"
    if source in done:
        return Outcome("duplicate", reason=f"{source} was already processed")
    try:
        block = decode(issue.get("body") or "")
    except BlockError as e:
        return Outcome("refused", reason=str(e))

    out = Outcome("processed")
    intake = {"reviewed_by": author, "reviewed_at": issue["created_at"], "source": source}
    for raw in block.decisions:
        what = f"{raw.get('item_type')}/{raw.get('item_id')}"
        if signature(raw) in recorded:
            out.repeated.append(what)
            continue
        try:
            decision = Decision.model_validate(raw | intake)
        except ValidationError as e:
            out.refused.append((what, e.errors()[0]["msg"]))
            continue
        problems = check_against(decision, queue)
        item = queue.get(decision.item_type, decision.item_id)
        if item is not None and not item.public and block.page == "public":
            problems.append("private item sent from the public page")
        if item is not None and decision.action is Action.KEEP and not item.warnings:
            problems.append("nothing to keep: the item has no warning")
        if problems:
            out.refused.append((what, "; ".join(problems)))
            continue
        if decision.action is Action.EDIT and isinstance(item.content, TextContent):
            warnings = edit_warnings(item, decision.payload, source_texts or {})
            if warnings:
                out.held.append(Held(decision, warnings))
                continue
        out.applied.append(decision)
        if judge is not None and item is not None and decision.action is Action.EDIT:
            out.advice += [(what, remark) for remark in judge(item, decision)]
    return out


# ---- reply and files -----------------------------------------------------------------

REFUSED_ES = {
    "stale: the item changed after she reviewed it": "el texto cambió después de que lo vieras",
    "private item sent from the public page": "no viene de la página que le corresponde",
    "nothing to keep: the item has no warning": "no tenía ningún aviso que mantener",
}


def _why_es(why: str) -> str:
    parts = [REFUSED_ES.get(p, p) for p in why.split("; ")]
    return "; ".join(parts)


def reply(out: Outcome, titles: dict[str, str]) -> str:
    """The comment for the Issue, in Spanish (it is public, like the Issue)."""
    if out.status == "refused":
        return ("No he podido leer las decisiones de este Issue, así que no se ha aplicado nada. "
                "Vuelve a la página de revisión y pulsa «Enviar» otra vez.\n\n"
                f"Detalle técnico: {out.reason}")  # fmt: skip
    t = lambda what: titles.get(what, what)  # noqa: E731
    lines = [f"Aplicadas: {len(out.applied)}."]
    if out.repeated:
        n = len(out.repeated)
        lines.append(f"{n} {'ya estaba aplicada' if n == 1 else 'ya estaban aplicadas'} "
                     "(las habías enviado antes): no se apuntan dos veces.")  # fmt: skip
    if out.held:
        lines += ["", "Vuelven a tu cola con un aviso (corrígelas o elige «Lo mantengo»):"]
        for h in out.held:
            lines.append(f"- {t(f'{h.decision.item_type}/{h.decision.item_id}')}")
            lines += [f"  - {w}" for w in h.warnings]
    if out.refused:
        lines += ["", "No se han aplicado:"]
        lines += [f"- {t(what)}: {_why_es(why)}" for what, why in out.refused]
    if out.advice:
        lines += ["", "El revisor automático comenta (no bloquea nada, solo por si te sirve):"]
        lines += [f"- {t(what)}: {remark}" for what, remark in out.advice]
    return "\n".join(lines)


def parts_note(event: dict, data_dir: Path) -> str:
    """Record this part of its send and say which parts have not arrived (round 2 of the
    test: she sent parts 4, 3 and 2 and lost track of part 1). Empty for a one-part send
    or a block without ``send``."""
    block = decode(event["issue"].get("body") or "")
    if not block.send or block.part[1] == 1:
        return ""
    path = data_dir / "parts.jsonl"
    rows = [json.loads(x) for x in path.read_text("utf-8").splitlines()] if path.exists() else []
    source = f"issue#{event['issue']['number']}"
    if not any(r["source"] == source for r in rows):
        rows.append({"send": block.send, "part": block.part[0], "of": block.part[1],
                     "source": source})  # fmt: skip
        data_dir.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rows[-1]) + "\n")
    got = {r["part"] for r in rows if r["send"] == block.send}
    total = block.part[1]
    missing = [n for n in range(1, total + 1) if n not in got]
    if not missing:
        return f"Con esta parte han llegado las {total} de este envío."
    names = ", ".join(map(str, missing))
    return (f"Esta es la parte {block.part[0]} de {total}. Aún no han llegado: {names}. "
            "Si no las enviaste, vuelve a la página y pulsa sus botones.")  # fmt: skip


def write(out: Outcome, data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    with (data_dir / "decisions.jsonl").open("a", encoding="utf-8") as f:
        for d in out.applied:
            f.write(json.dumps(d.model_dump(mode="json"), ensure_ascii=False) + "\n")
    with (data_dir / "held.jsonl").open("a", encoding="utf-8") as f:
        for h in out.held:
            row = {"decision": h.decision.model_dump(mode="json"), "warnings": h.warnings}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def run(
    event_path: Path,
    queue_path: Path,
    data_dir: Path,
    reviewer: str,
    reply_path: Path,
    cache_root: Path | None = None,
    efetch: list[Path] | None = None,
) -> dict:
    """Process one Issue event (``syn review intake``): what the workflow runs."""
    event = json.loads(event_path.read_text("utf-8"))
    queue = Queue.model_validate_json(queue_path.read_text("utf-8"))
    texts = source_texts(queue, cache_root or get_paths().cache, efetch or [])
    missing = missing_sources(event, queue, texts)
    if missing:
        return {"status": "error", "sources_without_text": missing}
    out = process(event, queue, reviewer, done=_done_sources(data_dir),
                  recorded=_recorded(data_dir), source_texts=texts)  # fmt: skip
    note = ""
    if out.status == "processed":
        write(out, data_dir)
        note = parts_note(event, data_dir)
    titles = {f"{i.item_type}/{i.item_id}": i.title_es for i in queue.items}
    if out.status in ("processed", "refused"):
        text = reply(out, titles) + (f"\n\n{note}" if note else "")
        reply_path.write_text(text + "\n", encoding="utf-8")
    return {"status": out.status, "applied": len(out.applied), "held": len(out.held),
            "refused": len(out.refused), "repeated": len(out.repeated)}  # fmt: skip


def queue_for(event_path: Path, queue_dir: Path) -> Path | None:
    """The queue her page showed (``queue-<day>.json``, by the ``queue:`` header of the
    Issue: the queue's ``generated_at`` is midnight UTC of its day), else the newest one.
    The body is read from the event file, never from a shell argument (step 28)."""
    event = json.loads(event_path.read_text("utf-8"))
    try:
        stamp = decode(event["issue"].get("body") or "").queue
        path = queue_dir / f"queue-{dt.datetime.fromisoformat(stamp).date().isoformat()}.json"
        if path.exists():
            return path
    except BlockError, ValueError, KeyError:
        pass
    found = sorted(queue_dir.glob("queue-*.json"))
    return found[-1] if found else None
