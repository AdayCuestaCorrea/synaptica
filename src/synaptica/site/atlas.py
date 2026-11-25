"""The Neuro Atlas page (Phase 2, SCOPE v161): region lists and credits from site/static/atlas/.

Reads the files written by ``syn atlas build`` (labels.json and licence.json of each atlas)
and nothing else: no warehouse, no network. Each atlas keeps its own rows and its own credit;
the human list shows the four layers side by side, each region tagged with the layer it comes
from, and no geometry is joined (CLAUDE.md, "Licencias").

The order of the regions is Sofía's to set (SCOPE §7, «Orden de las regiones»). Her answer
(sheet row 10, 2026-11-24; v237): start with the basal ganglia, the zona incerta, the
substantia nigra, the hippocampus and the cerebellum. Their families come first, in her
order, under «To start with», with her regions at the top of each; the other families go
from the surface inwards, the regions of the rat ↔ human pairs first in each family (v207).
The names stay as in the atlases (English); for Spanish she chose Wikipedia (row 13).
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
# Her regions to start with, in her order: the Waxholm ids whose subtree is the region (rat)
# and the names of its areas in the human layers (as in each labels.json).
HERS = (
    ({197, 1028}, {"Caudate", "Putamen", "Pallidum"}),  # basal ganglia
    ({1082}, {"ZI (Thalamus, zona incerta)"}),
    ({1098}, {"SNC (Midbrain, Substantia Nigra pars compacta)",
              "SNR (Midbrain, Substantia Nigra pars reticulata)"}),
    ({1021}, {"CA1 (Hippocampus)", "CA2 (Hippocampus)", "CA3 (Hippocampus)",
              "DG (Hippocampus)", "Subc (Hippocampus, Subicular complex)"}),
    ({1047}, {"Cerebellum Gray Matter", "Cerebellum White Matter", "Vermal lobules I-V",
              "Vermal lobules VI-VII", "Vermal lobules VIII-X"}),
)  # fmt: skip


def her_rank(row: dict[str, Any], atlas: str) -> int | None:
    """Place of the region in her list (0 = the basal ganglia), None if not one of hers."""
    for n, (rat, human) in enumerate(HERS):
        if (set(row.get("path") or ()) & rat) if atlas == "waxholm" else row["name"] in human:
            return n
    return None


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text("utf-8"))


def regions(atlas_dir: Path, brain: str, first: set[str] = frozenset()) -> list[dict[str, Any]]:
    """The families of one brain: first those of her regions (``depth: "start"``), in her
    order; then the rest from the surface inwards. Inside a family, her regions first (in her
    order), then those with a counterpart in the other brain (viewer keys in ``first``,
    v207), then the rest, each part by name.

    One entry per region name (both sides together), sorted inside its family:
    ``{"family", "depth" ("start" | "surface" | "interior"), "regions": [{"name", "acronym",
    "atlas", "colour", "key", "hers"}]}``. Families with no region are left out.
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
                "colour": row["color_calm"], "key": key, "hers": her_rank(row, atlas),
            })  # fmt: skip
    last = len(HERS)

    def order(r: dict[str, Any]) -> tuple:
        rank = last if r["hers"] is None else r["hers"]
        return (rank, r["key"] not in first, r["name"].lower(), r["atlas"])

    out = []
    for fam, found in by_family.items():
        if not found:
            continue
        regs = sorted(found.values(), key=order)
        start = regs[0]["hers"] is not None
        depth = "start" if start else "surface" if fam in SURFACE else "interior"
        out.append({"family": fam, "depth": depth, "regions": regs})
    starts = sorted((f for f in out if f["depth"] == "start"),
                    key=lambda f: f["regions"][0]["hers"])  # fmt: skip
    return starts + [f for f in out if f["depth"] != "start"]


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
