"""WCAG 2.x contrast of every text/background pair the mock-ups use, light and dark.

Reads the colour tokens from each mock-up's CSS (``:root`` and ``:root[data-theme="dark"]``)
and prints the ratio of each pair; AA for normal text is 4.5. The type tints of mock-up C
are left out on purpose: they are decoration (a stripe and a dot next to the type's word),
never a background for text.

    uv run python spikes/web/contrast.py
"""

from __future__ import annotations

import colorsys
import re
from pathlib import Path

HERE = Path(__file__).parent
# (foreground, background, where it is used)
PAIRS = {
    "a": [
        ("ink", "bg", "body text"), ("ink", "surface", "boxes, footer"),
        ("muted", "bg", "kickers, notes"), ("muted", "surface", "footer, Classics"),
        ("accent", "bg", "links, type"), ("accent", "surface", "links in boxes"),
        ("on-accent", "accent", "pressed filter, button"),
        ("ink", "accent-soft", "medical notice"),
        ("bg", "ink", "weekly ribbon"),
        ("alert", "bg", "retracted / corrected"), ("alert", "surface", "idem, in boxes"),
        ("gap-ink", "gap-bg", "gaps, provisional"),
    ],
    "b": [
        ("text", "bg", "body text"), ("text", "surface", "panels, bar"),
        ("muted", "bg", "dates, meta"), ("muted", "surface", "even rows"),
        ("muted", "surface-2", "table head"),
        ("blue", "bg", "links, verified"), ("blue", "surface", "idem, even rows"),
        ("blue", "blue-soft", "channel icon"), ("text", "blue-soft", "medical notice"),
        ("magenta", "bg", "preprint"), ("magenta", "surface", "preprint, even rows"),
        ("magenta", "magenta-soft", "preprint icon"),
        ("on-accent", "blue", "week button, button"), ("bg", "text", "pressed filter"),
        ("alert", "bg", "retracted / corrected"), ("alert", "surface", "idem, even rows"),
        ("alert", "alert-soft", "notice icon"),
        ("gap-ink", "gap-bg", "gaps, provisional"),
    ],
    "c": [
        ("text", "bg", "page text"), ("text", "surface", "card text"),
        ("muted", "surface", "card meta, fallback"), ("muted", "bg", "date line"),
        ("muted", "surface-2", "counters, pill label"), ("text", "surface-2", "pills"),
        ("accent", "surface", "links, verified"), ("accent", "bg", "back link"),
        ("accent", "accent-soft", "preprint pill"), ("text", "accent-soft", "medical notice"),
        ("on-accent", "accent", "nav, button"), ("bg", "text", "pressed filter"),
        ("alert", "alert-soft", "retracted / corrected"),
        ("gap-ink", "gap-bg", "gaps, provisional"),
    ],
}  # fmt: skip


def parse(color: str) -> tuple[float, float, float]:
    color = color.strip()
    if color.startswith("#"):
        return tuple(int(color[i : i + 2], 16) / 255 for i in (1, 3, 5))  # type: ignore[return-value]
    if m := re.match(r"hsl\(([\d.]+) ([\d.]+)% ([\d.]+)%\)", color):
        h, s, lum = (float(v) for v in m.groups())
        return colorsys.hls_to_rgb(h / 360, lum / 100, s / 100)
    raise ValueError(color)


def luminance(rgb: tuple[float, float, float]) -> float:
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def ratio(fg: str, bg: str) -> float:
    a, b = sorted((luminance(parse(fg)), luminance(parse(bg))), reverse=True)
    return (a + 0.05) / (b + 0.05)


def tokens(css: str) -> dict[str, dict[str, str]]:
    block = lambda sel: re.search(re.escape(sel) + r"\s*\{(.*?)\}", css, re.S).group(1)  # noqa: E731
    read = lambda body: dict(re.findall(r"--([\w-]+):\s*([^;]+);", body))  # noqa: E731
    light = read(block(":root"))
    return {"light": light, "dark": light | read(block(':root[data-theme="dark"]'))}


def main() -> None:
    worst = {}
    for x, pairs in PAIRS.items():
        modes = tokens((HERE / x / "static" / f"{x}.css").read_text(encoding="utf-8"))
        print(f"\n## {x.upper()}\n\n| par | uso | claro | oscuro |\n|---|---|---|---|")
        for fg, bg, use in pairs:
            r = {m: ratio(modes[m][fg], modes[m][bg]) for m in modes}
            flag = lambda v: f"{v:.2f}" + ("" if v >= 4.5 else " ✗")  # noqa: E731
            print(f"| {fg} / {bg} | {use} | {flag(r['light'])} | {flag(r['dark'])} |")
            for m in r:
                worst[(x, m)] = min(worst.get((x, m), 99), r[m])
    print("\nmínimo:", {f"{x}-{m}": round(v, 2) for (x, m), v in worst.items()})


if __name__ == "__main__":
    main()
