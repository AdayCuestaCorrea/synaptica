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
    assert report.pages == 17  # root + 8 kinds in 2 languages; no study without data


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
    """The glossary (Phase 2) is not built: no link to it."""
    out = build(tmp_path)
    for page in out.rglob("*.html"):
        text = page.read_text()
        assert "glosario.html" not in text and "glossary.html" not in text, page
    es = (out / "es/index.html").read_text()
    for href in ("como-evaluamos.html", "fuentes.html", "estado.html", "sobre-nosotros.html"):
        assert f'href="{href}"' in es, href


def test_relative_urls_only(tmp_path: Path) -> None:
    """Works under any base path (/synaptica/ on Pages), and nothing is *loaded* from
    another domain: every src, stylesheet, script and font is local. Plain links
    (<a href>) to the sources and to Paleo Atlas may point elsewhere."""
    out = build(tmp_path)
    for page in out.rglob("*.html"):
        html = page.read_text()
        for ref in re.findall(r'(?:href|src)="([^"]+)"', html):
            assert not ref.startswith("/"), (page, ref)
        loaded = re.findall(r'src="([^"]+)"', html) + re.findall(
            r'<link[^>]*rel="(?:stylesheet|preload|icon)"[^>]*href="([^"]+)"', html
        )
        assert loaded and not [r for r in loaded if r.startswith(("http", "//"))], page
    assert "url(http" not in (out / "static/synaptica.css").read_text()


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


def test_check_figure_needs_its_authors_and_licence_in_sight(tmp_path: Path) -> None:
    (tmp_path / "es").mkdir()
    (tmp_path / "es/f.webp").write_bytes(b"")
    good = (
        '<figure data-figure-credit="Ramón et al."><img src="f.webp">'
        "<figcaption>Figura 1 · Ramón et al. · CC BY 4.0</figcaption></figure>"
    )
    page(tmp_path, "es/a.html", good)
    assert check_site(tmp_path).passed
    page(tmp_path, "es/a.html", good.replace("· Ramón et al. ", ""))
    problems = check_site(tmp_path).problems
    assert any("figure without its authors' credit" in p for p in problems)
    page(tmp_path, "es/a.html", good.replace(" · CC BY 4.0", ""))
    assert any("without a licence" in p for p in check_site(tmp_path).problems)


@pytest.mark.parametrize("body", [
    '<img src="https://pmc.ncbi.nlm.nih.gov/x.jpg" alt="">',
    '<img src="//cdn.example/x.jpg" alt="">',
    '<img src="a.webp" srcset="a.webp 1x, https://x.example/b.webp 2x" alt="">',
    '<script src="https://cdn.example/x.js"></script>',
    '<link rel="stylesheet" href="https://fonts.example/f.css">',
    '<link rel="preconnect" href="https://fonts.example">',
    '<div style="background: url(https://x.example/b.png)"></div>',
])  # fmt: skip
def test_check_nothing_is_loaded_from_another_domain(tmp_path: Path, body: str) -> None:
    (tmp_path / "es").mkdir()
    (tmp_path / "es/a.webp").write_bytes(b"")
    page(tmp_path, "es/a.html", body)
    assert any("from another domain" in p for p in check_site(tmp_path).problems)


def test_check_links_to_other_domains_are_fine(tmp_path: Path) -> None:
    page(tmp_path, "es/a.html", '<a href="https://doi.org/10.1/a">DOI</a>')
    assert check_site(tmp_path).passed


def test_check_stylesheet_loading_from_another_domain(tmp_path: Path) -> None:
    page(tmp_path, "es/a.html", "<p>x</p>")
    (tmp_path / "s.css").write_text("@font-face { src: url('https://x.example/f.woff2'); }")
    assert any("s.css: loads from another domain" in p for p in check_site(tmp_path).problems)
    (tmp_path / "s.css").write_text("@import 'https://x.example/more.css';")
    assert any("s.css: loads from another domain" in p for p in check_site(tmp_path).problems)
    (tmp_path / "s.css").write_text("@font-face { src: url('fonts/f.woff2'); }")
    assert check_site(tmp_path).passed


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


# -- fixed pages (step 22) ----------------------------------------------------------------


def test_sources_seed_covers_every_source() -> None:
    """Every source the pipeline ingests, and every news outlet, has its row with a
    licence in both languages: the page «Fuentes y licencias» cannot miss one."""
    from synaptica.site.build import load_seed

    rows = load_seed("sources")
    keys = {r["source"] for r in rows}
    assert {r["source"] for r in load_seed("source_cadence")} <= keys
    assert {"openalex", "crossref"} <= keys
    outlets = {r["outlet"] for r in rows if r["source"] == "news"}
    assert {r["outlet"] for r in load_seed("news_feeds")} == outlets
    for r in rows:
        for col in ("name", "role_es", "role_en", "takes_es", "takes_en", "licence_es",
                    "licence_en"):  # fmt: skip
            assert r[col].strip(), (r["source"], col)


def test_sources_page_lists_sources_and_journals(tmp_path: Path) -> None:
    page = (build(tmp_path) / "en/sources.html").read_text()
    for text in ("PubMed (NLM)", "OpenAlex", "CC BY-ND 4.0", "Neuron", "nature.rss",
                 "Home page image: Sofía, made with ChatGPT · CC BY-SA 4.0"):  # fmt: skip
        assert text in page, text


def test_status_without_runs_says_so(tmp_path: Path) -> None:
    out = tmp_path / "site"
    SiteBuilder(out, images=LICENSED, data_dir=tmp_path / "data").build()
    es = (out / "es/estado.html").read_text()
    assert "Todavía no hay ejecuciones registradas" in es
    assert "<table" not in es


def test_status_shows_the_recorded_runs(tmp_path: Path) -> None:
    import datetime as dt

    from synaptica import report

    data = tmp_path / "data"
    t0 = dt.datetime(2026, 11, 12, 6, 23, tzinfo=dt.UTC)
    report.start_run(data, trigger="schedule", changed=True, now=t0)
    report.finish_run(data, now=t0 + dt.timedelta(minutes=9))
    report.start_run(data, trigger="backup", changed=False, now=t0 + dt.timedelta(days=1))
    out = tmp_path / "site"
    SiteBuilder(out, images=LICENSED, data_dir=data).build()
    en = (out / "en/status.html").read_text()
    assert en.index("2026-11-13 06:23") < en.index("2026-11-12 06:23")  # newest first
    assert "Backup" in en and "Running" in en and "Scheduled" in en and "Succeeded" in en
    assert check_site(out).passed


def test_fixed_pages_mark_their_gaps(tmp_path: Path) -> None:
    out = build(tmp_path)
    method = (out / "es/como-evaluamos.html").read_text()
    for key in ("method_review", "journal_name", "retraction_watch"):
        assert f'id="gap-{key}"' in method and f'href="#gap-{key}"' in method, key
    assert "provisional" not in method.lower()
    about = (out / "en/about.html").read_text()
    assert 'id="gap-contact"' in about and "@" not in about  # no address until they decide
