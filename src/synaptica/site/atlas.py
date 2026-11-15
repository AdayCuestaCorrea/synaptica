"""The Neuro Atlas page (Phase 2, SCOPE v161): region lists and credits from site/static/atlas/.

Reads the files written by ``syn atlas build`` (labels.json and licence.json of each atlas)
and nothing else: no warehouse, no network. Each atlas keeps its own rows and its own credit;
the human list shows the four layers side by side, each region tagged with the layer it comes
from, and no geometry is joined (CLAUDE.md, "Licencias").

The order of the regions is Sofía's to set (SCOPE §7, «Orden de las regiones»). Until she does,
the families of the calm palette go from the surface inwards, as she proposed, and the names
stay as in the atlases (English): their Spanish names are hers to review (study question 4).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# The brains of the page, each with its atlases (the first is the main one).
BRAINS = {"rat": ("waxholm",), "human": ("julich", "cerebra", "cit168", "icbm_wm")}
# Families of the calm palette (synaptica.atlas.palette), from the surface inwards.
SURFACE = ("cortex", "cortex_gap", "olfactory")
INTERIOR = ("hippocampus", "amygdala", "basal_ganglia", "thalamus", "hypothalamus",
            "midbrain", "hindbrain", "white_matter", "ventricles", "other")  # fmt: skip
FAMILIES = (*SURFACE, *INTERIOR)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text("utf-8"))


def regions(atlas_dir: Path, brain: str) -> list[dict[str, Any]]:
    """The families of one brain, from the surface inwards, each with its regions.

    One entry per region name (both sides together), sorted by name inside its family:
    ``{"family", "depth" ("surface" | "interior"), "regions": [{"name", "acronym", "atlas",
    "colour"}]}``. Families with no region are left out.
    """
    by_family: dict[str, dict[tuple[str, str], dict[str, Any]]] = {f: {} for f in FAMILIES}
    for atlas in BRAINS[brain]:
        for row in _load(atlas_dir / atlas / "labels.json")["rows"][1:]:
            fam = row.get("group") or "other"
            if fam not in by_family:
                raise ValueError(f"{atlas}: family {fam!r} has no place in the region list")
            # The viewer's key of the area, both sides (static/viewer/viewer.js, searchIndex).
            key = f"w{row['id']}" if atlas == "waxholm" else f"j{row['area_id']}"
            by_family[fam].setdefault((row["name"], atlas), {
                "name": row["name"], "acronym": row.get("acronym"), "atlas": atlas,
                "colour": row["color_calm"], "key": key,
            })  # fmt: skip
    return [
        {"family": fam, "depth": "surface" if fam in SURFACE else "interior",
         "regions": sorted(found.values(), key=lambda r: (r["name"].lower(), r["atlas"]))}
        for fam, found in by_family.items() if found
    ]  # fmt: skip


def credits(atlas_dir: Path, brain: str) -> list[dict[str, str]]:
    """The licence of every atlas of one brain, as written next to its data."""
    out = []
    for atlas in BRAINS[brain]:
        lic = _load(atlas_dir / atlas / "licence.json")
        keep = ("short", "licence", "licence_url", "source_url")
        out.append({"atlas": atlas} | {k: lic[k] for k in keep})
    return out
