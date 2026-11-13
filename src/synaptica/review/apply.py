"""From Sofía's decision log to the current state of every item.

Moved from the spike ``spikes/s4/apply.py`` (plan, step R; ADR 0005).

The log (``decisions.jsonl`` and ``held.jsonl``) is never rewritten; this module reads it
against today's queue of drafts and answers three questions for the pipeline:

* **What is each item's state?** ``state`` walks the item's events in time order. An
  event counts only if it names the hash of the version on the table: today's draft, or
  the held edit that went back to her queue. When a draft changes, its old decisions
  stop counting and the item is pending again; this is what keeps a Neuro Diseases sheet
  from being published with an approval of another text.
* **Can it be published?** ``publishable``: a Neuro Diseases sheet only with her approval
  (or her edit) of the current draft; anything she rejected, never; a text whose English
  is still to be rewritten from her Spanish, not yet (CLAUDE.md: no page in one language
  only). The rest is published while it waits, as SCOPE §9 says: only Neuro Diseases
  blocks.
* **What goes back to her queue?** ``next_queue``: what has no decision for its current
  version, and her held edits, shown with her text and the warnings.

Grades keep their whole history (who, when, which grade, which note), even the grades
of an older version of the pair.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from synaptica.review.intake import align, sentences
from synaptica.review.models import (
    Action,
    Decision,
    ItemType,
    Queue,
    ReviewItem,
    Sentence,
    TextContent,
)


@dataclass(frozen=True)
class Event:
    decision: Decision
    warnings: tuple[str, ...] = ()  # not empty: an edit held by the intake

    @property
    def held(self) -> bool:
        return bool(self.warnings)


@dataclass
class GradeEntry:
    grade: str
    note_es: str | None
    reviewed_by: str
    reviewed_at: datetime
    current_version: bool  # set on the pair as it is today


@dataclass
class State:
    item: ReviewItem
    status: str = "pending"  # pending | approved | edited | rejected | held | decided
    text: TextContent | None = None  # what is published for a text item, when it changed
    awaiting_en: bool = False  # she edited the Spanish only: the English is to be rewritten
    kept_reason: str | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    held: Event | None = None
    grade: str | None = None
    grade_note_es: str | None = None
    grades: list[GradeEntry] = field(default_factory=list)
    picks: list[str] = field(default_factory=list)
    enabled: bool = True  # a news topic is shown until she hides it
    terms: list[str] | None = None


# ---- reading the log -----------------------------------------------------------------


def read_log(data_dir: Path) -> list[Event]:
    events = []
    for name in ("decisions.jsonl", "held.jsonl"):
        path = data_dir / name
        if not path.exists():
            continue
        for line in path.read_text("utf-8").splitlines():
            row = json.loads(line)
            if "decision" in row:
                events.append(Event(Decision.model_validate(row["decision"]),
                                    tuple(row["warnings"])))  # fmt: skip
            else:
                events.append(Event(Decision.model_validate(row)))
    # Time order; on a tie, the Issue number, then the order in the file (stable sort).
    return sorted(events, key=lambda e: (e.decision.reviewed_at, _issue(e.decision.source)))


def _issue(source: str) -> int:
    return int(source.removeprefix("issue#"))


# ---- her text, as content ------------------------------------------------------------


def edited_text(base: TextContent, payload: dict) -> TextContent:
    """Her version as content: each sentence keeps the citations of the reviewed sentence
    it corrects (``intake.align``, the same rule as the checks); a sentence she added cites
    nothing. A language she did not touch stays as it was."""

    def lang(name: str) -> list[Sentence]:
        old = getattr(base, name)
        if not payload.get(name):
            return list(old)
        mine = sentences(payload[name])
        matched = align([o.text for o in old], mine)
        return [Sentence(text=s, cites=old[i].cites if i is not None else [])
                for s, i in zip(mine, matched, strict=True)]  # fmt: skip

    return TextContent(es=lang("es"), en=lang("en"), sources=base.sources)


def requeued(item: ReviewItem, event: Event) -> ReviewItem:
    """A held edit, back in her queue: her text, the warnings and the draft it corrects."""
    assert isinstance(item.content, TextContent)
    base = item.base or item.content
    return item.model_copy(update={
        "content": edited_text(base, event.decision.payload),
        "warnings": list(event.warnings),
        "base": base,
    })  # fmt: skip


# ---- state ---------------------------------------------------------------------------


def state(item: ReviewItem, events: list[Event]) -> State:
    st = State(item)
    mine = [e for e in events if (e.decision.item_type, e.decision.item_id) == item.key]
    on_table = {item.content_sha256}
    for e in mine:
        d = e.decision
        if d.action is Action.SET_GRADE:  # history of every grade, of any version
            st.grades.append(GradeEntry(d.payload["grade"], d.payload.get("note_es"),
                                        d.reviewed_by, d.reviewed_at,
                                        d.content_sha256 == item.content_sha256))  # fmt: skip
        if d.content_sha256 not in on_table:
            continue  # a decision on another version of the item
        st.reviewed_by, st.reviewed_at = d.reviewed_by, d.reviewed_at
        if e.held:
            st.status, st.held = "held", e
            on_table = {item.content_sha256, requeued(item, e).content_sha256}
            continue
        held, st.held = st.held, None  # anything but a new held edit settles it
        on_table = {item.content_sha256}
        if d.action is Action.KEEP and (
            held is None or d.content_sha256 != requeued(item, held).content_sha256
        ):
            continue  # «lo mantengo» answers the held edit on the table, nothing else
        match d.action:
            case Action.APPROVE:
                if st.item.content.kind == "terms":
                    st.status, st.terms = "decided", None
                else:
                    st.status, st.text, st.awaiting_en = "approved", None, False
            case Action.REJECT:
                st.status, st.text = "rejected", None
            case Action.EDIT if item.content.kind == "terms":
                st.status, st.terms = "decided", d.payload["terms"]
            case Action.EDIT:
                st.status, st.text = "edited", edited_text(item.content, d.payload)
                st.awaiting_en, st.kept_reason = not d.payload.get("en"), None
            case Action.KEEP:
                st.status, st.text = "edited", edited_text(item.content, held.decision.payload)
                st.awaiting_en = not held.decision.payload.get("en")
                st.kept_reason = d.payload["reason"]
            case Action.SET_GRADE:
                st.status = "decided"
                st.grade, st.grade_note_es = d.payload["grade"], d.payload.get("note_es")
            case Action.PICK:
                st.status, st.picks = "decided", list(d.payload["dois"])
            case Action.ENABLE | Action.DISABLE:
                st.status, st.enabled = "decided", d.action is Action.ENABLE
    if st.status == "pending":
        st.reviewed_by = st.reviewed_at = None
    return st


def states(queue: Queue, events: list[Event]) -> dict[tuple[str, str], State]:
    return {i.key: state(i, events) for i in queue.items}


def publishable(st: State) -> bool:
    if st.status == "rejected" or st.awaiting_en:
        return False
    if st.item.item_type is ItemType.DISEASE:
        return st.status in ("approved", "edited") and st.reviewed_by is not None
    return True


def next_queue(queue: Queue, sts: dict[tuple[str, str], State]) -> Queue:
    """Tomorrow's queue: what waits for her, with her held edits in place of the draft."""
    items = []
    for item in queue.items:
        st = sts[item.key]
        if st.status == "held":
            items.append(requeued(item, st.held))
        elif st.status == "pending":
            items.append(item)
    return queue.model_copy(update={"items": items})


def proposals(events: list[Event]) -> list[Decision]:
    """New glossary terms she proposed, for the drafting step (Phase 2)."""
    return [e.decision for e in events if e.decision.action is Action.PROPOSE]
