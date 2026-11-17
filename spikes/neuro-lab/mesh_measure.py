"""Spike for Neuro Lab, B1 (SCOPE v201): which techniques of SCOPE §4 have their own MeSH
descriptor, and how many studies of the warehouse each one finds by MeSH (the descriptor
and everything under it) or by text in the title and keywords. Counts only, no text.

    uv run python -I spikes/neuro-lab/mesh_measure.py DATA/warehouse.duckdb

Network: NLM's MeSH SPARQL endpoint, through ``synaptica.atlas.studies.fetch``. No LLM.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from synaptica.atlas import studies
from synaptica.http import make_client

# Tree numbers of the descriptor chosen for each technique (looked up on 2026-11-17 by
# entry terms; see docs/fases/fase-2-neuro-lab.md). Empty: no descriptor of its own.
TREES = {
    "western_blot": ["E05.196.401.143"],
    "immunofluorescence": ["E01.370.225.500.607.512.240"],
    "confocal": ["E01.370.350.515.395"],
    "electrophysiology": ["E05.200.500.905"],  # Patch-Clamp Techniques
    "eeg": ["E01.370.376.300", "E01.370.376.150"],  # EEG, electrocorticography
    "fmri": ["E01.370.350.578.875"],  # Functional Neuroimaging (PET too)
    "viral_tracing": ["E01.370.225.500.620.670.570"],  # Tract-Tracing (any tracer)
    "optogenetics": ["E05.393.667"],
    "chemogenetics": ["E05.393.128"],
    "perfusion": [],
    "fiber_photometry": [],
}
TEXT = {
    "western_blot": r"western blot",
    "immunofluorescence": r"immunofluorescen",
    "confocal": r"confocal",
    "electrophysiology": (
        r"electrophysiolog|patch[- ]clamp|whole[- ]cell record|single[- ]unit"
        r"|extracellular record"
    ),
    "eeg": r"\bEEG\b|electroencephalogra",
    "fmri": r"\bfMRI\b|functional magnetic resonance|functional MRI",
    "viral_tracing": r"\b(viral|virus|AAV|rabies)\b.{0,40}trac|tract[- ]tracing|monosynaptic trac",
    "optogenetics": r"optogenet|channelrhodopsin|\bChR2\b|halorhodopsin|archaerhodopsin",
    "chemogenetics": r"chemogenet|DREADD|clozapine[- ]N[- ]oxide",
    "perfusion": r"transcardial(ly)? perfus|perfusion[- ]fix",
    "fiber_photometry": r"fib(er|re)[- ]photometry",
}
COUNTS = ("mesh", "text", "both", "text_no_mesh_record", "text_only_with_mesh")


def main(warehouse: Path) -> dict:
    uis, names = {}, {}
    with make_client() as client:
        for tech, trees in TREES.items():
            rows = [r for tree in trees for r in studies.fetch(client, tree)]
            uis[tech] = {r["ui"] for r in rows}
            names[tech] = {r["name"].lower() for r in rows}
    out = {t: dict.fromkeys(COUNTS, 0) | {"descriptors": len(uis[t])} for t in TREES}
    total = with_mesh = 0
    for row, ui, keywords, mesh_names in studies._rows(warehouse, ("study_id", "title")):
        total += 1
        has = bool(ui or mesh_names)
        with_mesh += has
        text = row["title"] + " " + " ".join(keywords)
        lowered = {n.lower() for n in mesh_names}
        for tech, r in out.items():
            by_mesh = bool(set(ui) & uis[tech] or lowered & names[tech])
            by_text = bool(re.search(TEXT[tech], text, re.I))
            r["mesh"] += by_mesh
            r["text"] += by_text
            r["both"] += by_mesh and by_text
            r["text_no_mesh_record"] += by_text and not has
            r["text_only_with_mesh"] += by_text and has and not by_mesh
    return {"studies": total, "with_mesh": with_mesh, "techniques": out}


if __name__ == "__main__":
    print(json.dumps(main(Path(sys.argv[1])), indent=1))
