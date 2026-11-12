"""WCAG contrast of every text/background pair of round 2 (styles G, N and L), light and dark.
AA for normal text is 4.5. Same arithmetic as ``contrast.py``.

    uv run python spikes/web/contrast2.py
"""

from __future__ import annotations

import re
from pathlib import Path

from contrast import ratio

HERE = Path(__file__).parent
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
]  # fmt: skip
TINTS = [("ink", "tint-news"), ("link", "tint-news"), ("ink", "tint-week"),
         ("link", "tint-week"), ("ink", "tint-method"), ("link", "tint-method")]  # fmt: skip


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
    for x in ("g", "n", "l"):
        modes = tokens((HERE / "v2/styles" / f"{x}.css").read_text(encoding="utf-8"), x)
        print(f"\n## {x.upper()}\n\n| par | uso | claro | oscuro |\n|---|---|---|---|")
        for fg, bg, use in PAIRS + [(f, b, "tile") for f, b in TINTS if x == "l"]:
            r = {m: ratio(modes[m][fg], modes[m][bg]) for m in modes}
            flag = lambda v: f"{v:.2f}" + ("" if v >= 4.5 else " ✗")  # noqa: E731
            print(f"| {fg} / {bg} | {use} | {flag(r['light'])} | {flag(r['dark'])} |")
            for m in r:
                worst[(x, m)] = min(worst.get((x, m), 99), r[m])
    print("\nmínimo:", {f"{x}-{m}": round(v, 2) for (x, m), v in worst.items()})


if __name__ == "__main__":
    main()
