// Spike S3: shared helpers of mock-up C (Niivue); mock-up B was removed. Throwaway code.
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
    libsC: "Niivue (BSD-2-Clause), servido desde esta web:",
    licences: "licencias",
    view3d: "Solo 3D",
    view3dSlice: "3D + corte",
    clip: "Recortar",
    modes: "Modo de vista",
    modeColor: "Color",
    modeAtlas: "Atlas",
    modeStain: "Tinción",
    stainKind: "Tipo de tinción",
    stainDrawn: "Dibujada",
    stainReal: "Real",
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
    libsC: "Niivue (BSD-2-Clause), served from this site:",
    licences: "licences",
    view3d: "3D only",
    view3dSlice: "3D + slice",
    clip: "Cut away",
    modes: "View mode",
    modeColor: "Colour",
    modeAtlas: "Atlas",
    modeStain: "Stain",
    stainKind: "Kind of stain",
    stainDrawn: "Drawn",
    stainReal: "Real",
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

// Human layers, in order (Sofía's review): each one only labels what the ones before leave empty
// (spikes/s3/layers.py). Julich-Brain is the base.
const HUMAN_LAYERS = ["cerebra", "cit168", "icbm_wm"];

export async function loadData() {
  const [wl, wlic, jl, jlic, eq, ...layers] = await Promise.all([
    json("../data/waxholm/labels.json"),
    json("../data/waxholm/licence.json"),
    json("../data/julich/labels.json"),
    json("../data/julich/licence.json"),
    json("../data/equivalencias.json"),
    ...HUMAN_LAYERS.map((n) =>
      Promise.all([json(`../data/${n}/labels.json`), json(`../data/${n}/licence.json`)])),
  ]);
  // One human brain, several label files: the rows of each layer go after the ones before, so
  // the viewer reads value k of a layer as row k + from - 1 (c.js, VolumeViewer.load). The files
  // stay apart (licences); they only meet here, on screen.
  const rows = jl.rows.map((r) => ({ ...r, source: r.index ? "julich" : null }));
  const extras = [];
  HUMAN_LAYERS.forEach((name, i) => {
    const [labels, licence] = layers[i];
    const from = rows.length;
    rows.push(...labels.rows.slice(1).map((r) => ({ ...r, index: r.index + from - 1, source: name })));
    extras.push({ name, url: `../data/${name}/labels.nii.gz`, from, licence });
  });
  return {
    waxholm: { labels: wl, licence: wlic },
    julich: { labels: { ...jl, rows }, licence: jlic, extras },
    pairs: eq.pairs,
  };
}

// A region, whichever viewer picked it: {atlas, side, id, name, acronym?, label?, areaId?, path?}
export function regionFromRow(atlas, row, data) {
  if (atlas === "waxholm") {
    return { atlas, side: row.side, id: row.id, name: row.name, acronym: row.acronym, path: row.path };
  }
  return {
    atlas, side: row.side, id: row.id, name: row.name, label: row.label, areaId: row.area_id,
    source: row.source,
  };
}

// The test pair a region belongs to, if any. Waxholm matches through its ancestors (a click on
// CA1 belongs to the HF pair); Julich-Brain through the area without side.
export function pairOf(region, pairs) {
  if (region.atlas === "waxholm") {
    const path = region.path || [region.id];
    return pairs.find((p) => path.includes(p.waxholm.id)) || null;
  }
  return pairs.find((p) => p.human.some((j) => j.area_id === region.areaId)) || null;
}

// What the other viewer has to highlight: {atlas, side, waxholmId} or {atlas, side, areaIds}.
export function partnerOf(region, pair) {
  if (!pair) return null;
  if (region.atlas === "waxholm") {
    return { atlas: "julich", side: region.side, areaIds: pair.human.map((j) => j.area_id) };
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

export function renderLicence(box, lic, { colours = true } = {}) {
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
    ...(colours && palette === "calm" ? [el("br"), t.coloursCalm] : []),
  );
}

// Fills the static texts of the page (data-t="key").
export function fillTexts() {
  for (const n of document.querySelectorAll("[data-t]")) n.textContent = t[n.dataset.t];
  for (const n of document.querySelectorAll("[data-t-label]")) n.setAttribute("aria-label", t[n.dataset.tLabel]);
  for (const n of document.querySelectorAll("[data-t-title]")) n.title = t[n.dataset.tTitle];
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
    window.__s3 = { ...window.__s3, interactiveMs: Math.round(performance.getEntriesByName("s3-interactive")[0].startTime) };
    document.body.dataset.ready = "1";
  }
}
