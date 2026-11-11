"""S4 · The queue for the test with Sofía (step 6 of PLAN.md): the fixture queue plus a
little more of each kind, so the session feels like a real day.

Everything comes from the repository, as in ``make_fixtures.py``: two more S5 summaries
(the systematic review where she asked for caution with «podía predecir», and the
adolescents study), and four more terms of the glossary table in ``docs/propuesta.md``
(English translated from it). The Neuro Diseases sheet is still a marked placeholder: the
test is about the flow, not about health content. Run from the repo root:

    uv run --group spike-s4 python spikes/s4/prueba/make_queue.py
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent))

from make_fixtures import PROPOSAL, items, news_item  # noqa: E402
from models import ItemType, Queue, ReviewItem, Sentence, TextContent  # noqa: E402

OUT = HERE / "queue.json"
GENERATED_AT = datetime(2026, 11, 11, 6, 0, tzinfo=UTC)

MORE_NEWS = [
    ("42997793", "Resumen de S5: revisión sistemática sobre depresión mayor"),
    ("42997796", "Resumen de S5: 102 adolescentes de 10 a 17 años"),
]
MORE_GLOSSARY = [  # docs/propuesta.md, «Neuro Glossary: primeros términos»
    ("vta", "VTA",
     "VTA (área tegmental ventral): región del mesencéfalo con neuronas dopaminérgicas, "
     "clave en recompensa y adicción.",
     "VTA (ventral tegmental area): a midbrain region with dopaminergic neurons, key in "
     "reward and addiction."),
    ("nac", "NAc",
     "NAc (núcleo accumbens): zona del estriado ventral, central en el circuito de recompensa.",
     "NAc (nucleus accumbens): part of the ventral striatum, central to the reward circuit."),
    ("bold", "BOLD",
     "BOLD (blood-oxygen-level dependent): señal de la fMRI que depende del oxígeno en la "
     "sangre.",
     "BOLD (blood-oxygen-level dependent): the fMRI signal that depends on the oxygen in "
     "the blood."),
    ("chr2", "ChR2",
     "ChR2 (canalrodopsina-2): proteína sensible a la luz con la que se activan neuronas en "
     "optogenética.",
     "ChR2 (channelrhodopsin-2): a light-sensitive protein used to activate neurons in "
     "optogenetics."),
]  # fmt: skip


def test_queue() -> Queue:
    out = items()
    out += [news_item(pmid, title) for pmid, title in MORE_NEWS]
    for item_id, term, es, en in MORE_GLOSSARY:
        out.append(ReviewItem(
            item_type=ItemType.GLOSSARY, item_id=item_id, title_es=term,
            content=TextContent(es=[Sentence(text=es, cites=["propuesta"])],
                                en=[Sentence(text=en, cites=["propuesta"])],
                                sources=[PROPOSAL]),
        ))  # fmt: skip
    return Queue(generated_at=GENERATED_AT, items=out)


def main() -> None:
    queue = test_queue()
    OUT.write_text(
        json.dumps(queue.model_dump(mode="json"), ensure_ascii=False, indent=1) + "\n", "utf-8"
    )
    print(f"{len(queue.items)} items -> {OUT}")


if __name__ == "__main__":
    main()
