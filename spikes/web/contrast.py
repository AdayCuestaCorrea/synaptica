"""WCAG contrast of every text/background pair of the chosen style, N «Noche», light and dark.
AA for normal text is 4.5.

    uv run python spikes/web/contrast.py
"""

from __future__ import annotations

import re
from pathlib import Path

HERE = Path(__file__).parent


def luminance(hex_color: str) -> float:
    rgb = [int(hex_color.strip()[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def ratio(fg: str, bg: str) -> float:
    a, b = sorted((luminance(fg), luminance(bg)), reverse=True)
    return (a + 0.05) / (b + 0.05)


PAIRS = [
    ("ink", "bg", "body text"), ("ink", "surface", "cards"), ("ink", "surface-2", "fact"),
    ("muted", "bg", "dates, intro"), ("muted", "surface", "kickers, chips"),
    ("muted", "surface-2", "fact source"), ("link", "bg", "links"),
    ("link", "surface", "links in cards"), ("accent-ink", "surface", "type"),
    ("accent-ink", "surface-2", "fact number"), ("on-accent", "accent", "week box, button"),
    ("ink", "note-bg", "medical notice"), ("head-ink", "head-bg", "header"),
    ("ok", "surface", "verified"), ("warn-ink", "surface", "preprint chip"),
    ("alert-ink", "surface", "retracted / corrected"), ("on-alert", "alert", "notice chip"),
    ("gap-ink", "gap-bg", "gaps, provisional"), ("ink", "atlas-bg", "Atlas tile"),
    ("link", "atlas-bg", "Atlas tile link"), ("muted", "atlas-bg", "Atlas credit"),
    ("muted", "foot-bg", "footer"), ("ink", "accent-soft", "tags"),
    ("link", "accent-soft", "glossary term (hover), glossary target"),
    ("link", "surface", "glossary popover link"),
]  # fmt: skip


def tokens(css: str, x: str) -> dict[str, dict[str, str]]:
    def block(sel: str) -> dict[str, str]:
        body = re.search(re.escape(sel) + r"\s*\{(.*?)\}", css, re.S).group(1)
        return dict(re.findall(r"--([\w-]+):\s*([^;]+);", body))

    base = block(":root")
    if x == "n":  # dark by default
        return {"light": base | block(':root[data-theme="light"]'), "dark": base}
    return {"light": base, "dark": base | block(':root[data-theme="dark"]')}


def main() -> None:
    worst = {}
    for x in ("n",):
        modes = tokens((HERE / "v3/styles" / f"{x}.css").read_text(encoding="utf-8"), x)
        print(f"\n## {x.upper()}\n\n| par | uso | claro | oscuro |\n|---|---|---|---|")
        for fg, bg, use in PAIRS:
            r = {m: ratio(modes[m][fg], modes[m][bg]) for m in modes}
            flag = lambda v: f"{v:.2f}" + ("" if v >= 4.5 else " ✗")  # noqa: E731
            print(f"| {fg} / {bg} | {use} | {flag(r['light'])} | {flag(r['dark'])} |")
            for m in r:
                worst[(x, m)] = min(worst.get((x, m), 99), r[m])
    tiles = {
        "memory": "#1d4f91",
        "addiction": "#7b2a8f",
        "neurodegeneration": "#8a3b12",
        "neuroinflammation": "#1f6b4a",
        "sleep": "#3b3f99",
        "emotion": "#9a2445",
    }
    print("\n| tema (texto blanco, extremo claro) | ratio |\n|---|---|")
    for k, c in tiles.items():
        print(f"| {k} | {ratio('#ffffff', c):.2f} |")
    print("\nmínimo:", {f"{x}-{m}": round(v, 2) for (x, m), v in worst.items()})


if __name__ == "__main__":
    main()
