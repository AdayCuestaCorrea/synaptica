// Spike S3: what mock-ups B (three.js) and C (Niivue) share. Throwaway code.
//
// - Texts in Spanish and English (?lang=en), as every SYNAPTICA page.
// - Data loading: per atlas, labels.json and licence.json from ../data/<atlas>/ (same origin),
//   plus equivalencias.json. Nothing is requested from another domain.
// - Equivalences: which regions of the other atlas to highlight. The grade is shown as it comes
//   in equivalencias.json ("pendiente de Sofía"); it is never computed here.

const TEXT = {
  es: {
    lang: "es",
    other: "English",
    otherHref: "?lang=en",
    disclaimer:
      "Esto no es consejo médico. Maqueta de prueba de SYNAPTICA para elegir el visor 3D: " +
      "no recomienda tratamientos.",
    rat: "Rata",
    human: "Humano",
    loading: "Cargando…",
    hint: "Toca o haz clic en una región. Arrastra para girar; pellizca o usa la rueda para acercar.",
    none: "Ninguna región seleccionada.",
    id: "ID",
    side: { L: "hemisferio izquierdo", R: "hemisferio derecho" },
    mpmLabel: "etiqueta en el mapa",
    area: "área",
    equivalent: "En el otro atlas",
    grade: "grado",
    noPair: "Esta región no está en las equivalencias de prueba.",
    licence: "Licencia",
    cite: "Cita",
    source: "Fuente",
    changes: "Cambios",
    changesText: "datos derivados por SYNAPTICA (ver licence.json); se comparten con la misma licencia.",
    coloursCalm: "Colores: paleta propia de SYNAPTICA por familias de regiones, no la del atlas.",
    background: "fondo",
    isolate: "Aislar selección",
    cortexShown: "Contorno: transparente",
    cortexHidden: "Contorno: oculto",
    libsB: "three.js (MIT) y el decodificador Draco (Apache-2.0), servidos desde esta web:",
    libsC: "Niivue (BSD-2-Clause), servido desde esta web:",
    licences: "licencias",
    view3d: "Solo 3D",
    view3dSlice: "3D + corte",
    clip: "Recortar",
    titleB: "SYNAPTICA · Visor B",
    subB: "three.js 0.187.0 · mallas propias",
    titleC: "SYNAPTICA · Visor C",
    subC: "Niivue 0.69.0 · volúmenes propios",
  },
  en: {
    lang: "en",
    other: "Español",
    otherHref: "?lang=es",
    disclaimer:
      "This is not medical advice. SYNAPTICA test mock-up to choose the 3D viewer: it does not " +
      "recommend treatments.",
    rat: "Rat",
    human: "Human",
    loading: "Loading…",
    hint: "Tap or click a region. Drag to rotate; pinch or use the wheel to zoom.",
    none: "No region selected.",
    id: "ID",
    side: { L: "left hemisphere", R: "right hemisphere" },
    mpmLabel: "map label",
    area: "area",
    equivalent: "In the other atlas",
    grade: "grade",
    noPair: "This region is not in the test equivalences.",
    licence: "Licence",
    cite: "Citation",
    source: "Source",
    changes: "Changes",
    changesText: "data derived by SYNAPTICA (see licence.json); shared under the same licence.",
    coloursCalm: "Colours: SYNAPTICA's own palette by region family, not the atlas's.",
    background: "background",
    isolate: "Isolate selection",
    cortexShown: "Outline: transparent",
    cortexHidden: "Outline: hidden",
    libsB: "three.js (MIT) and the Draco decoder (Apache-2.0), served from this site:",
    libsC: "Niivue (BSD-2-Clause), served from this site:",
    licences: "licences",
    view3d: "3D only",
    view3dSlice: "3D + slice",
    clip: "Cut away",
    titleB: "SYNAPTICA · Viewer B",
    subB: "three.js 0.187.0 · our own meshes",
    titleC: "SYNAPTICA · Viewer C",
    subC: "Niivue 0.69.0 · our own volumes",
  },
};

export const lang = new URLSearchParams(location.search).get("lang") === "en" ? "en" : "es";
export const t = TEXT[lang];
document.documentElement.lang = lang;

// Palette (S3 step 7.2): "calm" groups regions by family in soft tones (Sofía's request P5);
// ?colors=atlas shows the official colours of each atlas, to compare.
export const palette = new URLSearchParams(location.search).get("colors") === "atlas" ? "atlas" : "calm";

export function colourOf(row) {
  return (palette === "calm" && row && row.color_calm) || (row && row.color) || "#888888";
}

// A stronger version of a colour, for the selected region and its partner: with soft tones the
// selection has to stand out from the rest without relying on the grey alone.
export function strong(hex) {
  const n = parseInt(hex.slice(1), 16);
  let [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => v / 255);
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  let h = 0;
  const l = (max + min) / 2;
  const d = max - min;
  const s = d === 0 ? 0 : d / (1 - Math.abs(2 * l - 1));
  if (d) {
    if (max === r) h = ((g - b) / d) % 6;
    else if (max === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
  }
  h = (h * 60 + 360) % 360;
  const s2 = Math.min(1, s + 0.35), l2 = Math.max(0.3, l - 0.25);
  const c = (1 - Math.abs(2 * l2 - 1)) * s2, x = c * (1 - Math.abs(((h / 60) % 2) - 1)), m = l2 - c / 2;
  [r, g, b] = h < 60 ? [c, x, 0] : h < 120 ? [x, c, 0] : h < 180 ? [0, c, x]
    : h < 240 ? [0, x, c] : h < 300 ? [x, 0, c] : [c, 0, x];
  return "#" + [r, g, b].map((v) => Math.round((v + m) * 255).toString(16).padStart(2, "0")).join("");
}

async function json(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
}

export async function loadData() {
  const [wl, wlic, jl, jlic, eq] = await Promise.all([
    json("../data/waxholm/labels.json"),
    json("../data/waxholm/licence.json"),
    json("../data/julich/labels.json"),
    json("../data/julich/licence.json"),
    json("../data/equivalencias.json"),
  ]);
  return {
    waxholm: { labels: wl, licence: wlic },
    julich: { labels: jl, licence: jlic },
    pairs: eq.pairs,
  };
}

// A region, whichever viewer picked it: {atlas, side, id, name, acronym?, label?, areaId?, path?}
export function regionFromRow(atlas, row, data) {
  if (atlas === "waxholm") {
    return { atlas, side: row.side, id: row.id, name: row.name, acronym: row.acronym, path: row.path };
  }
  return { atlas, side: row.side, id: row.id, name: row.name, label: row.label, areaId: row.area_id };
}

// The test pair a region belongs to, if any. Waxholm matches through its ancestors (a click on
// CA1 belongs to the HF pair); Julich-Brain through the area without side.
export function pairOf(region, pairs) {
  if (region.atlas === "waxholm") {
    const path = region.path || [region.id];
    return pairs.find((p) => path.includes(p.waxholm.id)) || null;
  }
  return pairs.find((p) => p.julich.some((j) => j.area_id === region.areaId)) || null;
}

// What the other viewer has to highlight: {atlas, side, waxholmId} or {atlas, side, areaIds}.
export function partnerOf(region, pair) {
  if (!pair) return null;
  if (region.atlas === "waxholm") {
    return { atlas: "julich", side: region.side, areaIds: pair.julich.map((j) => j.area_id) };
  }
  return { atlas: "waxholm", side: region.side, waxholmId: pair.waxholm.id };
}

function el(tag, attrs = {}, ...children) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v;
    else e.setAttribute(k, v);
  }
  for (const c of children) e.append(c);
  return e;
}

export function renderPanel(box, region, pairs) {
  box.replaceChildren();
  if (!region) {
    box.append(el("p", { class: "muted" }, t.none));
    return;
  }
  const title = region.acronym ? `${region.name} (${region.acronym})` : region.name;
  box.append(el("h3", {}, title));
  const facts = el("p", { class: "facts" });
  facts.append(`${t.side[region.side] || ""} · ${t.id}: `, el("code", {}, String(region.id)));
  if (region.label != null) facts.append(` · ${t.mpmLabel}: ${region.label}`);
  box.append(facts);
  const pair = pairOf(region, pairs);
  if (!pair) {
    box.append(el("p", { class: "muted" }, t.noPair));
    return;
  }
  const other =
    region.atlas === "waxholm"
      ? pair.julich.map((j) => j.name).join(", ")
      : `${pair.waxholm.name} (${pair.waxholm.acronym})`;
  const p = el("p", { class: "pair" }, `${t.equivalent}: ${other} · ${t.side[region.side]}. `);
  p.append(el("span", { class: "grade" }, `${t.grade}: ${pair.grade}`));
  box.append(p);
}

export function renderLicence(box, lic) {
  box.replaceChildren(
    el("strong", {}, lic.short),
    " · ",
    `${t.licence}: `,
    el("a", { href: lic.licence_url, rel: "license" }, lic.licence),
    " · ",
    el("a", { href: lic.source_url }, t.source),
    el("br"),
    `${t.cite}: ${lic.citation}`,
    el("br"),
    `${t.changes}: ${t.changesText}`,
    ...(palette === "calm" ? [el("br"), t.coloursCalm] : []),
  );
}

// Fills the static texts of the page (data-t="key").
export function fillTexts() {
  for (const n of document.querySelectorAll("[data-t]")) n.textContent = t[n.dataset.t];
  const a = document.getElementById("lang");
  if (a) {
    a.textContent = t.other;
    a.href = t.otherHref;
  }
}

// Measurements read by the spike (results/maqueta-*.md): when both viewers can be used.
const ready = new Set();
export function markReady(atlas) {
  ready.add(atlas);
  if (ready.size === 2) {
    performance.mark("s3-interactive");
    window.__s3 = { interactiveMs: Math.round(performance.getEntriesByName("s3-interactive")[0].startTime) };
    document.body.dataset.ready = "1";
  }
}
