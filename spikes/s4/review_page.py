"""S4 · Sofía's review page, generated from the review queue (step 2 of PLAN.md).

Generalises the S5 page (``spikes/s5/review_page.py``, which she used without terminal
or git) from one kind of question to every kind of decision in ``models.py``. Two
variants, never mixed:

* ``public``: every item except Neuro Diseases. In the pipeline it would go on Pages,
  under a path nothing links to and with ``noindex``; it is still public.
* ``private``: only the Neuro Diseases drafts, which never go on a public page (decision
  of Aday, 2026-11-11). Aday sends her the file and she opens it in her browser.

Each item carries its ``content_sha256``, so her answer names the exact version she saw.
Sending opens the Issue form ``.github/ISSUE_TEMPLATE/revision.yml`` already
filled in (``issue_block.py``, step 3). Run from the repo root:

    uv run --group spike-s4 python spikes/s4/review_page.py [queue.json]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from models import ItemType, Queue, ReviewItem  # noqa: E402

TEMPLATE = HERE / "review" / "template.html"
DEFAULT_QUEUE = HERE.parents[1] / "tests" / "fixtures" / "review" / "queue.json"
OUT = {"public": HERE / "review" / "revision.html",
       "private": HERE / "review" / "revision-privada.html"}  # fmt: skip
MARKER = "/*DATA*/{}"
ISSUE_NEW_URL = "https://github.com/AdayCuestaCorrea/synaptica/issues/new"
# Longest Issue URL the page builds; above it, a decision goes in its own part or is pasted.
# Measured in step 3 (spikes/s4/results/README.md): without a session GitHub redirects to
# the login with the whole URL and fails above ~6950 characters (500, then 414).
MAX_URL = 6000
PROPOSAL = HERE.parents[1] / "docs" / "propuesta.md"


def glossary_terms(queue: Queue) -> list[str]:
    """Terms already in the glossary: the sample table of docs/propuesta.md and those in
    the queue. Shown where she proposes new ones (in round 1 she proposed EEG, AAV, GFAP
    and LTP, which were there already: the page never listed them)."""
    text = PROPOSAL.read_text("utf-8")
    block = text.split("## Neuro Glossary: primeros términos", 1)[1].split("\n## ", 1)[0]
    terms = set(re.findall(r"^\| (?!Término|---)(.+?) \|", block, re.M))
    terms |= {i.content.es[0].text.split(" (")[0].split(":")[0]
              for i in queue.items if i.item_type is ItemType.GLOSSARY}  # fmt: skip
    return sorted(terms, key=str.lower)


# Her queue, in order of priority: what blocks publication, what expires (the week's
# Classics), what unlocks a feature (rat-human grades), the texts, and last the optional
# spot-check of summaries that are already published.
ORDER = [
    ItemType.DISEASE, ItemType.CLASSICS, ItemType.EQUIVALENCE, ItemType.ATLAS,
    ItemType.SEARCH_TERMS, ItemType.LAB, ItemType.GLOSSARY, ItemType.LEARN,
    ItemType.NEWS_TOPIC, ItemType.NEWS,
]  # fmt: skip


def page_items(queue: Queue, variant: str) -> list[ReviewItem]:
    if variant not in OUT:
        raise ValueError(f"unknown variant {variant!r}")
    want_public = variant == "public"
    chosen = [i for i in queue.items if i.public == want_public]
    return sorted(chosen, key=lambda i: (ORDER.index(i.item_type), i.item_id))


def page_data(queue: Queue, variant: str, label: str = "") -> dict:
    return {
        "variant": variant,
        "label": label,  # the round («ronda-3»): in the header, the file name and the store
        "generated_at": queue.generated_at.isoformat().replace("+00:00", "Z"),
        "propose": variant == "public",  # new glossary terms: not health content
        "glossary_terms": glossary_terms(queue) if variant == "public" else [],
        "issue_new_url": ISSUE_NEW_URL,
        "max_url": MAX_URL,
        "items": [
            i.model_dump(mode="json") | {"content_sha256": i.content_sha256, "blocking": i.blocking}
            for i in page_items(queue, variant)
        ],
    }


def embed(data: dict) -> str:
    """JSON safe inside a <script>: no '</script>' or '<!--' can close or open anything."""
    text = json.dumps(data, ensure_ascii=False)
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def render(queue: Queue, variant: str, label: str = "") -> str:
    template = TEMPLATE.read_text("utf-8")
    if template.count(MARKER) != 1:
        raise ValueError("the template must have exactly one data marker")
    return template.replace(MARKER, embed(page_data(queue, variant, label)))


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_QUEUE
    queue = Queue.model_validate_json(path.read_text("utf-8"))
    for variant, out in OUT.items():
        out.write_text(render(queue, variant), encoding="utf-8")
        print(f"{variant}: {len(page_items(queue, variant))} items -> {out}")


if __name__ == "__main__":
    main()
