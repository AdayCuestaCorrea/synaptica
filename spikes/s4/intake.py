"""S4 · Intake of Sofía's review Issues (step 4 of PLAN.md).

The workflow ``review-intake.yml`` (draft in this folder, not active) runs it on every
``issues: opened`` event. It never trusts what the Issue says about who or when:

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
the same Issue adds nothing. Run from the repo root:

    uv run --group spike-s4 python spikes/s4/intake.py --event event.json \\
        --queue queue.json --data-dir data/review --reviewer LOGIN --reply reply.md
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.path.insert(1, str(HERE.parent / "s5"))  # the S5 checks (copied from Paleo Atlas)

import checks  # noqa: E402
from issue_block import BlockError, decode  # noqa: E402
from models import Action, Decision, Queue, ReviewItem, TextContent, check_against  # noqa: E402
from pydantic import ValidationError  # noqa: E402

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
        for name in sorted(checks.names(text)):
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


def process(
    event: dict,
    queue: Queue,
    reviewer: str,
    *,
    done: set[str] = frozenset(),
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


def write(out: Outcome, data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    with (data_dir / "decisions.jsonl").open("a", encoding="utf-8") as f:
        for d in out.applied:
            f.write(json.dumps(d.model_dump(mode="json"), ensure_ascii=False) + "\n")
    with (data_dir / "held.jsonl").open("a", encoding="utf-8") as f:
        for h in out.held:
            row = {"decision": h.decision.model_dump(mode="json"), "warnings": h.warnings}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--event", type=Path, required=True)
    ap.add_argument("--queue", type=Path, required=True)
    ap.add_argument("--data-dir", type=Path, required=True)
    ap.add_argument("--reviewer", required=True)
    ap.add_argument("--reply", type=Path, required=True)
    args = ap.parse_args()
    event = json.loads(args.event.read_text("utf-8"))
    queue = Queue.model_validate_json(args.queue.read_text("utf-8"))
    out = process(event, queue, args.reviewer, done=_done_sources(args.data_dir))
    if out.status == "processed":
        write(out, args.data_dir)
    titles = {f"{i.item_type}/{i.item_id}": i.title_es for i in queue.items}
    if out.status in ("processed", "refused"):
        args.reply.write_text(reply(out, titles) + "\n", encoding="utf-8")
    print(json.dumps({"status": out.status, "applied": len(out.applied), "held": len(out.held),
                      "refused": len(out.refused)}))  # fmt: skip


if __name__ == "__main__":
    main()
