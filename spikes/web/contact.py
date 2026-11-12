"""Contact sheet: real candidate images for each illustration slot of the mock-up (SCOPE
v82), for Aday and Sofía to choose. Not part of the site.

Sources (decision of Aday: NIH BioArt for the section cards and topics, Wikimedia Commons
for a real image in the header; Sofía did not like our brain capture in the header, nor,
for the same look, in the Neuro Atlas card; no AI images, no Cajal drawings):

* NIH BioArt (bioart.niaid.nih.gov): the item page states licence, creator and credit;
  the image is its large PNG (``/api/bioarts/<id>/files/<file>``).
* Wikimedia Commons: the API's ``extmetadata`` (licence, author, credit, page).

The metadata come from each source, never typed by hand: ``data/contact.json``
(committed). Originals are cached in ``data/sources/images/contact/`` and the sheet is
written to ``contact/`` (both ignored by git: a tool to choose, not site content).

    uv run python spikes/web/contact.py
    python -m http.server 8771 --bind 127.0.0.1 --directory spikes/web   # → /contact/
"""

from __future__ import annotations

import html
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from synaptica.http import get_json, make_client

HERE = Path(__file__).parent
CACHE = HERE / "data/sources/images/contact"
OUT = HERE / "contact"
BIOART = "https://bioart.niaid.nih.gov"
COMMONS = "https://commons.wikimedia.org/w/api.php"

# slot -> (title, where it goes, candidates). A candidate is ("bioart", id) or
# ("commons", "File:…"). Picked by hand from searches of both sources (session of v82).
SLOTS: dict[str, tuple[str, str, list[tuple[str, Any]]]] = {
    "hero": ("Cabecera «Tu portal de neurociencia»",
             "Sustituye a la captura del cerebro de nuestro visor. Imagen real (Commons).",
             [("commons", "File:Brainbow (Smith 2007).jpg"),
              ("commons", "File:All that glitters in the brain.jpg"),
              ("commons", "File:A Star of Neurons, Uma Estrela de Neurónios.jpg")]),
    "atlas": ("Tarjeta Neuro Atlas",
              "Sustituye a las dos capturas (rata y humano). La tarjeta puede llevar un "
              "cerebro humano y uno de roedor.",
              [("bioart", 60), ("bioart", 590), ("bioart", 369)]),
    "lab": ("Tarjeta Neuro Lab", "Técnicas de laboratorio.",
            [("bioart", 86), ("bioart", 485), ("bioart", 408)]),
    "learn": ("Tarjeta Neuro Learn", "Explicaciones (neurona, sinapsis, glía…).",
              [("bioart", 197), ("bioart", 424), ("bioart", 40)]),
    "diseases": ("Tarjeta Neuro Diseases", "Enfermedades neurológicas.",
                 [("commons", "File:Histopathology of amyloid plaque in Alzheimer's disease.jpg"),
                  ("bioart", 689)]),
    "history": ("Tarjeta Neuro History", "Historia (sin Cajal).",
                [("commons", "File:GolgiStainedPyramidalCell.jpg"),
                 ("commons", "File:1870 circa, binocular compound microscope, Henry Crouch, "
                             "England - Golub Collection of Antique Microscopes - DSC04870.JPG"),
                 ("commons", "File:1858, Model No. 2 compound microscope, Powell & Lealand, "
                             "England - Golub Collection of Antique Microscopes - DSC04864.JPG")]),
    "experiments": ("Tarjeta Neuro Experiments", "Ilusiones ópticas y pruebas en pantalla.",
                    [("commons", "File:Müller-Lyer illusion - Franz Bretano - 1892.png"),
                     ("commons", "File:Cafe Wall Illusion.png"),
                     ("bioart", 855)]),
    "t-memory": ("Tema Memoria", "Tarjeta del carrusel y cabecera de su página.",
                 [("commons", 'File:"Forest of memory".jpg'),
                  ("commons", "File:DCX+ cells in the dentate gyrus.tif"),
                  ("commons", "File:Rat hippocampus stained with antibody to NeuN (green), "
                              "myelin basic protein (red) and DNA (blue).jpg")]),
    "t-addiction": ("Tema Adicción", "BioArt no tiene nada propio de adicción.",
                    [("commons", "File:Dopamine Pathway.png"),
                     ("commons", "File:Dopamine Pathways.png"),
                     ("bioart", 407)]),
    "t-neurodegeneration": ("Tema Neurodegeneración", "",
                            [("commons", "File:Histopathology of Alzheimer's disease.jpg"),
                             ("commons", "File:Cerebral amyloid angiopathy -2a- amyloid beta "
                                         "- high mag.jpg")]),
    "t-neuroinflammation": ("Tema Neuroinflamación", "",
                            [("commons", "File:Microglia and neurons.jpg"),
                             ("commons", "File:Fluorescently Labeled Microglia in a Coronal "
                                         "Brain Section from a C57 Mouse.jpg"),
                             ("commons", "File:Mikroglej 1.jpg")]),
    "t-sleep": ("Tema Sueño", "Ni BioArt ni Commons tienen una imagen buena: solo gráficas "
                              "(hipnograma, EEG).",
                [("commons", "File:Hypnogram 1.jpg"), ("commons", "File:Sleep EEG Stage 4.jpg")]),
    "t-emotion": ("Tema Emoción", "Láminas de Darwin (1872). La de miedo es una de las "
                                  "caras de Duchenne, provocadas con electricidad. El tema "
                                  "sigue pendiente de Sofía (v13).",
                  [("commons", "File:Expression of the Emotions Plate VII (fear1).jpg"),
                   ("commons", "File:Expression of the Emotions Plate IV (sneering).png")]),
}  # fmt: skip


def text(value: str | None) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value or ""))).strip()


def bioart(client: Any, item: int) -> dict[str, Any]:
    page = client.get(f"{BIOART}/bioart/{item}", timeout=60).text
    raw = page.replace('\\"', '"')

    def field(label: str) -> str | None:
        m = re.search(rf">{label}</h6><p[^>]*>(.*?)</p>", page)
        return text(m.group(1)) if m else None

    lic = re.search(r"Licensing:(?:\s|&nbsp;|\xa0)*<a[^>]*>(.*?)</a>", page)
    title = re.search(r'<h4 class="[^"]*MuiTypography-h4[^"]*">(.*?)</h4>', page)
    file_id = re.search(r'"carouselItems":\[\{"fileId":(\d+)', raw)
    if not (lic and file_id):
        raise SystemExit(f"BioArt {item}: licence or image not found")
    return {
        "source": "NIH BioArt", "id": f"BIOART-{item:06d}",
        "title": text(title.group(1)) if title else None,
        "author": field("Creator"), "credit": field("Credit"),
        "licence": text(lic.group(1)), "licence_url": f"{BIOART}/faqs#usage-restrictions-bioart",
        "page": f"{BIOART}/bioart/{item}",
        "file": f"{BIOART}/api/bioarts/{item}/files/{file_id.group(1)}",
    }  # fmt: skip


def commons(client: Any, title: str) -> dict[str, Any]:
    doc = get_json(client, COMMONS, params={
        "action": "query", "format": "json", "titles": title, "prop": "imageinfo",
        "iiprop": "url|extmetadata|size", "iiurlwidth": 1200})  # fmt: skip
    page = next(iter(doc["query"]["pages"].values()))
    ii = page["imageinfo"][0]
    m = ii["extmetadata"]
    get = lambda k: text((m.get(k) or {}).get("value"))  # noqa: E731
    return {
        "source": "Wikimedia Commons", "id": title,
        "title": title.removeprefix("File:").rsplit(".", 1)[0],
        "author": get("Artist") or None, "credit": get("Credit") or None,
        "licence": get("LicenseShortName"), "licence_url": get("LicenseUrl") or None,
        "page": ii["descriptionurl"], "file": ii["thumburl"],
        "size": [ii["width"], ii["height"]],
    }  # fmt: skip


def fetch(client: Any, url: str, name: str) -> Path:
    path = CACHE / name
    if not path.exists():
        r = client.get(url, timeout=120, follow_redirects=True)
        r.raise_for_status()
        CACHE.mkdir(parents=True, exist_ok=True)
        path.write_bytes(r.content)
    return path


def main() -> None:
    meta_path = HERE / "data/contact.json"
    known = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    (OUT / "img").mkdir(parents=True, exist_ok=True)
    out: dict[str, Any] = {}
    with make_client() as client:
        for slot, (_, _, cands) in SLOTS.items():
            rows = []
            for i, (kind, ref) in enumerate(cands, 1):
                key = f"{kind}:{ref}"
                meta = known.get(key) or (bioart(client, ref) if kind == "bioart"
                                          else commons(client, ref))  # fmt: skip
                known[key] = meta
                stem = f"{slot}-{i}"
                src = fetch(client, meta["file"], re.sub(r"[^\w.-]", "_", key)[:120])
                subprocess.run(["magick", f"{src}[0]", "-resize", "520x520>", "-strip",
                                "-quality", "82", str(OUT / "img" / f"{stem}.webp")],
                               check=True)  # fmt: skip
                rows.append({"code": stem, "key": key, **meta})
            out[slot] = rows
    meta_path.write_text(json.dumps(known, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "index.html").write_text(page(out), encoding="utf-8")
    print(f"{sum(len(v) for v in out.values())} candidates in {len(out)} slots → {OUT}")


def page(out: dict[str, list[dict[str, Any]]]) -> str:
    e = html.escape
    parts = []
    for slot, rows in out.items():
        title, note, _ = SLOTS[slot]
        cards = []
        for r in rows:
            lic = (f'<a href="{e(r["licence_url"])}">{e(r["licence"])}</a>'
                   if r.get("licence_url") else e(r["licence"]))  # fmt: skip
            who = " · ".join(e(x) for x in (r.get("author"), r.get("credit")) if x)
            cards.append(f"""<figure class="cand">
  <p class="code">{e(r["code"])}</p>
  <div class="pair"><div class="dark"><img src="img/{e(r["code"])}.webp" alt=""></div>
  <div class="light"><img src="img/{e(r["code"])}.webp" alt=""></div></div>
  <figcaption><strong>{e(r["title"] or r["id"])}</strong><br>
  {who or "Autor sin indicar en la fuente"}<br>
  {lic} · <a href="{e(r["page"])}">{e(r["source"])}</a></figcaption>
</figure>""")
        parts.append(f"""<section><h2>{e(title)}</h2>{f"<p>{e(note)}</p>" if note else ""}
<div class="grid">{"".join(cards)}</div></section>""")
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hoja de contactos · SYNAPTICA</title>
<style>
:root {{ --bg:#0b1020; --surface:#121a2e; --ink:#e9eef8; --muted:#a9b4cc; --rule:#26324d;
  --link:#8fe3da; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:16px/1.5 system-ui, sans-serif; }}
main {{ max-width:1180px; margin:0 auto; padding:16px; }}
a {{ color:var(--link); }}
h2 {{ border-bottom:1px solid var(--rule); padding-bottom:4px; margin-top:32px; }}
section > p, .intro {{ color:var(--muted); max-width:60rem; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill, minmax(330px, 1fr)); gap:16px; }}
.cand {{ margin:0; background:var(--surface); border:1px solid var(--rule); border-radius:12px;
  padding:10px; }}
.code {{ margin:0 0 6px; font-weight:700; font-family:ui-monospace, monospace; }}
.pair {{ display:grid; grid-template-columns:1fr 1fr; gap:6px; }}
.pair div {{ display:grid; place-items:center; aspect-ratio:4/3; border-radius:8px;
  overflow:hidden; }}
.dark {{ background:#0b1020; }} .light {{ background:#f4f6fb; }}
.pair img {{ max-width:100%; max-height:100%; object-fit:contain; }}
figcaption {{ font-size:0.85rem; color:var(--muted); margin-top:8px; overflow-wrap:anywhere; }}
figcaption strong {{ color:var(--ink); }}
</style></head><body><main>
<h1>Hoja de contactos de imágenes</h1>
<p class="intro">Candidatas reales para cada hueco de la maqueta Noche, cada una sobre fondo
oscuro y claro (los dos modos de la web). Autor, licencia y enlace salen de la fuente
(NIH BioArt o Wikimedia Commons). Sin imágenes generadas por IA ni dibujos de Cajal. Para
elegir, basta con el código (por ejemplo <code>hero-2</code>); un hueco puede quedarse sin
ninguna. Página interna, solo en español: no es parte de la web.</p>
{"".join(parts)}
</main></body></html>
"""


if __name__ == "__main__":
    main()
