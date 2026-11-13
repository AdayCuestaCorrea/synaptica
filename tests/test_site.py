"""The static website (plan, step 21): build and ``syn site --check``. No network: the
build reads only the templates, the static files and the interface strings."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from synaptica.site.build import SiteBuilder, load_i18n
from synaptica.site.check import _PageParser, check_site

LICENSED = {"hero": {"files": [], "author": "Sofía", "licence": "CC BY-SA 4.0"}}
PENDING = {"hero": {"files": [], "author": "Sofía", "licence": ""}}


def test_i18n_same_keys() -> None:
    i18n = load_i18n()
    assert set(i18n["es"]) == set(i18n["en"])


def test_i18n_no_empty_string() -> None:
    for lang, strings in load_i18n().items():
        assert all(v.strip() for v in strings.values()), lang


def build(tmp_path: Path, images=LICENSED) -> Path:
    out = tmp_path / "site"
    SiteBuilder(out, images=images).build()
    return out


def test_build_passes_the_check(tmp_path: Path) -> None:
    out = build(tmp_path)
    for rel in ("index.html", "es/index.html", "en/index.html", "static/synaptica.css"):
        assert (out / rel).exists(), rel
    report = check_site(out)
    assert report.passed, report.problems
    assert report.pages == 3


def test_build_is_idempotent(tmp_path: Path) -> None:
    out = build(tmp_path)
    first = {p: p.read_bytes() for p in out.rglob("*") if p.is_file()}
    SiteBuilder(out, images=LICENSED).build()
    assert {p: p.read_bytes() for p in out.rglob("*") if p.is_file()} == first


def test_build_never_wipes_a_foreign_folder(tmp_path: Path) -> None:
    out = tmp_path / "site"
    out.mkdir()
    (out / "keep.txt").write_text("mine")
    with pytest.raises(RuntimeError):
        SiteBuilder(out, images=LICENSED).build()
    assert (out / "keep.txt").exists()


def test_pending_licence_is_shown_as_a_gap_and_fails(tmp_path: Path) -> None:
    out = build(tmp_path, PENDING)
    page = (out / "es/index.html").read_text()
    assert "licencia pendiente" in page and 'href="#gap-hero_licence"' in page
    problems = check_site(out).problems
    assert any("without a licence in #credit-hero" in p for p in problems)


def test_pages_link_only_to_built_pages(tmp_path: Path) -> None:
    """Step 21 builds only the home page: no link to Neuro News or the fixed pages yet."""
    page = (build(tmp_path) / "es/index.html").read_text()
    assert "noticias.html" not in page and "como-evaluamos.html" not in page


def test_relative_urls_only(tmp_path: Path) -> None:
    """Works under any base path (/synaptica/ on Pages); nothing from another domain except
    the S3 prototype on our own GitHub Pages."""
    out = build(tmp_path)
    for page in out.rglob("*.html"):
        refs = re.findall(r'(?:href|src)="([^"]+)"', page.read_text())
        for ref in refs:
            assert not ref.startswith("/"), (page, ref)
            if ref.startswith("http"):
                assert ref.startswith("https://adaycuestacorrea.github.io/synaptica/"), ref


def test_both_languages_alternate(tmp_path: Path) -> None:
    out = build(tmp_path)
    es, en = (out / "es/index.html").read_text(), (out / "en/index.html").read_text()
    assert 'hreflang="en" href="../en/index.html"' in es
    assert 'hreflang="es" href="../es/index.html"' in en
    assert '<html lang="es"' in es and '<html lang="en"' in en


# -- the check, on hand-written pages ---------------------------------------------------

NOTICE = load_i18n()["es"]["disclaimer"]


def page(root: Path, rel: str, body: str, *, alternate: bool = True,
         notice: bool = True) -> Path:  # fmt: skip
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    alt = f'<link rel="alternate" hreflang="en" href="{path.name}">' if alternate else ""
    note = f'<p class="disclaimer">{NOTICE}</p>' if notice else ""
    path.write_text(f"<html><head>{alt}</head><body>{note}{body}</body></html>")
    return path


def test_check_broken_link_and_missing_alternate(tmp_path: Path) -> None:
    page(tmp_path, "es/a.html", '<a href="missing.html">x</a>', alternate=False)
    problems = check_site(tmp_path).problems
    assert any("broken link missing.html" in p for p in problems)
    assert any("es/a.html: no hreflang alternate" in p for p in problems)


def test_check_absolute_path_is_reported(tmp_path: Path) -> None:
    page(tmp_path, "es/a.html", '<a href="/es/a.html">x</a>')
    assert any("broken link /es/a.html" in p for p in check_site(tmp_path).problems)


def test_check_medical_notice(tmp_path: Path) -> None:
    page(tmp_path, "es/a.html", "<p>hola</p>", notice=False)
    assert any("es/a.html: no medical notice" in p for p in check_site(tmp_path).problems)


def test_check_medical_notice_in_the_wrong_language(tmp_path: Path) -> None:
    page(tmp_path, "en/a.html", "<p>hi</p>")  # carries the Spanish notice
    assert any("en/a.html: no medical notice" in p for p in check_site(tmp_path).problems)


SIGNALS_OK = (
    '<article data-study="10.1/a"><ul><li data-signal="review"><span>Preprint</span></li>'
    '<li data-signal="subject">Sin dato</li><li data-signal="integrity">Sin avisos</li></ul>'
    "</article>"
)


def test_check_signals_complete(tmp_path: Path) -> None:
    page(tmp_path, "es/a.html", SIGNALS_OK)
    assert check_site(tmp_path).passed


def test_check_signals_missing_or_empty(tmp_path: Path) -> None:
    body = SIGNALS_OK.replace('<li data-signal="integrity">Sin avisos</li>', "")
    body = body.replace("Sin dato", "")
    page(tmp_path, "es/a.html", body)
    problems = check_site(tmp_path).problems
    assert any("study 10.1/a without subject, integrity" in p for p in problems)


def test_check_images_need_a_licensed_credit(tmp_path: Path) -> None:
    (tmp_path / "es").mkdir()
    (tmp_path / "es/i.webp").write_bytes(b"")
    body = (
        '<figure><img src="i.webp"><figcaption>Foto de alguien</figcaption></figure>'
        '<img src="i.webp">'
        '<img src="i.webp" data-credit="c1"><p id="c1">Sofía · <b>CC BY-SA 4.0</b></p>'
        '<img src="i.webp" data-credit="c2"><p id="c2">Sofía · licencia pendiente</p>'
    )
    page(tmp_path, "es/a.html", body)
    problems = check_site(tmp_path).problems
    assert any("1 image(s) without a licence in the credit" in p for p in problems)
    assert any("image i.webp without a credit" in p for p in problems)
    assert any("#c2" in p for p in problems)
    assert not any("#c1" in p for p in problems)


def test_check_orphan_study_page(tmp_path: Path) -> None:
    page(tmp_path, "es/estudio/a.html", SIGNALS_OK)
    page(tmp_path, "es/estudio/b.html", SIGNALS_OK)
    page(tmp_path, "es/index.html", '<a href="estudio/a.html">a</a>')
    problems = check_site(tmp_path).problems
    assert any("es/estudio/b.html: no page links to it" in p for p in problems)
    assert not any("estudio/a.html: no page" in p for p in problems)


def test_check_unbalanced_tags(tmp_path: Path) -> None:
    page(tmp_path, "es/a.html", "<div><p>x</div>")
    assert any("unbalanced tags" in p for p in check_site(tmp_path).problems)


def test_check_empty_site(tmp_path: Path) -> None:
    assert not check_site(tmp_path).passed


def test_parser_nested_capture_closes_at_its_own_end() -> None:
    p = _PageParser()
    p.feed('<div id="a"><span>uno</span> dos</div><p id="b">tres</p>')
    assert p.texts_by_id == {"a": "uno dos", "b": "tres"}


# -- contrast: WCAG AA (4.5) for every text/background pair, light and dark --------------
# From spikes/web/contrast.py, which measured the mock-up (SCOPE v79).

PAIRS = [
    ("ink", "bg"), ("ink", "surface"), ("ink", "surface-2"), ("muted", "bg"),
    ("muted", "surface"), ("muted", "surface-2"), ("link", "bg"), ("link", "surface"),
    ("accent-ink", "surface"), ("accent-ink", "surface-2"), ("on-accent", "accent"),
    ("ink", "note-bg"), ("head-ink", "head-bg"), ("ok", "surface"), ("warn-ink", "surface"),
    ("alert-ink", "surface"), ("on-alert", "alert"), ("gap-ink", "gap-bg"),
    ("ink", "atlas-bg"), ("link", "atlas-bg"), ("muted", "atlas-bg"), ("muted", "foot-bg"),
    ("ink", "accent-soft"), ("link", "accent-soft"),
]  # fmt: skip


def _luminance(hex_color: str) -> float:
    rgb = [int(hex_color.strip()[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _ratio(fg: str, bg: str) -> float:
    a, b = sorted((_luminance(fg), _luminance(bg)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def _tokens(css: str, selector: str) -> dict[str, str]:
    body = re.search(re.escape(selector) + r"\s*\{(.*?)\}", css, re.S).group(1)
    return dict(re.findall(r"--([\w-]+):\s*([^;]+);", body))


@pytest.mark.parametrize("mode", ["dark", "light"])
def test_contrast_aa(mode: str) -> None:
    from synaptica.site.build import SITE_DIR

    css = (SITE_DIR / "static/noche.css").read_text(encoding="utf-8")
    tokens = _tokens(css, ":root")  # dark by default
    if mode == "light":
        tokens |= _tokens(css, ':root[data-theme="light"]')
    low = {f"{fg}/{bg}": round(_ratio(tokens[fg], tokens[bg]), 2) for fg, bg in PAIRS}
    assert all(v >= 4.5 for v in low.values()), {k: v for k, v in low.items() if v < 4.5}
