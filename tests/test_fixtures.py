"""Source fixtures (spike S1) parse and keep no publisher text (CLAUDE.md: no abstracts).

The spike scripts in spikes/s1/ replace abstracts, descriptions and article bodies with a
REDACTED marker before saving. These tests guard that rule for every fixture, including
ones added or refreshed later by hand.
"""

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
REDACTED = "[REDACTED in fixture"

# Same lists as spikes/s1/common.py (copied: tests do not import throwaway spike code).
TEXT_KEYS = {"abstract", "abstracttext", "abstract_inverted_index", "description", "summary"}
TEXT_TAGS = ("AbstractText", "description", "content:encoded", "summary", "content", "abstract")

FILES = sorted(p for p in FIXTURES.rglob("*") if p.suffix in {".json", ".xml"})


def _id(path: Path) -> str:
    return str(path.relative_to(FIXTURES))


def _unredacted_json(value, where="$"):
    """Yield the paths of publisher-text keys whose value is not the REDACTED marker."""
    if isinstance(value, dict):
        for k, v in value.items():
            if k.lower() in TEXT_KEYS and v and not str(v).startswith(REDACTED):
                yield f"{where}.{k}"
            else:
                yield from _unredacted_json(v, f"{where}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            yield from _unredacted_json(v, f"{where}[{i}]")


def _unredacted_xml(text: str):
    """Yield the publisher-text elements whose content is not the REDACTED marker."""
    for tag in TEXT_TAGS:
        pattern = rf"<{re.escape(tag)}\b[^>]*(?<!/)>(.*?)</{re.escape(tag)}>"
        for m in re.finditer(pattern, text, flags=re.DOTALL):
            body = m.group(1).strip()
            if body and not body.startswith(REDACTED):
                yield f"<{tag}>{body[:60]}"


def test_there_are_fixtures():
    assert len(FILES) >= 30


@pytest.mark.parametrize("path", FILES, ids=_id)
def test_fixture_parses_and_is_redacted(path: Path):
    text = path.read_text("utf-8")
    if path.suffix == ".json":
        leaks = list(_unredacted_json(json.loads(text)))
    else:
        ET.fromstring(text.encode("utf-8"))  # well-formed XML
        leaks = list(_unredacted_xml(text))
    assert not leaks, f"publisher text kept in {_id(path)}: {leaks[:3]}"
