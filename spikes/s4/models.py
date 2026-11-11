"""S4 · Data model of Sofía's review queue and of her decisions (spike, decision D5).

* ``ReviewItem``: one thing waiting for her review (a text, a rat-human pair, the weekly
  Classics...). Its ``content_sha256`` binds an approval to the exact version she saw:
  if the draft changes, the hash changes and the approval no longer applies.
* ``Decision``: one answer of hers. Decisions are appended to ``review/decisions.jsonl``
  on the data branch and never rewritten; the current state is the last decision per
  item (step 5 of PLAN.md), so the history of every grade is kept.
* ``check_against``: the problems of a decision with respect to the current queue
  (unknown item, stale hash, picks outside the candidates). The model alone validates
  what does not need the queue.

``reviewed_by`` and ``reviewed_at`` are not typed by her: the intake (step 4) takes them
from the author and the creation date of the GitHub Issue.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ItemType(StrEnum):
    DISEASE = "disease"  # Neuro Diseases sheet: the only one that blocks publication
    ATLAS = "atlas"  # text of an atlas region
    SEARCH_TERMS = "search_terms"  # region -> PubMed search terms
    LAB = "lab"  # Neuro Lab technique
    GLOSSARY = "glossary"
    LEARN = "learn"
    NEWS = "news"  # optional spot-check of a published summary (ADR D4: spanish_natural)
    EQUIVALENCE = "equivalence"  # rat <-> human pair: grade and note
    CLASSICS = "classics"  # the weekly choice of Classics
    NEWS_TOPIC = "news_topic"  # a news category she can switch off


class Grade(StrEnum):
    CLEAR = "clear"  # clara
    PARTIAL = "partial"  # parcial
    DISPUTED = "disputed"  # discutida


class Action(StrEnum):
    APPROVE = "approve"
    EDIT = "edit"
    REJECT = "reject"
    KEEP = "keep"  # «lo mantengo»: her edit failed a check and she keeps it, with a reason
    SET_GRADE = "set_grade"
    PICK = "pick"
    ENABLE = "enable"
    DISABLE = "disable"
    PROPOSE = "propose"  # a new item (for now, a glossary term), so there is no hash


# ---- content of a queue item, one shape per kind ------------------------------------


class Source(Strict):
    id: str
    url: str
    label: str


class Sentence(Strict):
    text: str = Field(min_length=1)
    cites: list[str] = []  # Source ids; the citation check is the intake's (step 4)


class TextContent(Strict):
    kind: Literal["text"] = "text"
    es: list[Sentence] = Field(min_length=1)
    en: list[Sentence] = Field(min_length=1)  # never one language without the other
    sources: list[Source] = []

    @model_validator(mode="after")
    def _cites_exist(self) -> TextContent:
        known = {s.id for s in self.sources}
        missing = {c for s in self.es + self.en for c in s.cites} - known
        if missing:
            raise ValueError(f"sentences cite unknown sources: {sorted(missing)}")
        return self


class TermsContent(Strict):
    kind: Literal["terms"] = "terms"
    region: str
    terms: list[str] = Field(min_length=1)


class RatRegion(Strict):
    id: int
    acronym: str
    name: str


class HumanArea(Strict):
    area_id: str
    label: int
    name: str


class PairContent(Strict):
    kind: Literal["pair"] = "pair"
    rat: RatRegion  # Waxholm v4.01
    human: list[HumanArea] = Field(min_length=1)  # Julich-Brain v3.1


class Candidate(Strict):
    doi: str
    title: str
    year: int
    cited_by: int


class CandidatesContent(Strict):
    kind: Literal["candidates"] = "candidates"
    week: str = Field(pattern=r"^\d{4}-W\d{2}$")  # ISO week
    max_picks: int = Field(ge=1)
    candidates: list[Candidate] = Field(min_length=1)


class ToggleContent(Strict):
    kind: Literal["toggle"] = "toggle"
    label_es: str
    label_en: str


Content = Annotated[
    TextContent | TermsContent | PairContent | CandidatesContent | ToggleContent,
    Field(discriminator="kind"),
]

KIND_OF: dict[ItemType, str] = {
    ItemType.DISEASE: "text",
    ItemType.ATLAS: "text",
    ItemType.LAB: "text",
    ItemType.GLOSSARY: "text",
    ItemType.LEARN: "text",
    ItemType.NEWS: "text",
    ItemType.SEARCH_TERMS: "terms",
    ItemType.EQUIVALENCE: "pair",
    ItemType.CLASSICS: "candidates",
    ItemType.NEWS_TOPIC: "toggle",
}

ALLOWED: dict[str, set[Action]] = {
    "text": {Action.APPROVE, Action.EDIT, Action.REJECT, Action.KEEP},
    "terms": {Action.APPROVE, Action.EDIT},
    "pair": {Action.SET_GRADE},
    "candidates": {Action.PICK},
    "toggle": {Action.ENABLE, Action.DISABLE},
}
PROPOSABLE = {ItemType.GLOSSARY}


def canonical_sha256(value: object) -> str:
    """SHA-256 of a JSON value with sorted keys and no spaces (stable across runs)."""
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ReviewItem(Strict):
    item_type: ItemType
    item_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")
    title_es: str
    content: Content
    public: bool = True  # False: never on the public review page (Neuro Diseases)

    @model_validator(mode="after")
    def _consistent(self) -> ReviewItem:
        if self.content.kind != KIND_OF[self.item_type]:
            raise ValueError(f"{self.item_type} needs content of kind {KIND_OF[self.item_type]}")
        if self.item_type is ItemType.DISEASE and self.public:
            raise ValueError("Neuro Diseases drafts never go on the public review page")
        return self

    @property
    def key(self) -> tuple[str, str]:
        return (self.item_type.value, self.item_id)

    @property
    def blocking(self) -> bool:
        return self.item_type is ItemType.DISEASE

    @property
    def content_sha256(self) -> str:
        return canonical_sha256(
            {"item_type": self.item_type.value, "item_id": self.item_id,
             "content": self.content.model_dump(mode="json")}
        )  # fmt: skip


class Queue(Strict):
    generated_at: datetime
    items: list[ReviewItem]

    @field_validator("generated_at")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return _as_utc(v)

    @model_validator(mode="after")
    def _unique(self) -> Queue:
        keys = [i.key for i in self.items]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate items in the queue")
        return self

    def get(self, item_type: ItemType, item_id: str) -> ReviewItem | None:
        return next((i for i in self.items if i.key == (item_type.value, item_id)), None)


# ---- decisions --------------------------------------------------------------------


class Empty(Strict):
    pass


class EditText(Strict):
    # Free text per language; splitting it into sentences and citations is step 4.
    # At least one language: what to do with the other one is an open point of step 4.
    es: str | None = None
    en: str | None = None

    @model_validator(mode="after")
    def _one(self) -> EditText:
        if not (self.es or self.en):
            raise ValueError("an edit changes at least one language")
        return self


class EditTerms(Strict):
    terms: list[str] = Field(min_length=1)


class Keep(Strict):
    reason: str = Field(min_length=3)


class SetGrade(Strict):
    grade: Grade
    note_es: str | None = None  # shown on the site: its English version is step 4's


class Pick(Strict):
    dois: list[str] = Field(min_length=1)


class ProposeTerm(Strict):
    term: str = Field(min_length=1)
    meaning_es: str = Field(min_length=1)
    explanation_es: str | None = None


PAYLOADS: dict[Action, type[Strict]] = {
    Action.APPROVE: Empty,
    Action.REJECT: Empty,
    Action.EDIT: EditText,  # EditTerms for "terms" items, see Decision._payload
    Action.KEEP: Keep,
    Action.SET_GRADE: SetGrade,
    Action.PICK: Pick,
    Action.ENABLE: Empty,
    Action.DISABLE: Empty,
    Action.PROPOSE: ProposeTerm,
}

SHA256 = r"^[0-9a-f]{64}$"


class Decision(Strict):
    item_type: ItemType
    item_id: str
    content_sha256: str | None = Field(default=None, pattern=SHA256)
    action: Action
    payload: dict = {}
    note: str | None = Field(default=None, max_length=2000)  # public (it goes in the Issue)
    reviewed_by: str = Field(min_length=1)  # GitHub login of the Issue's author
    reviewed_at: datetime  # creation date of the Issue, UTC
    source: str = Field(pattern=r"^issue#\d+$")

    @field_validator("reviewed_at")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return _as_utc(v)

    @model_validator(mode="after")
    def _payload(self) -> Decision:
        if self.action is Action.PROPOSE:
            if self.item_type not in PROPOSABLE:
                raise ValueError(f"{self.item_type} items cannot be proposed")
            if self.content_sha256 is not None:
                raise ValueError("a proposal has no content hash: the item does not exist yet")
        else:
            kind = KIND_OF[self.item_type]
            if self.action not in ALLOWED[kind]:
                raise ValueError(f"{self.action} does not apply to {self.item_type} items")
            if self.content_sha256 is None:
                raise ValueError("a decision on an existing item needs its content hash")
        model = (
            EditTerms
            if (self.action is Action.EDIT and KIND_OF[self.item_type] == "terms")
            else PAYLOADS[self.action]
        )
        model.model_validate(self.payload)  # raises with the field that is wrong
        return self


def _as_utc(v: datetime) -> datetime:
    if v.tzinfo is None:
        raise ValueError("dates carry their time zone (CLAUDE.md: UTC, ISO 8601)")
    return v.astimezone(UTC)


def check_against(decision: Decision, queue: Queue) -> list[str]:
    """Problems of a decision with respect to the queue it answers (empty: it applies)."""
    if decision.action is Action.PROPOSE:
        return []
    item = queue.get(decision.item_type, decision.item_id)
    if item is None:
        return [f"unknown item {decision.item_type}/{decision.item_id}"]
    problems = []
    if decision.content_sha256 != item.content_sha256:
        problems.append("stale: the item changed after she reviewed it")
    if decision.action is Action.PICK and isinstance(item.content, CandidatesContent):
        dois = Pick.model_validate(decision.payload).dois
        offered = {c.doi for c in item.content.candidates}
        if extra := sorted(set(dois) - offered):
            problems.append(f"picks outside the candidates: {extra}")
        if len(set(dois)) > item.content.max_picks:
            problems.append(f"more than {item.content.max_picks} picks")
    return problems
