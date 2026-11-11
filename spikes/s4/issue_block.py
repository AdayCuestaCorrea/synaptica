"""S4 · The block of decisions that travels in a GitHub Issue (step 3 of PLAN.md).

The review page writes it (``template.html``, ``blockOf``) into the "Decisiones" field of
the Issue form ``.github/ISSUE_TEMPLATE/revision.yml``; the intake (step 4) reads it back
with ``decode``. Plain text, so Sofía can see what she sends::

    synaptica-review v1
    queue: 2026-11-11T06:00:00Z
    page: public
    part: 1/1
    {"item_type":"glossary","item_id":"gaba","content_sha256":"…","action":"approve",…}

One compact JSON object per decision line, with the fields of ``models.Decision`` except
the three that the intake fills in from the Issue itself (``reviewed_by``,
``reviewed_at``, ``source``): nothing typed in the page can claim who or when.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

MAGIC = "synaptica-review v1"
HEADER_KEYS = ("queue", "page", "part")
DECISION_KEYS = ("item_type", "item_id", "content_sha256", "action", "payload", "note")
# The form renders the field inside a code fence; a person may also paste the bare block.
FENCE = re.compile(r"```[a-z]*\n(.*?)\n```", re.DOTALL)


class BlockError(ValueError):
    pass


@dataclass(frozen=True)
class Block:
    queue: str  # generated_at of the queue the page was built from
    page: str  # public | private
    part: tuple[int, int]
    decisions: list[dict]


def encode(queue: str, page: str, decisions: list[dict], part: tuple[int, int] = (1, 1)) -> str:
    """Same text as the page's ``blockOf`` (the tests and the intake share this format)."""
    lines = [MAGIC, f"queue: {queue}", f"page: {page}", f"part: {part[0]}/{part[1]}"]
    for d in decisions:
        ordered = {k: d.get(k) for k in DECISION_KEYS}
        lines.append(json.dumps(ordered, ensure_ascii=False, separators=(",", ":")))
    return "\n".join(lines)


def _find(body: str) -> str:
    candidates = [m.group(1) for m in FENCE.finditer(body)] + [body]
    for text in candidates:
        text = text.replace("\r\n", "\n")
        start = text.find(MAGIC)
        if start != -1:
            return text[start:]
    raise BlockError("no SYNAPTICA review block in the Issue")


def decode(body: str) -> Block:
    """Read the block back from an Issue body; raises BlockError with the reason."""
    lines = [line.strip() for line in _find(body).split("\n")]
    lines = [line for line in lines if line]
    if lines[0] != MAGIC:
        raise BlockError(f"unknown format: {lines[0]!r}")
    header = {}
    for key, line in zip(HEADER_KEYS, lines[1:4], strict=False):
        name, _, value = line.partition(": ")
        if name != key or not value:
            raise BlockError(f"header line {key!r} missing or wrong: {line!r}")
        header[key] = value
    if len(header) != len(HEADER_KEYS):
        raise BlockError("incomplete header")
    m = re.fullmatch(r"(\d+)/(\d+)", header["part"])
    if not m or not 1 <= int(m.group(1)) <= int(m.group(2)):
        raise BlockError(f"wrong part: {header['part']!r}")
    decisions = []
    for n, line in enumerate(lines[4:], start=1):
        try:
            d = json.loads(line)
        except json.JSONDecodeError as e:
            raise BlockError(f"decision {n} is not valid JSON: {e.msg}") from None
        if not isinstance(d, dict) or set(d) - set(DECISION_KEYS):
            raise BlockError(f"decision {n} has unexpected fields")
        decisions.append(d)
    if not decisions:
        raise BlockError("the block has no decisions")
    return Block(header["queue"], header["page"], (int(m.group(1)), int(m.group(2))), decisions)
