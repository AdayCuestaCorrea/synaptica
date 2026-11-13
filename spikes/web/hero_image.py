"""The header image of the mock-up without its background (Aday, 2026-11-13).

The image was made by Sofía with ChatGPT: white line art and teal fills on a flat night-blue
background. Its background is turned into transparency by colour-to-alpha (the idea of GIMP's
filter): each pixel is read as the background colour plus a line colour on top with some
opacity, and the opacity is the smallest that explains it. So anti-aliased edges keep their
softness and leave no dark halo.

Two versions, one per theme of the «Noche» mock-up:
* dark (default): the lines as they are, white;
* light: the white and grey lines in the theme's ink colour, the teal in its accent, because
  white lines on a light page would not be seen.

    uv run python spikes/web/hero_image.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).parent
SRC = HERE / "img/cabecera-cerebro-original.webp"
OUT = {"dark": HERE / "img/cabecera-cerebro-oscuro.webp",
       "light": HERE / "img/cabecera-cerebro-claro.webp"}  # fmt: skip
INK_LIGHT = np.array([0x0F, 0x16, 0x26], dtype=np.float32)  # --ink, light theme (n.css)
ACCENT_LIGHT = np.array([0x0F, 0x76, 0x6E], dtype=np.float32)  # --accent, light theme
NOISE = 0.08  # opacity below this is background noise (compression grain of the source)
BG_TOL = 14  # a pixel this close (per channel) to the border colour counts as background
BG_SIGMA = 12  # px: how far the background estimate reaches under the drawing
SPECK = 8  # px: smaller separate specks are grain, not drawing
NEAR = 2  # px: light version, faint pixels kept this close to a line
FILL_MIN = 400  # px: a teal area at least this big is a fill (light version: accent)


def background(rgb: np.ndarray) -> np.ndarray:
    """The background colour at every pixel. It is not flat (a soft gradient and compression
    grain), so: the pixels close to the border colour are background, and a wide blur of only
    those (normalised convolution) fills in the background under the drawing too."""
    from scipy.ndimage import gaussian_filter

    p = rgb.astype(np.float32)
    border = np.concatenate([p[0], p[-1], p[:, 0], p[:, -1]])
    flat = np.median(border, axis=0)
    is_bg = (np.abs(p - flat).max(axis=-1) < BG_TOL).astype(np.float32)
    weight = gaussian_filter(is_bg, BG_SIGMA)
    out = np.stack([gaussian_filter(p[..., c] * is_bg, BG_SIGMA) for c in range(3)], axis=-1)
    return np.where(weight[..., None] > 1e-3, out / np.maximum(weight, 1e-3)[..., None], flat)


def colour_to_alpha(rgb: np.ndarray, bg: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(colour, alpha) such that colour over bg with that alpha gives rgb, alpha smallest."""
    p = rgb.astype(np.float32)
    up = np.where(p > bg, (p - bg) / np.maximum(255 - bg, 1), 0)
    down = np.where(p < bg, (bg - p) / np.maximum(bg, 1), 0)
    alpha = np.max(np.maximum(up, down), axis=-1)
    alpha = np.where(alpha < NOISE, 0, alpha)
    # Loose specks of grain (a few pixels apart from any line) are not drawing.
    from scipy.ndimage import label

    lab, n = label(alpha > 0)
    sizes = np.bincount(lab.ravel(), minlength=n + 1)
    alpha = np.where(sizes[lab] < SPECK, 0, alpha)
    alpha[lab == 0] = 0
    safe = np.maximum(alpha, 1e-6)[..., None]
    colour = np.clip((p - bg) / safe + bg, 0, 255)
    return colour, alpha


def light_version(colour: np.ndarray, alpha: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """White and grey lines in ink, teal in the accent, by how saturated each pixel is. Only
    teal areas of FILL_MIN px or more get the accent: the fills are large and continuous, the
    grain beside the lines is specks of the same faint opacity (measured: ~0.15 both).

    Dark ink on a light page shows grain that white on night blue hides, so faint pixels are
    kept only within NEAR px of a line (their anti-aliasing) or inside a fill."""
    from scipy.ndimage import binary_dilation, label

    mx, mn = colour.max(axis=-1), colour.min(axis=-1)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1), 0)[..., None]
    sat = np.clip(sat * 2.5, 0, 1)  # the teal of the source is soft: full accent from ~0.4
    lab, n = label((sat[..., 0] > 0.3) & (alpha > 0))
    big = np.bincount(lab.ravel(), minlength=n + 1) >= FILL_MIN
    big[0] = False
    fill = big[lab]
    sat = sat * fill[..., None]
    keep = binary_dilation(alpha > 0.5, iterations=NEAR) | fill
    return INK_LIGHT * (1 - sat) + ACCENT_LIGHT * sat, np.where(keep, alpha, 0)


def main() -> None:
    rgb = np.asarray(Image.open(SRC).convert("RGB"))
    bg = background(rgb)
    colour, alpha = colour_to_alpha(rgb, bg)
    for theme, (c, a) in (("dark", (colour, alpha)), ("light", light_version(colour, alpha))):
        a8 = np.rint(a * 255).astype(np.uint8)
        rgba = np.dstack([np.rint(c).astype(np.uint8), a8])
        Image.fromarray(rgba, "RGBA").save(OUT[theme], "WEBP", quality=88, method=6)
        print(theme, OUT[theme].name, OUT[theme].stat().st_size, "bytes")
        print("  transparent", round(float((a8 == 0).mean()), 3))
    print("background", bg.mean(axis=(0, 1)).round(1).tolist())


if __name__ == "__main__":
    main()
