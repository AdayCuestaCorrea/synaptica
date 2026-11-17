"""The Neuro Atlas page (Phase 2, SCOPE v161): region lists and credits from site/static/atlas/.

Reads the files written by ``syn atlas build`` (labels.json and licence.json of each atlas)
and nothing else: no warehouse, no network. Each atlas keeps its own rows and its own credit;
the human list shows the four layers side by side, each region tagged with the layer it comes
from, and no geometry is joined (CLAUDE.md, "Licencias").

The order of the regions is Sofía's to set (SCOPE §7, «Orden de las regiones»). Until she does,
the families of the calm palette go from the surface inwards, as she proposed, the regions of
the rat ↔ human pairs first in each family (v207), and the names
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


def regions(atlas_dir: Path, brain: str, first: set[str] = frozenset()) -> list[dict[str, Any]]:
    """The families of one brain, from the surface inwards, each with its regions.

    Provisional order (plan of 2026-11-17, option A, until Sofía answers row 10): inside a
    family, the regions with a counterpart in the other brain (viewer keys in ``first``)
    come first, then the rest, each part by name.

    One entry per region name (both sides together), sorted inside its family:
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
         "regions": sorted(found.values(),
                           key=lambda r: (r["key"] not in first, r["name"].lower(), r["atlas"]))}
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


# ---------------------------------------------------------------- region pages (step 5)
# Aday's option B (SCOPE v166): only the regions of the rat ↔ human pairs get a page for now,
# with what the data already hold (name, brain, family, atlas and licence, counterpart). The
# description, studies, diseases and techniques are gaps until they exist and Sofía reviews them.

BRAIN_OF = {"waxholm": "rat", "julich": "human", "cerebra": "human", "cit168": "human",
            "icbm_wm": "human"}  # fmt: skip


def slug(text: str) -> str:
    """ASCII, lower case, hyphens: «CA1 (Hippocampus)» → «ca1-hippocampus»."""
    import re
    import unicodedata

    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")


def _rat_family(rows: list[dict[str, Any]], node: int) -> str:
    """The family of a Waxholm node: the one most of its pieces belong to (ties: first)."""
    counts: dict[str, int] = {}
    for r in rows[1:]:
        if node in (r.get("path") or [r.get("id")]):
            fam = r.get("group") or "other"
            counts[fam] = counts.get(fam, 0) + int(r.get("voxels") or 1)
    return max(counts, key=lambda f: counts[f]) if counts else "other"


def region_pages(atlas_dir: Path) -> list[dict[str, Any]]:
    """One entry per region of the pairs, both sides: its page key, names, family, atlas and
    counterparts. Page keys carry the atlas (``waxholm-…``, ``julich-…``) so a rat and a human
    region of the same name never share one; a clash is refused."""
    pairs = _load(atlas_dir / "pairs.json")["pairs"]
    rat_rows = _load(atlas_dir / "waxholm" / "labels.json")["rows"]
    human_rows = {a: _load(atlas_dir / a / "labels.json")["rows"] for a in BRAINS["human"]}
    pages: dict[str, dict[str, Any]] = {}

    def add(entry: dict[str, Any]) -> dict[str, Any]:
        key = entry["page"]
        if key in pages:
            if pages[key]["key"] != entry["key"]:
                raise ValueError(f"two regions would share the page {key}")
            return pages[key]
        pages[key] = entry | {"pairs": []}
        return pages[key]

    for n, p in enumerate(pairs):
        w = p["waxholm"]
        rat = add({
            "brain": "rat", "atlas": "waxholm", "key": f"w{w['id']}",
            "page": f"waxholm-{slug(w['name'])}", "name": w["name"],
            "acronym": w.get("acronym"), "family": _rat_family(rat_rows, w["id"]),
        })  # fmt: skip
        humans = []
        for hr in p["human"]:
            row = next(r for r in human_rows[hr["atlas"]][1:] if r["area_id"] == hr["area_id"])
            humans.append(add({
                "brain": "human", "atlas": hr["atlas"], "key": f"j{hr['area_id']}",
                "page": f"{hr['atlas']}-{slug(hr['name'])}", "name": hr["name"],
                "acronym": None, "family": row.get("group") or "other",
            }))  # fmt: skip
        pair = {"index": n, "kind": p["kind"], "grade": p.get("grade"), "note": p.get("note")}
        rat["pairs"].append(pair | {"counterparts": [h["page"] for h in humans]})
        for h in humans:
            h["pairs"].append(pair | {"counterparts": [rat["page"]]})
    return list(pages.values())
