"""S4 · Build the example review queue and decisions in ``tests/fixtures/review/``.

Everything comes from material already in the repository, so nothing is made up:

* news: one S5 summary (Qwen 27B on Groq, PMID 42971231, the one the judge and Sofía
  both flagged as overstating safety);
* glossary: two entries of the glossary table in ``docs/propuesta.md`` (draft, to review;
  the English text is a translation of that table);
* equivalence: the three test pairs of ``spikes/s3/site/data/equivalencias.json`` (read
  only), without their placeholder grade;
* Classics: the five most cited works of the OpenAlex fixture (metadata only);
* news topics: the four example filters of ``docs/propuesta.md``;
* search terms: the region's own names in the atlas, nothing else;
* disease: a placeholder marked as test text. No health content is invented.

The decisions use the placeholder login ``sofia-test``. Run from the repo root:

    uv run --group spike-s4 python spikes/s4/make_fixtures.py
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from models import (  # noqa: E402
    Candidate,
    CandidatesContent,
    Decision,
    HumanArea,
    ItemType,
    PairContent,
    Queue,
    RatRegion,
    ReviewItem,
    Sentence,
    Source,
    TermsContent,
    TextContent,
    ToggleContent,
)

OUT = ROOT / "tests" / "fixtures" / "review"
S5_RUN = HERE.parent / "s5" / "results" / "run_groq-qwen-qwen3.8-27b-groq-openai-gpt-oss-120b.json"
PAIRS = HERE.parent / "s3" / "site" / "data" / "equivalencias.json"
OPENALEX = ROOT / "tests" / "fixtures" / "openalex" / "works_most_cited_2016.json"
GENERATED_AT = datetime(2026, 11, 11, 6, 0, tzinfo=UTC)  # fixed: the fixture is stable

PROPOSAL = Source(id="propuesta", url="docs/propuesta.md", label="Propuesta, glosario (borrador)")
GLOSSARY = [  # docs/propuesta.md, «Neuro Glossary: primeros términos»
    ("gaba", "GABA",
     "GABA (ácido gamma-aminobutírico): principal neurotransmisor inhibidor del cerebro.",
     "GABA (gamma-aminobutyric acid): the main inhibitory neurotransmitter of the brain."),
    ("snr", "SNr",
     "SNr (sustancia negra pars reticulata): parte de la sustancia negra, en los ganglios "
     "basales, que envía señales inhibidoras a otras zonas.",
     "SNr (substantia nigra pars reticulata): part of the substantia nigra, in the basal "
     "ganglia, that sends inhibitory signals to other areas."),
]  # fmt: skip
TOPICS = [  # docs/propuesta.md, Neuro News filters
    ("healthy-brain", "Cerebro sano", "Healthy brain"),
    ("diseases", "Enfermedades", "Diseases"),
    ("clinical-trials", "Ensayos clínicos", "Clinical trials"),
    ("new-techniques", "Técnicas nuevas", "New techniques"),
]
PLACEHOLDER = "[Texto de prueba del spike S4: no es contenido de salud.]"
PLACEHOLDER_EN = "[S4 spike test text: this is not health content.]"


def news_item() -> ReviewItem:
    pmid = "42971231"
    row = next(a for a in json.loads(S5_RUN.read_text())["articles"] if a["pmid"] == pmid)
    src = Source(id=f"pubmed-{pmid}", url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                 label=f"PubMed {pmid}")  # fmt: skip
    return ReviewItem(
        item_type=ItemType.NEWS,
        item_id=f"pubmed-{pmid}",
        title_es="Resumen de S5: dolutegravir y defectos del tubo neural",
        content=TextContent(
            es=[Sentence(text=t, cites=[src.id]) for t in row["es"]],
            en=[Sentence(text=t, cites=[src.id]) for t in row["en"]],
            sources=[src],
        ),
    )


def items() -> list[ReviewItem]:
    out = [
        ReviewItem(
            item_type=ItemType.DISEASE,
            item_id="test-placeholder",
            title_es="Ficha de prueba (no es una enfermedad real)",
            content=TextContent(
                es=[Sentence(text=PLACEHOLDER)], en=[Sentence(text=PLACEHOLDER_EN)]
            ),
            public=False,
        ),
        news_item(),
    ]
    for item_id, term, es, en in GLOSSARY:
        out.append(ReviewItem(
            item_type=ItemType.GLOSSARY, item_id=item_id, title_es=term,
            content=TextContent(es=[Sentence(text=es, cites=["propuesta"])],
                                en=[Sentence(text=en, cites=["propuesta"])],
                                sources=[PROPOSAL]),
        ))  # fmt: skip
    for pair in json.loads(PAIRS.read_text())["pairs"]:
        rat = RatRegion(**pair["waxholm"])
        out.append(ReviewItem(
            item_type=ItemType.EQUIVALENCE, item_id=f"waxholm-{rat.id}",
            title_es=f"{rat.acronym} (rata) ↔ Julich-Brain",
            content=PairContent(rat=rat, human=[HumanArea(**h) for h in pair["julich"]]),
        ))  # fmt: skip
        if pair["kind"] == "internal":
            out.append(ReviewItem(
                item_type=ItemType.SEARCH_TERMS, item_id=f"waxholm-{rat.id}",
                title_es=f"Búsqueda en PubMed: {rat.name}",
                content=TermsContent(region=f"waxholm-{rat.id}", terms=[rat.name, rat.acronym]),
            ))  # fmt: skip
    works = sorted(json.loads(OPENALEX.read_text())["results"], key=lambda w: -w["cited_by_count"])
    out.append(ReviewItem(
        item_type=ItemType.CLASSICS, item_id="2026-w46", title_es="Clásicos de la semana 46",
        content=CandidatesContent(week="2026-W46", max_picks=2, candidates=[
            Candidate(doi=w["doi"].removeprefix("https://doi.org/"), title=w["title"],
                      year=w["publication_year"], cited_by=w["cited_by_count"])
            for w in works[:5]
        ]),
    ))  # fmt: skip
    for item_id, es, en in TOPICS:
        out.append(ReviewItem(
            item_type=ItemType.NEWS_TOPIC, item_id=item_id, title_es=f"Tema: {es}",
            content=ToggleContent(label_es=es, label_en=en),
        ))  # fmt: skip
    return out


def decisions(queue: Queue) -> list[Decision]:
    """One valid example of each action, as the intake would write them."""

    def d(item_type: ItemType, item_id: str, action: str, n: int, **kw) -> Decision:
        item = queue.get(item_type, item_id)
        return Decision(
            item_type=item_type, item_id=item_id,
            content_sha256=item.content_sha256 if item else None, action=action,
            reviewed_by="sofia-test", reviewed_at=datetime(2026, 11, 12, 19, n, tzinfo=UTC),
            source=f"issue#{n}", **kw,
        )  # fmt: skip

    return [
        d(ItemType.GLOSSARY, "gaba", "approve", 1),
        d(ItemType.NEWS, "pubmed-42971231", "edit", 2,
          payload={"es": "Estos resultados no muestran más defectos del tubo neural con "
                         "dolutegravir que con otros fármacos."},
          note="Exagera la seguridad."),
        d(ItemType.GLOSSARY, "snr", "reject", 3),
        d(ItemType.EQUIVALENCE, "waxholm-1021", "set_grade", 4,
          payload={"grade": "partial", "note_es": "Nota de prueba del spike S4."}),
        d(ItemType.EQUIVALENCE, "waxholm-1021", "set_grade", 5, payload={"grade": "clear"}),
        d(ItemType.CLASSICS, "2026-w46", "pick", 6,
          payload={"dois": [queue.get(ItemType.CLASSICS, "2026-w46").content.candidates[0].doi]}),
        d(ItemType.NEWS_TOPIC, "clinical-trials", "disable", 7),
        d(ItemType.SEARCH_TERMS, "waxholm-1021", "edit", 8,
          payload={"terms": ["hippocampal formation", "hippocampus"]}),
        d(ItemType.GLOSSARY, "ltp", "propose", 9,
          payload={"term": "LTP", "meaning_es": "Potenciación a largo plazo"}),
        d(ItemType.NEWS, "pubmed-42971231", "keep", 10,
          payload={"reason": "Prueba del spike S4: mantengo mi versión."}),
    ]  # fmt: skip


def main() -> None:
    queue = Queue(generated_at=GENERATED_AT, items=items())
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "queue.json").write_text(
        json.dumps(queue.model_dump(mode="json"), ensure_ascii=False, indent=1) + "\n", "utf-8"
    )
    lines = [json.dumps(x.model_dump(mode="json"), ensure_ascii=False) for x in decisions(queue)]
    (OUT / "decisions.jsonl").write_text("\n".join(lines) + "\n", "utf-8")
    print(f"{len(queue.items)} items, {len(lines)} decisions -> {OUT}")


if __name__ == "__main__":
    main()
