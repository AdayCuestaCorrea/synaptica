"""Calm palette of Neuro Atlas (spike S3, step 7.2; Sofía's request P5).

Copied from ``spikes/s3/build_assets.py`` (spike S3, Phase 0) for Neuro Atlas (Phase 2,
SCOPE v160).

The official colours of the atlases give hundreds of unrelated hues side by side. Here every
region takes the soft hue of its family (cortex, hippocampus, thalamus...), with a small change
of lightness between neighbours so that borders still show. Same family, same hue in both
atlases, so the rat and the human read alike; each atlas is coloured from its own hierarchy
only. The official colour stays in ``color``; this one goes in ``color_calm``. Both sides of a
region share a colour.
"""

from __future__ import annotations

import colorsys

# Family: (hue in degrees, saturation, lightness), all low-saturation pastels.
FAMILIES = {
    "cortex": (15, 0.45, 0.80),
    "cortex_gap": (15, 0.12, 0.86),  # Julich-Brain GapMaps: cortex not mapped yet
    "hippocampus": (265, 0.30, 0.77),
    "olfactory": (40, 0.45, 0.78),
    "amygdala": (340, 0.33, 0.76),
    "basal_ganglia": (200, 0.35, 0.77),
    "thalamus": (50, 0.55, 0.77),
    "hypothalamus": (90, 0.30, 0.75),
    "midbrain": (170, 0.28, 0.73),
    "hindbrain": (125, 0.20, 0.72),
    "white_matter": (35, 0.12, 0.90),
    "ventricles": (205, 0.50, 0.85),
    "other": (0, 0.0, 0.80),
}
# First match wins, over the ancestor names (lower case) from the root down to the region.
RULES = [
    ("cortex_gap", ("gapmap",)),
    ("hippocampus", ("hippocampal formation",)),
    ("olfactory", ("olfactory bulb",)),
    ("amygdala", ("amygdala", "non-laminated pallium")),
    ("basal_ganglia", ("basal ganglia", "basal forebrain", "subpallium")),
    ("hypothalamus", ("hypothalamus",)),
    ("thalamus", ("thalamus", "subthalamus", "diencephalon")),
    ("midbrain", ("mesencephalon",)),
    ("hindbrain", ("rhombencephalon", "metencephalon")),
    ("white_matter", ("white matter",)),
    ("ventricles", ("ventricular system",)),
    ("cortex", ("cerebral cortex",)),
]
# Human cortex: a slight hue shift per lobe, inside the cortex family.
LOBE_SHIFT = {
    "frontal lobe": -6,
    "parietal lobe": 8,
    "temporal lobe": -12,
    "occipital lobe": 16,
    "insula": 2,
    "limbic lobe": -18,
}
STEPS = (0.0, 0.05, -0.05, 0.025, -0.025)  # lightness steps between neighbours


def family(ancestors: list[str]) -> str:
    """The calm family of a region from its ancestor names (root first)."""
    names = [a.strip().lower() for a in ancestors]
    for fam, keys in RULES:
        if any(k in n for n in names for k in keys):
            return fam
    return "other"


def colours(members: list[tuple[str, list[str], object]]) -> dict[object, tuple[str, str]]:
    """members: (family, ancestors, key) per region. Returns key → (family, "#RRGGBB").

    Within a family, regions are taken in key order and step through STEPS, so the result
    depends only on the atlas data (idempotent).
    """
    out = {}
    seen: dict[str, int] = {}
    for fam, ancestors, key in sorted(members, key=lambda m: (m[0], str(m[2]))):
        h, s, li = FAMILIES[fam]
        if fam == "cortex":
            lower = [a.strip().lower() for a in ancestors]
            h += next((v for k, v in LOBE_SHIFT.items() if k in lower), 0)
        n = seen.get(fam, 0)
        seen[fam] = n + 1
        li = min(0.95, max(0.5, li + STEPS[n % len(STEPS)]))
        r, g, b = colorsys.hls_to_rgb((h % 360) / 360, li, s)
        out[key] = (fam, "#{:02X}{:02X}{:02X}".format(*(round(c * 255) for c in (r, g, b))))
    return out
