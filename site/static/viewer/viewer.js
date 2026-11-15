// Neuro Atlas viewer (Phase 2, SCOPE v163). Copied from spikes/s3/site/c/c.js and
// spikes/s3/site/common/common.js (spike S3, mock-up C, chosen by Sofía; ADR D3) and adapted to
// the atlas page (site/templates/atlas.html.j2): data from static/atlas/, texts in the page's
// language, and the controls of the UX study (docs/fases/fase-2-atlas-ux.md): both brains on a
// wide screen and one with a switch on a phone (UX-1 C); only the search, «Recortar» and «Más
// opciones» in view, the last choice remembered (UX-3 B); the other brain marks the counterpart
// without moving, and «Ir a la pareja» takes it there (UX-4 B); the page first and the viewer
// after it, over the still image (UX-5 B). The Niivue 0.69 patches of the prototype are kept,
// each with its comment: upgrading Niivue means repeating the touch tests of S3 (ADR D3).
//
// Niivue is loaded here, as a classic script, once the page has loaded: global `niivue`.
const root = document.querySelector("[data-atlas-viewer]");
const lang = document.documentElement.lang === "en" ? "en" : "es";
const DATA = root ? root.dataset.atlasViewer.replace(/\/$/, "") : ""; // static/atlas
// Region pages (step 5): viewer key of the area → its page, relative to the atlas page.
const REGION_PAGES = root ? JSON.parse(root.dataset.regionPages || "{}") : {};
let Niivue, NVImage, SLICE_TYPE;

// Background of the 3D view: the page's --atlas-bg, so it follows the light and dark themes.
function backColour() {
  const c = getComputedStyle(document.documentElement).getPropertyValue("--atlas-bg").trim();
  const n = parseInt((/^#[0-9a-f]{6}$/i.test(c) ? c : "#101a33").slice(1), 16);
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255, 1];
}
// Step 7.3 (Sofía, P2): a true side view, no diagonal. Azimuth 90 looks at the left side.
const AZIMUTH = 90;
// Step 7.9: the 3D is a ray cast per pixel, so its cost grows with the canvas resolution. On an
// emulated phone (software WebGL, CPU x4) spinning went 3 fps at DPR 3, 6 at 2, 10 at 1.5 and 22
// at 1 (results/maqueta-c.md); on a real phone 1.5 felt a little smoother than 2 and no less sharp
// (Aday). Touch devices are capped at MOBILE_DPR; desktops keep theirs. ?dpr=N forces a ratio.
const MOBILE_DPR = 1.5;
const APPLY_PAUSE = 150; // ms without moving a slider before the highlight is repainted
function pixelRatio() {
  const forced = Number(new URLSearchParams(location.search).get("dpr"));
  if (forced > 0) return forced;
  const device = window.devicePixelRatio || 1;
  return matchMedia("(pointer: coarse)").matches ? Math.min(device, MOBILE_DPR) : 0; // 0 = device
}
// Niivue 0.69 lifts every value above the scale minimum to at least 2/256 of the colour table
// (its issue 1139): with ~450 labels, background and the first labels all land on entry 3-4,
// opaque. So, in this viewer only, labels move up by OFFSET when the volume is loaded: entries
// 0..OFFSET-1 are left empty and transparent. Data files keep the plain indices.
// With the atlas mode's edge labels (step 7.6) the table doubles (~900 entries, lift ~7), so 16.
const OFFSET = 16;
const ELEVATION = 0;
// The cut is always sagittal (P2). Niivue's clip plane is dot(n, p - 0.5) + depth = 0 in volume
// fractions, with n from (azimuth + 180, elevation): for azimuth 270 and elevation 0, n = +x, so
// the plane sits at x = 0.5 - depth and the part on the camera's side (left) is cut away.
// Niivue's own drag in 3D rotates the plane, so it is not used.
const CLIP_AZIMUTH = 270;
const clipAt = (fx) => [0.5 - fx, CLIP_AZIMUTH, 0];

// Step 7.3 (P1): the 3D cut (sagittal) and the 2D slice (coronal) are perpendicular, so they share
// a point, Niivue's crosshair: its x is the sagittal cut, its y the coronal slice, its z the height
// of the crosshair. Clicking the slice or the 3D cut face moves the point too. Of the two variants
// tried, Aday kept the sliders (2026-11-11), with the exact millimetre typed on the keyboard and
// a third axis, z.
const TXT = {
  es: { x: "Sagital · x (3D)", y: "Coronal · y (2D)", z: "Vertical · z", mm: "mm" },
  en: { x: "Sagittal · x (3D)", y: "Coronal · y (2D)", z: "Vertical · z", mm: "mm" },
}[lang];

// Step 7.5 (P7): what the millimetres mean. The viewer works in each volume's own frame (RAS, mm,
// centred on the brain); coords.json maps it to what is shown: mm from Bregma for the rat (from
// a published table, see spikes/s3/coords.py) and MNI mm for the human.
const FRAME = {
  es: {
    bregma: {
      axes: { x: "ML · x (3D)", y: "AP · y (2D)", z: "DV · z" },
      title: "Milímetros desde Bregma",
      lambda: (ap, deg) =>
        `Cráneo plano: el atlas se ha girado ${deg}° para dejar Lambda a la altura de Bregma, a ${ap} mm (AP).`,
      approx: "Son las coordenadas del animal del atlas: en otra rata, aproximadas.",
      source: "Bregma y Lambda: tabla de",
      cite: "Papp y Bjaalie (2014)",
      slice: (b, l) => `Bregma ${b} mm · Lambda ${l} mm`,
    },
    mni: {
      axes: { x: "Sagital · x (3D)", y: "Coronal · y (2D)", z: "Vertical · z" },
      title: "Milímetros del espacio MNI152 (2009c)",
      source: "Espacio:",
      cite: "ICBM 152 2009c no lineal asimétrico",
      slice: (y) => `y = ${y} mm (MNI)`,
    },
  },
  en: {
    bregma: {
      axes: { x: "ML · x (3D)", y: "AP · y (2D)", z: "DV · z" },
      title: "Millimetres from Bregma",
      lambda: (ap, deg) =>
        `Flat skull: the atlas is turned ${deg}° so that Lambda is at Bregma's height, ${ap} mm (AP) away.`,
      approx: "These are the coordinates of the atlas animal: approximate for any other rat.",
      source: "Bregma and Lambda: table by",
      cite: "Papp and Bjaalie (2014)",
      slice: (b, l) => `Bregma ${b} mm · Lambda ${l} mm`,
    },
    mni: {
      axes: { x: "Sagittal · x (3D)", y: "Coronal · y (2D)", z: "Vertical · z" },
      title: "Millimetres in MNI152 space (2009c)",
      source: "Space:",
      cite: "ICBM 152 2009c nonlinear asymmetric",
      slice: (y) => `y = ${y} mm (MNI)`,
    },
  },
}[lang];
// Number fields: plain dot decimals, and no "-0.00".
const fixed2 = (x) => (Math.abs(x) < 0.005 ? 0 : x).toFixed(2);
const fmt = (x, d = 2) =>
  new Intl.NumberFormat(lang === "es" ? "es-ES" : "en-GB", {
    minimumFractionDigits: d, maximumFractionDigits: d, signDisplay: "exceptZero",
  }).format(Math.abs(x) < 0.5 * 10 ** -d ? 0 : x);

const SEARCH = {
  es: { none: "Sin resultados", rat: "rata", human: "humano" },
  en: { none: "No results", rat: "rat", human: "human" },
}[lang];

// Step 7.4 (P3, P6): the card under each brain (UX-2 C: the short card; the full region page
// comes later).
const P = {
  es: {
    none: "Ninguna región seleccionada.",
    nonePoint: "Ninguna región en el punto.",
    side: { L: "hemisferio izquierdo", R: "hemisferio derecho" },
    both: "ambos hemisferios",
    id: "ID",
    mpm: "etiqueta del mapa",
    atlas: "atlas",
    origName: "Nombre original del atlas, en inglés: la traducción la revisa Sofía.",
    grades: { clear: "clara", partial: "parcial", disputed: "discutida" },
    gradePending: "pendiente de Sofía",
    goPair: "Ir a la pareja",
    page: "Ficha completa de la región",
    marked: "Pareja marcada; este cerebro no se ha movido.",
    pairOf: "Pareja de",
    inOther: "En el otro cerebro",
    grade: "grado",
    noPairHere: "sin pareja todavía en el otro cerebro.",
    noPairThere: (n) => `${n} aún no tiene pareja en este cerebro.`,
    rat: "rata",
    human: "humano",
  },
  en: {
    none: "No region selected.",
    nonePoint: "No region at the point.",
    side: { L: "left hemisphere", R: "right hemisphere" },
    both: "both hemispheres",
    id: "ID",
    mpm: "map label",
    atlas: "atlas",
    origName: null,
    grades: { clear: "clear", partial: "partial", disputed: "disputed" },
    gradePending: "pending Sofía's review",
    goPair: "Go to the counterpart",
    page: "Full page of the region",
    marked: "Counterpart marked; this brain has not moved.",
    pairOf: "Counterpart of",
    inOther: "In the other brain",
    grade: "grade",
    noPairHere: "no counterpart yet in the other brain.",
    noPairThere: (n) => `${n} has no counterpart in this brain yet.`,
    rat: "rat",
    human: "human",
  },
}[lang];

// Name and short name of a region. Waxholm gives an acronym; for Julich-Brain the short name is
// the part before the brackets ("CA1 (Hippocampus)" → "CA1"). The short name carries a stable
// data-glossary key, so Neuro Glossary (Phase 2) can attach its definition to it.
function names(region) {
  const short = region.acronym || region.name.split(" (")[0];
  return { full: region.name, short };
}

// Search text: lower case, no accents.
const fold = (x) => x.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();

// Improvement M1: best matches first (exact short name, short name start, name start, anywhere).
function search(items, query, max = 8) {
  const q = fold(query);
  if (!q) return [];
  const rank = (it) => (it.s === q ? 0 : it.s.startsWith(q) ? 1 : it.f.startsWith(q) ? 2
    : it.f.includes(q) || it.s.includes(q) ? 3 : 9);
  return items
    .map((it) => [rank(it), it])
    .filter(([r]) => r < 9)
    .sort((a, b) => a[0] - b[0] || a[1].full.length - b[1].full.length || a[1].full.localeCompare(b[1].full))
    .slice(0, max)
    .map(([, it]) => it);
}

function h(tag, attrs = {}, ...children) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  e.append(...children);
  return e;
}

function abbr(region) {
  const n = names(region);
  return h("abbr", { "data-glossary": n.short, title: n.full }, n.short);
}

function title(region) {
  const n = names(region);
  return n.short === n.full ? h("h3", {}, abbr(region)) : h("h3", {}, abbr(region), " · ", n.full);
}

const ATLAS_NAME = {
  julich: "Julich-Brain v3.1", cerebra: "CerebrA", cit168: "CIT168", icbm_wm: "ICBM152 2009c",
};

function facts(region) {
  const p = h("p", { class: "facts" }, `${P.side[region.side] || P.both} · ${P.id}: `);
  p.append(h("code", {}, String(region.id)));
  if (region.label != null) p.append(` · ${P.mpm}: ${region.label}`);
  // Sofía's review: the human brain has two atlases, so say which one this region comes from.
  if (region.source) p.append(` · ${P.atlas}: ${ATLAS_NAME[region.source]}`);
  return p;
}

// The panel of the viewer that was clicked.
function panelPicked(box, region, pair, empty = P.none) {
  box.replaceChildren();
  if (!region) return box.append(h("p", { class: "muted" }, empty));
  box.append(title(region), facts(region));
  if (!pair) {
    box.append(h("p", { class: "muted" }, abbr(region), ": ", P.noPairHere));
  } else {
    const other = region.atlas === "waxholm"
      ? pair.human.map((j) => j.name).join(", ")
      : `${pair.waxholm.name} (${pair.waxholm.acronym})`;
    const p = h("p", { class: "pair" }, `${P.inOther}: ${other}. `);
    p.append(h("span", { class: "grade" }, `${P.grade}: ${gradeOf(pair)}`));
    box.append(p);
    // Step 5: the regions of the pairs have their own page (the rat's, by the pair's node).
    const page = REGION_PAGES[region.atlas === "waxholm" ? `w${pair.waxholm.id}` : `j${region.areaId}`];
    if (page) box.append(h("p", {}, h("a", { href: page }, `${P.page} →`)));
  }
  if (P.origName) box.append(h("p", { class: "muted small" }, P.origName));
}

// The panel of the other viewer: what was selected there on its behalf, or why nothing was.
// The grade is Sofía's: shown as she sets it, «pending» until then; never computed here.
const gradeOf = (pair) => (pair.grade ? P.grades[pair.grade] || pair.grade : P.gradePending);

function panelPartner(box, source, pair, onGo = () => {}) {
  box.replaceChildren();
  if (!source) return box.append(h("p", { class: "muted" }, P.none));
  const species = source.atlas === "waxholm" ? P.rat : P.human;
  if (!pair) {
    box.append(h("p", { class: "muted" }, P.noPairThere(`${names(source).short} (${species})`)));
    return;
  }
  const shown = source.atlas === "waxholm"
    ? pair.human.map((j) => ({ name: j.name, id: j.area_id }))
    : [{ name: pair.waxholm.name, acronym: pair.waxholm.acronym, id: pair.waxholm.id }];
  const head = h("h3", {}, `${P.pairOf} `, abbr(source), ` (${species})`);
  const list = h("p", {});
  shown.forEach((r, i) => {
    if (i) list.append(", ");
    list.append(abbr(r));
    const n = names(r);
    // Waxholm: "M1 · Primary motor area"; Julich-Brain: "CA1 (Hippocampus)", the rest of the name.
    if (n.short !== n.full) {
      list.append(r.acronym ? ` · ${n.full}` : ` ${n.full.slice(n.short.length).trim()}`);
    }
  });
  list.append(` · ${P.side[source.side] || P.both}`);
  const g = h("p", { class: "pair" }, h("span", { class: "grade" }, `${P.grade}: ${gradeOf(pair)}`));
  // UX-4 B: this brain marks the counterpart but does not turn; the button takes it there.
  const go = h("button", { type: "button", class: "btn go-pair" }, P.goPair);
  go.addEventListener("click", () => onGo());
  box.append(head, list, g, h("p", { class: "muted small" }, P.marked, " "), go);
  if (P.origName) box.append(h("p", { class: "muted small" }, P.origName));
}

// Step 7.6 (P4): one way of looking at a time. "color": the calm palette; "atlas": black and
// white, grey fill and contours, like a printed atlas plate; "stain": a drawn Nissl-like stain
// (step 7.7), always with the notice that it is an illustration.
const MODES = ["color", "atlas", "stain"];
// UX-4 C (Aday, 2026-11-15, SCOPE v165): while a region is selected, the rest of the brain is
// see-through (opacity SEE_THROUGH of 255), so inner regions show without cutting; it turns solid
// again when the selection goes. 4 was the lowest that still shows the brain's shape (step 4
// trial); it costs smoothness while turning (21 → 7 fps on the simulated phone). ?ver=N (0-255)
// overrides it, to compare on a real phone; ?ver=255 is the solid grey of UX-4 B.
const SEE_THROUGH = (() => {
  const q = new URLSearchParams(location.search);
  const n = Number(q.get("ver"));
  return q.has("ver") && n >= 0 && n <= 255 ? n : 4;
})();
// UX-3 B: the last choice of «Más opciones» is remembered in this browser (and only there).
const STORE = "synaptica-atlas-view";
function remembered() {
  try {
    return JSON.parse(localStorage.getItem(STORE)) || {};
  } catch {
    return {};
  }
}
const saved = remembered();
const state = {
  view: saved.view === "slice" ? "slice" : "3d",
  clip: saved.view === "slice", // the 3D cut and the 2D slice go together (P1)
  isolate: saved.isolate === true,
  mode: MODES.includes(saved.mode) ? saved.mode : "color",
  // Step 7.8: inside "stain", the drawn one or real histology where there is some.
  stain: saved.stain === "real" ? "real" : "drawn",
};
function remember() {
  try {
    const { view, isolate, mode, stain } = state;
    localStorage.setItem(STORE, JSON.stringify({ view, isolate, mode, stain }));
  } catch {
    // private mode: nothing is remembered
  }
}
// Step 7.8: real stains, one folder and licence each (results/tincion.md). Rat: none found that
// fits (backlog), so the rat keeps the drawn one and says so.
const REAL_STAIN = { julich: `${DATA}/bigbrain` };
// Sofía's review: the rat has real Nissl sections, not a volume, so only the 2D slice shows them
// (spikes/s3/nissl.py): the section nearest the slice, with how far it is.
const REAL_SLICE = { waxholm: `${DATA}/nissl` };
// Atlas mode: fill grey from the lightness of the region's colour, kept light so the contours
// read; the selection and its counterpart, darker. Contours, almost black.
const GREY = { lo: 175, hi: 238, focus: 125, edge: 40 };

// Step 7.7 (P4): drawn stain, Nissl-like (cresyl violet). How dark a region stains is a drawing
// choice by family and a few names (cell-dense layers dark, white matter and molecular layers
// pale), not a measurement: the canvas says so. Slide and ink colours, and density 0..1.
const STAIN = {
  slide: [247, 243, 247],
  ink: [70, 36, 118],
  family: {
    cortex: 0.6, cortex_gap: 0.55, hippocampus: 0.75, olfactory: 0.65, amygdala: 0.6,
    basal_ganglia: 0.5, thalamus: 0.55, hypothalamus: 0.6, midbrain: 0.5, hindbrain: 0.48,
    white_matter: 0.1, ventricles: 0, other: 0.35,
  },
  names: [
    [/molecular|layer 1\b/i, 0.22],
    // CerebrA's cerebellar grey matter and vermis are mostly granular layer, like the rat's
    // "Cerebellum, unspecified".
    [/dentate gyrus|^DG |granule cell layer|granular layer|layer 2\b|cerebellum, unspecified|cerebellum gray matter|vermal lobules/i, 0.9],
    [/glomerular/i, 0.35],
  ],
};
const NOTICE = {
  es: {
    drawn: "Ilustración, no es una tinción real",
    noReal: "Ilustración, no es una tinción real (no hay de rata)",
    real: "Tinción real de otro cerebro (BigBrain)",
    real3dRat: "Ilustración: la tinción real de rata solo está en el corte 2D",
    realSlice: (d) => `Nissl real de otra rata · corte a ${d} mm de este plano`,
    realSliceLoading: "Cargando el corte real…",
  },
  en: {
    drawn: "Illustration, not a real stain",
    noReal: "Illustration, not a real stain (none for the rat)",
    real: "Real stain of another brain (BigBrain)",
    real3dRat: "Illustration: the rat's real stain is only on the 2D slice",
    realSlice: (d) => `Real Nissl of another rat · section ${d} mm from this plane`,
    realSliceLoading: "Loading the real section…",
  },
}[lang];

// Deterministic noise in [0, 1) for integer cells, so the drawn grain does not flicker.
function hash2(i, j) {
  let x = Math.imul(i, 374761393) + Math.imul(j, 668265263);
  x = Math.imul(x ^ (x >>> 13), 1274126177);
  return ((x ^ (x >>> 16)) >>> 0) / 4294967296;
}

const mix = (a, b, t) => a.map((v, k) => Math.round(v + (b[k] - v) * t));

function greyOf(rgb) {
  const l = (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255; // ~0.65-0.92 in calm
  const t = Math.min(1, Math.max(0, (l - 0.6) / 0.35));
  const g = Math.round(GREY.lo + t * (GREY.hi - GREY.lo));
  return [g, g, g];
}

function hex(c) {
  const n = parseInt((c || "#888888").slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

class VolumeViewer {
  constructor(section, atlas, rows, extras = []) {
    this.atlas = atlas;
    this.extras = extras; // human: further label layers, laid under Julich-Brain's (loadData)
    this.section = section;
    this.rows = rows;
    this.canvas = section.querySelector("canvas");
    this.panel = section.querySelector(".panel");
    this.focus = new Set(); // row indices shown at full strength
    this.selectedIndex = null;
    this.n = rows.length; // atlas mode: the edge voxels of region r hold r + n (step 7.6)
    this.edges = null; // set the first time the atlas mode is chosen
    this.onPick = () => {};
    this.nv = null; // made in load(), once Niivue is there (UX-5 B)
  }

  async load(url) {
    this.nv = new Niivue({
      backColor: backColour(),
      show3Dcrosshair: false, // on in "3D + slice": the 3D view shows where the 2D slice is
      isColorbar: false,
      dragAndDropEnabled: false,
      loadingText: "",
      crosshairColor: [1, 0.85, 0.2, 1],
      crosshairWidth: 1,
      isOrientCube: false,
      clipPlaneColor: [0, 0, 0, 0], // cut without drawing the plane
      logLevel: "error",
      forceDevicePixelRatio: pixelRatio(),
    });
    await this.nv.attachToCanvas(this.canvas);
    this.nv.setInterpolation(true); // nearest neighbour: labels must not blend
    // Step 4: the bytes were asked for together with Niivue (prefetch), not after it.
    const name = url.split("/").pop();
    this.nv.addVolume(await NVImage.loadFromUrl({ url, name, buffer: await prefetch(url) }));
    this.vol = this.nv.volumes[0];
    const img = this.vol.img;
    // Sofía's review: where Julich-Brain has no label, the next layer's, and so on (same grid;
    // built so that they never overlap). Done in memory, on screen: the files stay apart.
    // Step 4: a layer marked `late` (the white matter, the heaviest) joins once the brain can
    // already be used; the others before. In atlas mode all join first (its contours need them).
    const now = this.extras.filter((x) => !x.late || state.mode === "atlas");
    const late = this.extras.filter((x) => !now.includes(x));
    // Niivue reads the format from the name's extension (.nii.gz).
    const layer = async (x) => NVImage.loadFromUrl({ url: x.url, name: `${x.name}.nii.gz`, buffer: await prefetch(x.url) });
    const join = (x, ex) => {
      if (ex.img.length !== img.length) throw new Error(`${x.name}: other grid`);
      const add = x.from - 1 + OFFSET; // joins after the lift: the base is lifted already
      for (let i = 0; i < img.length; i++) if (!img[i] && ex.img[i]) img[i] = ex.img[i] + add;
    };
    (await Promise.all(now.map(layer))).forEach((ex, k) => {
      const x = now[k];
      if (ex.img.length !== img.length) throw new Error(`${x.name}: other grid`);
      for (let i = 0; i < img.length; i++) if (!img[i] && ex.img[i]) img[i] = ex.img[i] + x.from - 1;
    });
    for (let i = 0; i < img.length; i++) if (img[i]) img[i] += OFFSET;
    this.vol.calMinMax();
    this.lateDone = !late.length;
    if (late.length) {
      Promise.all(late.map(layer)).then((exs) => {
        exs.forEach((ex, k) => join(late[k], ex)); // values already lifted by OFFSET here
        this.vol.calMinMax();
        this.lateDone = true;
        this.apply();
      }).catch((e) => console.error(e));
    }
    this.coords = JSON.parse(new TextDecoder().decode(await prefetch(`${DATA}/${this.atlas}/coords.json`)));
    this.nv.setRenderAzimuthElevation(AZIMUTH, ELEVATION);
    this.nv.onLocationChange = (loc) => {
      this.syncPlanes();
      this.picked(loc);
    };
    this.buildSliders();
    this.buildAxes();
    // Name of the region next to the point that was clicked (P6).
    this.tag = h("div", { class: "tag" });
    this.tag.hidden = true;
    this.section.querySelector(".stage").append(this.tag);
    this.singleClickPicks();
    this.apply();
  }

  // UX-4 C, Aday's refinements (v169–v171): with a region selected, the rest of the brain is
  // see-through, also while it is turned to look from another angle; while it is zoomed or its
  // point moved it is solid, see-through again once let go. With the cut on as well: the cut
  // goes through the region picked in this brain, not through the counterpart marked in the
  // other, which stays inside (UX-4 B). Turning see-through costs speed (21 → 7 fps on the
  // simulated phone).
  get seeThrough() {
    return SEE_THROUGH < 255 && !this.busy && !state.isolate;
  }

  setBusy(on) {
    if (Boolean(this.busy) === on) return;
    const before = this.seeThrough;
    this.busy = on;
    if (this.vol && this.focus.size && before !== this.seeThrough) this.apply();
  }

  // The same 3D tap again, once the brain is drawn solid (UX-4 C, see picked).
  tapAgain(at) {
    this.retrying = true;
    requestAnimationFrame(() => requestAnimationFrame(() => {
      const box = this.canvas.getBoundingClientRect();
      const dpr = this.nv.uiData.dpr || 1;
      this.nv.mousePos = [(at.clientX - box.left) * dpr, (at.clientY - box.top) * dpr];
      this.lastClick = { x: at.clientX - box.left, y: at.clientY - box.top };
      this.tapFrom = [...this.nv.scene.crosshairPos];
      this.canvas.dispatchEvent(new MouseEvent("dblclick", { ...at, bubbles: true }));
      this.retrying = false;
    }));
  }

  // In the 3D view Niivue only reads the voxel under the pointer (depth picking) on a double
  // click, double tap or long press. To behave like B, a short click that barely moves sends it
  // the double click it listens for. 2D slices already pick on a single click.
  singleClickPicks() {
    let down = null;
    // Where the press was, for the name tag: Niivue reports a 2D click on press, a 3D one on
    // the double click sent below. A drag (rotating, moving the slice) hides the tag.
    const at = (e) => {
      const box = this.canvas.getBoundingClientRect();
      return { x: e.clientX - box.left, y: e.clientY - box.top };
    };
    // Step 7.9 (real phone): Niivue keeps the pointer position (nv.mousePos) from mouse moves, and
    // a finger sends none between gestures. So a tap picked at the end of the previous gesture
    // (often background: "the tap did not register"), and the first move of a new drag turned by
    // the whole jump from there (the brain "reset" upside down). The press sets it first.
    // A finger also wobbles more than a mouse: SLOP CSS px still count as a tap.
    const SLOP = (e) => (e.pointerType === "mouse" ? 6 : 12);
    const fingers = new Set(); // pointers down on the canvas: two or more are a pinch
    this.canvas.addEventListener("pointerdown", (e) => {
      fingers.add(e.pointerId);
      const box = this.canvas.getBoundingClientRect();
      const px = this.nv.uiData.dpr || 1;
      // Turning is a one-finger drag on the 3D view; on the 2D slice a drag moves the point.
      const turning = this.nv.inRenderTile((e.clientX - box.left) * px, (e.clientY - box.top) * px) >= 0;
      down = { x: e.clientX, y: e.clientY, t: performance.now(), slop: SLOP(e), turning };
      this.lastClick = at(e);
      const dpr = this.nv.uiData.dpr || 1;
      this.nv.mousePos = [this.lastClick.x * dpr, this.lastClick.y * dpr];
    });
    this.canvas.addEventListener("pointermove", (e) => {
      if (down && Math.hypot(e.clientX - down.x, e.clientY - down.y) > down.slop) {
        this.tag.hidden = true;
        // Aday (v171): turning keeps the see-through; zooming (a pinch) or moving the point on
        // the 2D slice makes the brain solid until it is let go.
        if (!down.turning || fingers.size > 1) this.setBusy(true);
      }
    });
    this.canvas.addEventListener("pointercancel", (e) => {
      fingers.delete(e.pointerId);
      down = null;
      this.setBusy(false);
    });
    // Zooming with the wheel: solid while the wheel turns, see-through again a moment after.
    this.canvas.addEventListener("wheel", () => {
      this.setBusy(true);
      clearTimeout(this.wheelTimer);
      this.wheelTimer = setTimeout(() => this.setBusy(false), 300);
    }, { passive: true });
    // A drag that ends outside the canvas (the mouse let go beyond its edge) ends too.
    addEventListener("pointerup", (e) => {
      fingers.delete(e.pointerId);
      down = null;
      this.setBusy(false);
    });
    this.canvas.addEventListener("pointerup", (e) => {
      this.setBusy(false);
      if (!down) return;
      const quick = performance.now() - down.t < 600;
      const still = Math.hypot(e.clientX - down.x, e.clientY - down.y) <= down.slop;
      down = null;
      if (!quick || !still) return;
      this.upAt = performance.now(); // step 4: start of the tap's timing (picked)
      // Aday (v167): Niivue's 3D pick leaves the point where it was when the ray hits no
      // tissue, and still reports the region there. Where the point was, to tell (picked).
      const r = this.canvas.getBoundingClientRect();
      const dpr = this.nv.uiData.dpr || 1;
      if (this.nv.inRenderTile((e.clientX - r.left) * dpr, (e.clientY - r.top) * dpr) < 0) return;
      this.tapFrom = [...this.nv.scene.crosshairPos]; // 3D only: a 2D click always moves it
      this.lastTap = { clientX: e.clientX, clientY: e.clientY };
      this.canvas.dispatchEvent(
        new MouseEvent("dblclick", { clientX: e.clientX, clientY: e.clientY, bubbles: true }),
      );
    });
  }

  colormap() {
    const R = [], G = [], B = [], A = [], I = [], labels = [];
    const atlas = state.mode === "atlas";
    // Edge entries (index + n) exist once the edges have been marked; in colour mode they take
    // the region's own colour, so the marks do not show.
    for (const edge of this.edges ? [false, true] : [false]) {
      for (const r of this.rows) {
        if (edge && !r.index) continue;
        const focused = r.index && this.focus.has(r.index);
        let rgb = r.index ? hex(focused ? strong(colourOf(r)) : colourOf(r)) : [0, 0, 0];
        let a = r.index ? 255 : 0;
        if (atlas && r.index) {
          rgb = edge ? [GREY.edge, GREY.edge, GREY.edge]
            : focused ? [GREY.focus, GREY.focus, GREY.focus] : greyOf(hex(colourOf(r)));
        }
        if (state.mode === "stain" && r.index && !focused) {
          rgb = mix(STAIN.slide, STAIN.ink, this.stainDensity()[r.index]);
          if (this.realOn) a = 0; // the histology shows through; only the selection is coloured
        }
        // While something is selected the rest goes grey (alpha barely shows in the 3D render
        // of a label volume), or disappears when isolating.
        if (r.index && this.focus.size && !focused) {
          if (state.mode === "color") {
            const grey = Math.round(0.15 * (rgb[0] + rgb[1] + rgb[2]) / 3 + 0.85 * 150);
            rgb = [grey, grey, grey];
          }
          if (state.isolate) a = 0;
          else if (this.seeThrough) a = SEE_THROUGH; // UX-4 C, at rest only
        }
        R.push(rgb[0]); G.push(rgb[1]); B.push(rgb[2]); A.push(a);
        I.push(r.index ? r.index + OFFSET + (edge ? this.n : 0) : 0);
        labels.push(r.index ? `${r.acronym || r.name} ${r.side}${edge ? " edge" : ""}` : "");
      }
    }
    return { R, G, B, A, I, labels };
  }

  // Step 7.7: stain density per row index, once (see STAIN). A small, fixed variation per region
  // keeps neighbours of one family apart, as in a real section.
  stainDensity() {
    if (this.density) return this.density;
    const d = new Float32Array(this.n);
    for (const r of this.rows) {
      if (!r.index) continue;
      const byName = STAIN.names.find(([re]) => re.test(r.name));
      const base = byName ? byName[1] : STAIN.family[r.group] ?? STAIN.family.other;
      d[r.index] = base ? Math.min(1, Math.max(0, base + 0.16 * (hash2(r.index, 17) - 0.5))) : 0;
    }
    this.density = d;
    return d;
  }

  // Step 7.8: this viewer shows real histology now (stain mode, "real", and it has some).
  get realOn() {
    return state.mode === "stain" && state.stain === "real" && Boolean(REAL_STAIN[this.atlas]);
  }

  // Load the real stain the first time it is asked for, and put it under the labels (first
  // volume, same grid) or take it out. Its licence goes under the atlas licence while shown.
  async syncReal() {
    const dir = REAL_STAIN[this.atlas];
    if (!dir || !this.vol) return;
    const want = this.realOn;
    if (want && !this.real) {
      this.realLoading ||= Promise.all([
        NVImage.loadFromUrl({ url: `${dir}/stain.nii.gz`, colormap: "gray", cal_min: 1, cal_max: 254 }),
        fetch(`${dir}/licence.json`).then((r) => r.json()),
      ]);
      const [vol, lic] = await this.realLoading;
      if (this.real) return; // another call got here first
      this.real = vol;
      this.realLicence = lic;
      if (!this.realOn) return;
    }
    const has = this.real && this.nv.volumes.includes(this.real);
    if (want && !has) {
      this.nv.addVolume(this.real);
      this.nv.setVolume(this.real, 0);
    } else if (!want && has) {
      this.nv.removeVolume(this.real);
    }
    if (want !== Boolean(has)) this.apply();
    const box = this.section.querySelector(".licence-extra");
    box.hidden = !want;
    if (want) renderLicence(box, this.realLicence, { colours: false });
  }

  // Step 7.6: region index of a stored voxel value (0 = background), with or without edge mark.
  regionOf(value) {
    const v = value > OFFSET ? value - OFFSET : 0;
    return v >= this.n ? v - this.n : v;
  }

  // Step 7.6, contours in 3D: mark, once, the voxels on a border between two regions, in the
  // volume itself (region r → r + n), so the 3D render draws them dark in atlas mode. Computed
  // here from the loaded labels: no extra file. One side of each border only (thin lines), and
  // only borders seen in the 3D view: across y and z (the sagittal cut face and the lateral
  // surface) and, on the outer surface only, across x. Borders across y would leave patches on a
  // coronal slice, so the plane under the 2D slice is kept unmarked (cleanSlice); its contours
  // are drawn as lines over it (drawContours).
  markEdges() {
    if (this.edges) return;
    const t0 = performance.now();
    const img = this.vol.img;
    const [, nx, ny, nz] = this.vol.hdr.dims;
    const sx = 1, sy = nx, sz = nx * ny;
    const n = this.n;
    const base = (i) => this.regionOf(img[i]);
    let marked = 0;
    for (let z = 0; z < nz; z++) {
      for (let y = 0; y < ny; y++) {
        for (let x = 0, i = y * sy + z * sz; x < nx; x++, i++) {
          const a = base(i);
          if (!a) continue;
          const xp = x + 1 < nx ? base(i + sx) : 0;
          const xm = x > 0 ? base(i - sx) : 0;
          const yp = y + 1 < ny ? base(i + sy) : 0;
          const ym = y > 0 ? base(i - sy) : 0;
          const zp = z + 1 < nz ? base(i + sz) : 0;
          const zm = z > 0 ? base(i - sz) : 0;
          const surface = !xp || !xm || !yp || !ym || !zp || !zm;
          // a border is marked on the side with the lower index only
          const edge = yp > a || ym > a || zp > a || zm > a || (surface && (xp > a || xm > a));
          if (edge) {
            img[i] += n;
            marked++;
          }
        }
      }
    }
    this.vol.calMinMax();
    this.edges = { ms: Math.round(performance.now() - t0), marked, slice: null };
    (window.__atlasPerf ||= {}).edges = { ...(window.__atlasPerf.edges || {}), [this.atlas]: this.edges.ms };
  }

  // Keep the coronal plane under the 2D slice free of edge marks while the slice is shown in
  // atlas mode; put the previous plane's marks back. Returns true if the volume changed.
  cleanSlice() {
    if (!this.edges) return false;
    const want = state.mode === "atlas" && state.view !== "3d"
      ? this.vol.convertFrac2Vox(this.nv.scene.crosshairPos)[1] : null;
    const e = this.edges;
    if (e.slice && e.slice.y === want) return false;
    if (!e.slice && want == null) return false;
    const img = this.vol.img;
    const [, nx, ny, nz] = this.vol.hdr.dims;
    if (e.slice) {
      for (let z = 0, k = 0; z < nz; z++) {
        for (let x = 0; x < nx; x++, k++) img[x + e.slice.y * nx + z * nx * ny] = e.slice.saved[k];
      }
      e.slice = null;
    }
    if (want != null) {
      const saved = new Uint16Array(nx * nz);
      for (let z = 0, k = 0; z < nz; z++) {
        for (let x = 0; x < nx; x++, k++) {
          const i = x + want * nx + z * nx * ny;
          saved[k] = img[i];
          if (img[i] >= OFFSET + this.n) img[i] -= this.n;
        }
      }
      e.slice = { y: want, saved };
    }
    return true;
  }

  apply() {
    if (!this.vol) return;
    if (state.mode === "atlas" && this.lateDone) this.markEdges(); // contours once all layers are in
    this.cleanSlice();
    if (REAL_STAIN[this.atlas] && this.realOn !== (this.real ? this.nv.volumes.includes(this.real) : false)) {
      this.syncReal(); // calls apply() again once the volume is in or out
    } else if (REAL_STAIN[this.atlas]) {
      const box = this.section.querySelector(".licence-extra");
      if (box) box.hidden = !this.realOn;
    }
    if (REAL_SLICE[this.atlas]) this.showSectionLicence();
    this.vol.setColormapLabel(this.colormap());
    this.nv.updateGLVolume();
    this.layout();
  }

  // Viewer frame (centred RAS mm) ↔ shown frame (mm from Bregma, or MNI mm), axis by axis.
  shownMm(axis, v) {
    return this.coords.scale * v + this.coords.offset[axis];
  }

  viewerMm(axis, v) {
    return (v - this.coords.offset[axis]) / this.coords.scale;
  }

  // One row per axis: a slider (volume fraction) and a number field in millimetres that can be
  // typed, in the shown frame (step 7.5).
  buildSliders() {
    const F = FRAME[this.coords.frame];
    const box = document.createElement("div");
    box.className = "planes";
    this.sliders = {};
    const lo = this.nv.frac2mm([0, 0, 0]).map((v, a) => this.shownMm(a, v));
    const hi = this.nv.frac2mm([1, 1, 1]).map((v, a) => this.shownMm(a, v));
    for (const [axis, key] of [[0, "x"], [1, "y"], [2, "z"]]) {
      const label = document.createElement("label");
      const name = document.createElement("span");
      const range = Object.assign(document.createElement("input"), {
        type: "range", min: 0, max: 1000, step: 1,
      });
      const [min, max] = [Math.min(lo[axis], hi[axis]), Math.max(lo[axis], hi[axis])];
      const number = Object.assign(document.createElement("input"), {
        type: "number", step: 0.01, min: min.toFixed(2), max: max.toFixed(2), inputMode: "decimal",
      });
      number.setAttribute("aria-label", `${F.axes[key]} (${TXT.mm})`);
      const unit = document.createElement("span");
      unit.textContent = TXT.mm;
      name.textContent = F.axes[key];
      range.addEventListener("input", () => {
        this.setBusy(true); // moving the point with the slider: solid until it is let go (v169)
        this.setPlane(axis, range.value / 1000);
        this.pickAtPoint({ partner: false, defer: true }); // M2: live in this brain only
      });
      range.addEventListener("change", () => {
        this.pickAtPoint({ partner: true }); // on release
        this.setBusy(false);
      });
      // Applied on Enter or when the field loses focus, so typing "-3.2" does not jump at "-".
      number.addEventListener("change", () => {
        const v = parseFloat(number.value);
        if (Number.isFinite(v)) {
          this.setPlaneMm(axis, this.viewerMm(axis, Math.min(max, Math.max(min, v))));
        }
        // Show what was applied (clamped to the volume, 2 decimals), even while still focused.
        const at = this.nv.frac2mm(this.nv.scene.crosshairPos)[axis];
        number.value = fixed2(this.shownMm(axis, at));
        this.syncPlanes();
        this.pickAtPoint({ partner: true }); // M2
      });
      label.append(name, range, number, unit);
      box.append(label);
      this.sliders[axis] = { range, number };
    }
    box.append(this.frameNote(F));
    this.section.querySelector(".stage").after(box);
    this.planesBox = box;
    this.syncPlanes();
  }

  // Move one plane: the crosshair coordinate on that axis. The coronal slice follows by itself.
  setPlane(axis, frac) {
    const pos = [...this.nv.scene.crosshairPos];
    pos[axis] = Math.min(1, Math.max(0, frac));
    this.nv.scene.crosshairPos = pos;
    this.syncPlanes();
    this.nv.drawScene();
  }

  setPlaneMm(axis, mm) {
    const at = this.nv.frac2mm(this.nv.scene.crosshairPos);
    const target = [at[0], at[1], at[2]];
    target[axis] = mm;
    this.setPlane(axis, this.nv.mm2frac(target)[axis]);
  }

  // The sagittal cut follows the crosshair x, and the controls show where the point is.
  syncPlanes() {
    const pos = this.nv.scene.crosshairPos;
    if (state.clip) this.nv.setClipPlane(clipAt(pos[0]));
    if (this.vol && this.cleanSlice()) this.nv.updateGLVolume();
    if (!this.sliders) return;
    const mm = this.nv.frac2mm(pos);
    for (const axis of [0, 1, 2]) {
      const { range, number } = this.sliders[axis];
      range.value = Math.round(pos[axis] * 1000);
      if (document.activeElement !== number) number.value = fixed2(this.shownMm(axis, mm[axis]));
    }
  }

  // Under the sliders: what the millimetres are and where Bregma and Lambda come from.
  frameNote(F) {
    const c = this.coords;
    const parts = [h("strong", {}, F.title), ". "];
    const lam = c.landmarks.lambda;
    if (lam) parts.push(F.lambda(fmt(lam.shown_mm[1]), fmt(c.flat_skull_deg, 1).replace(/^\+/, "")), " ", F.approx, " ");
    parts.push(
      F.source, " ",
      h("a", { href: c.source.url, rel: "noopener" }, F.cite),
      ".",
    );
    return h("p", { class: "frame small" }, ...parts);
  }

  // Step 7.5 (P7): millimetre ticks on the coronal slice, x along the bottom and z along the
  // left edge, plus the slice's position (AP from Bregma and Lambda, or MNI y) in a corner. A 2D
  // canvas over Niivue's; it follows Niivue's own tile geometry (screenSlices), redrawn only when
  // that or the point changes.
  buildAxes() {
    this.axes = h("canvas", { class: "axes" });
    this.section.querySelector(".stage").append(this.axes);
    let last = "";
    const loop = () => {
      const tile = state.view === "3d" ? null : this.nv.screenSlices.find(
        (s) => s.axCorSag === SLICE_TYPE.CORONAL && s.AxyzMxy.length >= 4,
      );
      const key = JSON.stringify([
        tile && [tile.leftTopWidthHeight, tile.leftTopMM, tile.fovMM, this.nv.scene.crosshairPos],
        this.canvas.width, this.canvas.height, state.view, state.mode, state.stain, state.isolate,
        [...this.focus], this.realOn && this.nv.volumes.includes(this.real),
        this.sectionShown && this.sectionShown.nr,
      ]);
      if (key !== last) {
        last = key;
        this.drawAxes(tile);
      }
      requestAnimationFrame(loop);
    };
    requestAnimationFrame(loop);
  }

  drawAxes(tile) {
    const cv = this.axes;
    const dpr = this.nv.uiData.dpr || 1;
    cv.width = this.canvas.width;
    cv.height = this.canvas.height;
    const g = cv.getContext("2d");
    g.clearRect(0, 0, cv.width, cv.height);
    // Step 7.7: the notice goes on the canvas itself, on the 3D view and on the slice.
    // The 3D view starts at the top left corner in both layouts (layout()).
    if (state.mode === "stain") {
      const half = state.view !== "3d" && cv.width >= cv.height;
      const text = this.realSliceOn ? NOTICE.real3dRat : null;
      this.drawNotice(g, 8 * dpr, 8 * dpr, dpr, (half ? cv.width / 2 : cv.width) - 16 * dpr, text);
    }
    if (!tile) return;
    const [left, top, w, hgt] = tile.leftTopWidthHeight;
    // Niivue: horizontal mm = leftTopMM[0] + h * fovMM[0], h = (X - left) / w (also when w < 0,
    // radiological); vertical mm = leftTopMM[1] + D * fovMM[1], D = 1 - (Y - top) / height.
    const toX = (mm) => left + ((mm - tile.leftTopMM[0]) / tile.fovMM[0]) * w;
    const toY = (mm) => top + (1 - (mm - tile.leftTopMM[1]) / tile.fovMM[1]) * hgt;
    if (state.mode === "atlas") this.drawContours(g, toX, toY, dpr);
    if (state.mode === "stain" && this.realOn) {
      if (this.focus.size) this.drawContours(g, toX, toY, dpr, this.focus, "rgb(232 120 20)", 2);
    } else if (state.mode === "stain") {
      // Real section: only the slide under it, so nothing drawn passes for tissue around its
      // edges or in its tears (Aday, 2026-11-13). Otherwise the drawn stain.
      if (this.realSliceOn) {
        const [left, top, w, hgt] = tile.leftTopWidthHeight;
        g.save();
        g.fillStyle = `rgb(${STAIN.slide.join(" ")})`;
        g.fillRect(Math.min(left, left + w), top, Math.abs(w), hgt);
        g.restore();
        this.paintSection(g, tile, toX, toY);
      } else {
        this.paintStain(g, tile, dpr);
      }
      // The painted slice covers Niivue's: crosshair and selection drawn again on top.
      const at = this.nv.frac2mm(this.nv.scene.crosshairPos);
      g.save();
      g.strokeStyle = "rgb(255 217 51)";
      g.lineWidth = dpr;
      g.beginPath();
      g.moveTo(toX(at[0]), top);
      g.lineTo(toX(at[0]), top + hgt);
      g.moveTo(left, toY(at[2]));
      g.lineTo(left + w, toY(at[2]));
      g.stroke();
      g.restore();
      if (this.focus.size) this.drawContours(g, toX, toY, dpr, this.focus, "rgb(232 120 20)", 2);
    }
    const c = this.coords;
    const fg = state.mode === "stain" && !this.realOn
      ? "rgb(40 30 50)" : getComputedStyle(this.section).color;
    g.fillStyle = fg;
    g.strokeStyle = fg;
    g.lineWidth = dpr;
    g.font = `${11 * dpr}px system-ui, sans-serif`;
    // A round step that leaves at least ~40 CSS px between ticks.
    const pxPerMm = Math.abs(w / tile.fovMM[0]) * c.scale ** -1;
    const step = [0.5, 1, 2, 5, 10, 20, 50].find((s) => s * pxPerMm >= 40 * dpr) || 100;
    const range = (axis, a, b) => {
      const [s0, s1] = [this.shownMm(axis, a), this.shownMm(axis, b)].sort((p, q) => p - q);
      const out = [];
      for (let v = Math.ceil(s0 / step) * step; v <= s1 + 1e-9; v += step) out.push(v);
      return out;
    };
    const dec = step < 1 ? 1 : 0;
    // x along the bottom edge.
    const bottom = top + hgt;
    g.textAlign = "center";
    g.textBaseline = "bottom";
    for (const v of range(0, tile.leftTopMM[0], tile.leftTopMM[0] + tile.fovMM[0])) {
      const X = toX(this.viewerMm(0, v));
      g.beginPath();
      g.moveTo(X, bottom);
      g.lineTo(X, bottom - (v === 0 ? 10 : 6) * dpr);
      g.stroke();
      g.fillText(fmt(v, dec), X, bottom - 12 * dpr);
    }
    // z along the left edge.
    const x0 = Math.min(left, left + w);
    g.textAlign = "left";
    g.textBaseline = "middle";
    for (const v of range(2, tile.leftTopMM[1], tile.leftTopMM[1] + tile.fovMM[1])) {
      const Y = toY(this.viewerMm(2, v));
      g.beginPath();
      g.moveTo(x0, Y);
      g.lineTo(x0 + (v === 0 ? 10 : 6) * dpr, Y);
      g.stroke();
      g.fillText(fmt(v, dec), x0 + 12 * dpr, Y);
    }
    // Where the slice is, top left of the tile.
    const y = this.shownMm(1, this.nv.frac2mm(this.nv.scene.crosshairPos)[1]);
    const F = FRAME[c.frame];
    const text = c.frame === "bregma"
      ? F.slice(fmt(y), fmt(y - c.landmarks.lambda.shown_mm[1]))
      : F.slice(fmt(y, 1));
    g.textBaseline = "top";
    g.font = `600 ${12 * dpr}px system-ui, sans-serif`;
    g.fillText(text, x0 + 8 * dpr, top + 8 * dpr);
    if (state.mode === "stain") {
      const sec = this.realSliceOn ? this.sectionShown : null;
      const text = !this.realSliceOn ? null
        : sec ? NOTICE.realSlice(fmt(sec.distance, 2).replace(/^\+/, "")) : NOTICE.realSliceLoading;
      this.drawNotice(g, x0 + 8 * dpr, top + 28 * dpr, dpr, Math.abs(w) - 16 * dpr, text);
    }
  }

  // Sofía's review: the rat's real stain in 2D. Real only in stain mode, "real", with sections.
  get realSliceOn() {
    return state.mode === "stain" && state.stain === "real" && Boolean(REAL_SLICE[this.atlas]);
  }

  // The real section nearest the coronal slice, over the drawn one (which still shows around it,
  // so the slide is not mistaken for tissue it lacks). Loads the index and each image once.
  paintSection(g, tile, toX, toY) {
    const dir = REAL_SLICE[this.atlas];
    if (!this.sections) {
      this.sections = fetch(`${dir}/index.json`).then((r) => r.json());
      this.sectionImgs = new Map();
      Promise.all([this.sections, fetch(`${dir}/licence.json`).then((r) => r.json())])
        .then(([, lic]) => { this.sectionLicence = lic; this.showSectionLicence(); });
    }
    this.showSectionLicence();
    const ap = this.shownMm(1, this.nv.frac2mm(this.nv.scene.crosshairPos)[1]);
    this.sections.then((idx) => {
      this.sectionIndex = idx;
      const best = idx.sections.reduce((a, b) => (Math.abs(b.ap_mm - ap) < Math.abs(a.ap_mm - ap) ? b : a));
      if (!this.sectionImgs.has(best.nr)) {
        const img = new Image();
        img.src = `${dir}/${best.file}`;
        const entry = { img: null };
        entry.ready = img.decode().then(() => (entry.img = img));
        this.sectionImgs.set(best.nr, entry);
      }
      this.sectionImgs.get(best.nr).ready.then(() => {
        const want = { nr: best.nr, distance: best.ap_mm - ap };
        const now = this.sectionShown;
        // A new section or a new distance redraws (the loop compares the section number only).
        if (!now || now.nr !== want.nr || Math.abs(now.distance - want.distance) > 0.005) {
          this.sectionShown = want;
          if (now && now.nr === want.nr) this.drawAxesSoon();
        }
      });
    });
    const sec = this.sectionShown && this.sectionIndex
      && this.sectionIndex.sections.find((s) => s.nr === this.sectionShown.nr);
    const img = sec && this.sectionImgs.get(sec.nr)?.img;
    if (!img) return;
    const [xl, xr, zb, zt] = sec.extent_mm;
    const X1 = toX(this.viewerMm(0, xl)), X2 = toX(this.viewerMm(0, xr));
    const Y1 = toY(this.viewerMm(2, zt)), Y2 = toY(this.viewerMm(2, zb));
    g.save();
    g.imageSmoothingEnabled = true;
    if (X2 < X1) { // radiological: mirror the image
      g.translate(X1, 0);
      g.scale(-1, 1);
      g.drawImage(img, 0, Y1, X1 - X2, Y2 - Y1);
    } else {
      g.drawImage(img, X1, Y1, X2 - X1, Y2 - Y1);
    }
    g.restore();
  }

  drawAxesSoon() {
    const tile = state.view === "3d" ? null : this.nv.screenSlices.find(
      (s) => s.axCorSag === SLICE_TYPE.CORONAL && s.AxyzMxy.length >= 4,
    );
    requestAnimationFrame(() => this.drawAxes(tile));
  }

  showSectionLicence() {
    const box = this.section.querySelector(".licence-extra");
    if (!box) return;
    box.hidden = !this.realSliceOn || !this.sectionLicence;
    if (!box.hidden && !box.childElementCount) renderLicence(box, this.sectionLicence, { colours: false });
  }

  // The notice always fits its view: the type shrinks (down to 8 px) rather than being cut.
  drawNotice(g, x, y, dpr, maxW, override = null) {
    g.save();
    g.textBaseline = "top";
    g.textAlign = "left";
    const pad = 5 * dpr;
    const text = override || (this.realOn ? NOTICE.real
      : state.stain === "real" ? NOTICE.noReal : NOTICE.drawn);
    let size = 12 * dpr;
    g.font = `600 ${size}px system-ui, sans-serif`;
    const full = g.measureText(text).width;
    if (full + 2 * pad > maxW) {
      size = Math.max(8 * dpr, (size * (maxW - 2 * pad)) / full);
      g.font = `600 ${size}px system-ui, sans-serif`;
    }
    const w = g.measureText(text).width + 2 * pad;
    const hh = size + 2 * pad;
    g.fillStyle = "rgb(255 248 225 / 0.95)";
    g.strokeStyle = "rgb(150 100 0)";
    g.lineWidth = dpr;
    g.beginPath();
    g.roundRect(x, y, w, hh, 4 * dpr);
    g.fill();
    g.stroke();
    g.fillStyle = "rgb(90 55 0)";
    g.fillText(text, x + pad, y + pad + dpr);
    g.restore();
  }

  // Step 7.7: the coronal slice painted as a drawn Nissl-like section. Density per voxel from
  // the region (stainDensity), blended between voxel centres so borders are soft, times a grain
  // tied to the voxel grid (three cells per voxel), so it stays put while the slice redraws.
  // Painted at no more than 1.5 pixels per CSS pixel and scaled, to keep phones fast.
  paintStain(g, tile, dpr) {
    const img = this.vol.img;
    const [, nx, ny, nz] = this.vol.hdr.dims;
    const y = this.vol.convertFrac2Vox(this.nv.scene.crosshairPos)[1];
    const dens = this.stainDensity();
    const D = new Float32Array(nx * nz);
    for (let z = 0; z < nz; z++) {
      for (let x = 0; x < nx; x++) D[x + z * nx] = dens[this.regionOf(img[x + y * nx + z * nx * ny])] || 0;
    }
    const at = (x, z) => (x < 0 || x >= nx || z < 0 || z >= nz ? 0 : D[x + z * nx]);
    const [left, top, w, hgt] = tile.leftTopWidthHeight;
    const x0 = Math.min(left, left + w);
    const s = Math.min(1.5, dpr) / dpr;
    const W = Math.max(1, Math.ceil(Math.abs(w) * s));
    const H = Math.max(1, Math.ceil(hgt * s));
    const m = this.vol.hdr.affine;
    const out = new ImageData(W, H);
    const px = out.data;
    const [sr, sg, sb] = STAIN.slide;
    const [ir, ig, ib] = STAIN.ink;
    for (let py = 0; py < H; py++) {
      const Y = top + (py + 0.5) / s;
      const mmZ = tile.leftTopMM[1] + (1 - (Y - top) / hgt) * tile.fovMM[1];
      const fk = (mmZ - m[2][3]) / m[2][2];
      const k0 = Math.floor(fk);
      const tk = fk - k0;
      for (let qx = 0; qx < W; qx++) {
        const X = x0 + (qx + 0.5) / s;
        const mmX = tile.leftTopMM[0] + ((X - left) / w) * tile.fovMM[0];
        const fi = (mmX - m[0][3]) / m[0][0];
        const i0 = Math.floor(fi);
        const ti = fi - i0;
        const d = (at(i0, k0) * (1 - ti) + at(i0 + 1, k0) * ti) * (1 - tk)
          + (at(i0, k0 + 1) * (1 - ti) + at(i0 + 1, k0 + 1) * ti) * tk;
        const n = hash2(Math.floor(fi * 3), Math.floor(fk * 3));
        const t = Math.min(1, d * (0.7 + 0.8 * n * n * n));
        const o = 4 * (qx + py * W);
        px[o] = sr + (ir - sr) * t;
        px[o + 1] = sg + (ig - sg) * t;
        px[o + 2] = sb + (ib - sb) * t;
        px[o + 3] = 255;
      }
    }
    const off = new OffscreenCanvas(W, H);
    off.getContext("2d").putImageData(out, 0, 0);
    g.save();
    g.imageSmoothingEnabled = true;
    g.drawImage(off, x0, top, Math.abs(w), hgt);
    g.restore();
  }

  // Step 7.6, contours in 2D: lines along the voxel faces between two regions (or a region and
  // the background) of the coronal slice, neighbours in the slice only, so a border lying along
  // the slice never shows as a patch. Isolating keeps only the borders of what is shown.
  drawContours(g, toX, toY, dpr, subset = null, colour = null, width = 0.75) {
    const img = this.vol.img;
    const [, nx, ny, nz] = this.vol.hdr.dims;
    const y = this.vol.convertFrac2Vox(this.nv.scene.crosshairPos)[1];
    // Voxel centres are at affine * index (RAS, diagonal); faces half a voxel away.
    const m = this.vol.hdr.affine;
    const fx = (i) => toX(m[0][0] * (i - 0.5) + m[0][3]);
    const fz = (k) => toY(m[2][2] * (k - 0.5) + m[2][3]);
    const at = (x, z) => (x < 0 || x >= nx || z < 0 || z >= nz ? 0
      : this.regionOf(img[x + y * nx + z * nx * ny]));
    const only = subset || (state.isolate && this.focus.size ? this.focus : null);
    const shown = (a) => a && (!only || only.has(a));
    const path = new Path2D();
    for (let z = 0; z <= nz; z++) {
      for (let x = 0; x <= nx; x++) {
        const a = at(x, z);
        const left = at(x - 1, z);
        const below = at(x, z - 1);
        if (a !== left && (shown(a) || shown(left))) {
          path.moveTo(fx(x), fz(z));
          path.lineTo(fx(x), fz(z + 1));
        }
        if (a !== below && (shown(a) || shown(below))) {
          path.moveTo(fx(x), fz(z));
          path.lineTo(fx(x + 1), fz(z));
        }
      }
    }
    g.save();
    g.strokeStyle = colour || `rgb(${GREY.edge} ${GREY.edge} ${GREY.edge})`;
    g.lineWidth = Math.max(1, dpr * width);
    g.stroke(path);
    g.restore();
  }

  layout() {
    const nv = this.nv;
    nv.setClipPlane(state.clip ? clipAt(nv.scene.crosshairPos[0]) : [2, 0, 0]);
    nv.opts.show3Dcrosshair = state.view !== "3d";
    if (this.planesBox) this.planesBox.hidden = state.view === "3d";
    if (state.view === "3d") {
      nv.clearCustomLayout();
      nv.setSliceType(SLICE_TYPE.RENDER);
      return;
    }
    // 3D + one coronal slice: side by side if the canvas is wide, one above the other if not.
    const wide = this.canvas.clientWidth >= this.canvas.clientHeight;
    nv.setSliceType(SLICE_TYPE.MULTIPLANAR);
    nv.setCustomLayout(
      wide
        ? [
            { sliceType: SLICE_TYPE.RENDER, position: [0, 0, 0.5, 1] },
            { sliceType: SLICE_TYPE.CORONAL, position: [0.5, 0, 0.5, 1] },
          ]
        : [
            { sliceType: SLICE_TYPE.RENDER, position: [0, 0, 1, 0.5] },
            { sliceType: SLICE_TYPE.CORONAL, position: [0, 0.5, 1, 0.5] },
          ],
    );
  }

  picked(loc) {
    const at = this.nv.volumes.indexOf(this.vol); // 1 while the real stain is under it
    const raw = loc && loc.values && loc.values[at] ? Math.round(loc.values[at].value) : 0;
    let v = this.regionOf(raw);
    if (this.tapFrom) {
      const moved = this.nv.scene.crosshairPos.some((x, a) => Math.abs(x - this.tapFrom[a]) > 1e-6);
      this.tapFrom = null;
      if (!moved) v = 0; // the tap hit the background of the 3D view
    }
    this.showTag(v ? this.rows[v] : null);
    if (!v) {
      // Aday (v167): a tap outside the brain lets go of the selection in this brain only; it
      // takes its colours back, and the other brain keeps what it shows.
      this.upAt = null;
      // UX-4 C: while something is selected the rest is almost transparent, and a tap on it
      // goes through. Once solid again, the same tap is tried once more: on tissue it picks
      // the region there; on the background nothing else happens (v168).
      const retry = this.focus.size > 0 && this.seeThrough && this.lastTap && !this.retrying;
      const at = this.lastTap;
      this.lastTap = null;
      this.pick(0, { partner: false });
      if (retry) this.tapAgain(at);
      return;
    }
    this.lastTap = null;
    // Step 4 (SCOPE v164): how long a tap takes, by parts, for scripts/atlas_measure.mjs. From
    // the finger lifting to: the region read (Niivue's pick), this brain repainted, the other
    // brain repainted, and the next frame on screen.
    const t = { read: performance.now() - (this.upAt || performance.now()) };
    this.pick(v, { partner: true, timing: t });
    if (this.upAt && v) {
      const t0 = this.upAt;
      requestAnimationFrame(() => {
        t.frame = performance.now() - t0;
        ((window.__atlasPerf ||= {}).taps ||= []).push({ atlas: this.atlas, ...t });
      });
    }
    this.upAt = null;
  }

  // Select region index v (0 = none). partner: also tell the other brain (pair, panel, point).
  // While a slider is dragged the other brain waits (partner false) and catches up on release,
  // so the same region is picked again with partner true if it was not passed on yet.
  // defer (step 7.9, slider drags): repainting the highlight (apply) is what stuttered on a real
  // phone, so while dragging it waits until the finger stops for APPLY_PAUSE ms or lets go; the
  // panel still follows live.
  pick(v, { partner = true, atPoint = false, defer = false, timing = null } = {}) {
    const same = v === (this.selectedIndex || 0);
    const t0 = performance.now();
    if (!same) {
      this.selectedIndex = v || null;
      this.focus = new Set(v ? [v] : []);
      if (defer) this.applySoon();
      else this.applyNow();
    } else if (!defer && this.applyTimer) this.applyNow();
    if (timing) timing.thisBrain = performance.now() - t0;
    if (same && (!partner || this.passedOn)) return;
    this.passedOn = partner;
    const t1 = performance.now();
    this.onPick(v ? regionFromRow(this.atlas, this.rows[v]) : null, { partner, atPoint });
    if (timing) timing.otherBrain = performance.now() - t1;
  }

  applySoon() {
    clearTimeout(this.applyTimer);
    this.applyTimer = setTimeout(() => this.applyNow(), APPLY_PAUSE);
  }

  applyNow() {
    clearTimeout(this.applyTimer);
    this.applyTimer = null;
    this.apply();
  }

  // Improvement M2 (Aday): the point where the three axes meet picks the region there.
  pickAtPoint(options) {
    if (!this.vol) return;
    const [x, y, z] = this.vol.convertFrac2Vox(this.nv.scene.crosshairPos);
    const [, nx, ny] = this.vol.hdr.dims;
    if (this.tag) this.tag.hidden = true;
    this.pick(this.regionOf(this.vol.img[x + y * nx + z * nx * ny]), { ...options, atPoint: true });
  }

  showTag(row) {
    if (!row || !this.lastClick) {
      this.tag.hidden = true;
      return;
    }
    const n = names(regionFromRow(this.atlas, row));
    this.tag.replaceChildren(h("strong", {}, n.short), n.short === n.full ? "" : ` ${n.full}`);
    this.tag.style.left = `${this.lastClick.x}px`;
    this.tag.style.top = `${this.lastClick.y}px`;
    this.tag.classList.toggle("left", this.lastClick.x > this.canvas.clientWidth / 2);
    this.tag.hidden = false;
  }

  // Step 7.4 (P3): bring the highlighted region into view. The point (and so the coronal slice
  // and the sagittal cut) goes to its centroid, weighted by voxels when it is several areas. In
  // the plain 3D view, the camera turns to the region's side; with the cut on it stays on the
  // left, because the cut removes the camera's side and the region shows on the cut face.
  goTo(indices) {
    // Both sides (an area picked in the search): go to the left one, the side the camera
    // faces; their joint centroid would fall on the midline.
    const sides = new Set([...indices].map((i) => this.rows[i].side));
    if (sides.size > 1) indices = [...indices].filter((i) => this.rows[i].side === "L");
    let w = 0;
    const c = [0, 0, 0];
    for (const i of indices) {
      const r = this.rows[i];
      if (!r.centroid_mm || !r.voxels) continue;
      for (const a of [0, 1, 2]) c[a] += r.centroid_mm[a] * r.voxels;
      w += r.voxels;
    }
    if (!w) return;
    const frac = this.nv.mm2frac(c.map((x) => x / w));
    this.nv.scene.crosshairPos = [0, 1, 2].map((a) => Math.min(1, Math.max(0, frac[a])));
    const side = this.rows[[...indices][0]].side;
    if (!state.clip) this.nv.setRenderAzimuthElevation(side === "R" ? 270 : AZIMUTH, ELEVATION);
    this.syncPlanes();
    this.nv.drawScene();
  }

  // Improvement M1 (Aday): pick an area from the search box, as a click would, both sides.
  selectArea(item) {
    this.selectedIndex = -1; // an area, not one piece: any later click or point picks again
    this.passedOn = true;
    this.focus = new Set(item.indices);
    if (this.tag) this.tag.hidden = true;
    this.apply();
    this.goTo(this.focus);
    this.onPick(item.region);
  }

  // What the search box can find in this atlas: one entry per area with both sides together
  // (Waxholm id, Julich-Brain area) and, for Waxholm, the parent nodes of its hierarchy, which
  // stand for all their pieces. Names are the atlases' own, in English.
  searchIndex(tree) {
    const items = new Map();
    const add = (key, region, index) => {
      if (!items.has(key)) items.set(key, { region, indices: [] });
      items.get(key).indices.push(index);
    };
    for (const r of this.rows) {
      if (!r.index) continue;
      if (this.atlas === "waxholm") {
        add(`w${r.id}`, { atlas: "waxholm", side: null, id: r.id, name: r.name, acronym: r.acronym, path: r.path }, r.index);
        for (const a of r.path || []) {
          if (a === r.id || !tree[a]) continue;
          const t = tree[a];
          add(`w${a}`, { atlas: "waxholm", side: null, id: a, name: t.name, acronym: t.acronym, path: t.path }, r.index);
        }
      } else {
        // A further layer's label value differs per side, so a both-sides entry shows none.
        const label = r.source === "julich" ? r.label : null;
        add(`j${r.area_id}`, { atlas: "julich", side: null, id: r.area_id, name: r.name, label, areaId: r.area_id, source: r.source }, r.index);
      }
    }
    return [...items.entries()].map(([key, it]) => {
      const n = names(it.region);
      return { ...it, key, short: n.short, full: n.full, s: fold(n.short), f: fold(n.full) };
    });
  }

  // Highlight what the other atlas asked for: same side, by Waxholm ancestor or Julich area.
  highlight(partner) {
    this.selectedIndex = -1; // the partner set, not a picked piece: any click or point picks again
    this.focus = new Set(
      partner
        ? this.rows
            .filter((r) => r.index && (partner.side == null || r.side === partner.side))
            .filter((r) =>
              partner.waxholmId != null
                ? (r.path || []).includes(partner.waxholmId)
                : partner.areaIds.includes(r.area_id),
            )
            .map((r) => r.index)
        : [],
    );
    if (this.tag) this.tag.hidden = true;
    if (!this.vol) return; // still loading: applied when it is ready
    this.apply(); // UX-4 B: marked, not moved; «Ir a la pareja» calls goTo
  }
}

// ---------------------------------------------------------------- from spikes/s3/site/common/common.js

// Palette (S3 step 7.2): the calm colours by family (Sofía's request P5).
const colourOf = (row) => (row && (row.color_calm || row.color)) || "#888888";

// A stronger version of a colour, for the selected region and its counterpart: with soft tones
// the selection has to stand out from the rest without relying on the grey alone.
function strong(hexColour) {
  const n = parseInt(hexColour.slice(1), 16);
  let [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => v / 255);
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  let hue = 0;
  const l = (max + min) / 2;
  const d = max - min;
  const sat = d === 0 ? 0 : d / (1 - Math.abs(2 * l - 1));
  if (d) {
    if (max === r) hue = ((g - b) / d) % 6;
    else if (max === g) hue = (b - r) / d + 2;
    else hue = (r - g) / d + 4;
  }
  hue = (hue * 60 + 360) % 360;
  const s2 = Math.min(1, sat + 0.35), l2 = Math.max(0.3, l - 0.25);
  const c = (1 - Math.abs(2 * l2 - 1)) * s2, x = c * (1 - Math.abs(((hue / 60) % 2) - 1)), m = l2 - c / 2;
  [r, g, b] = hue < 60 ? [c, x, 0] : hue < 120 ? [x, c, 0] : hue < 180 ? [0, c, x]
    : hue < 240 ? [0, x, c] : hue < 300 ? [x, 0, c] : [c, 0, x];
  return "#" + [r, g, b].map((v) => Math.round((v + m) * 255).toString(16).padStart(2, "0")).join("");
}

// Step 4: the volumes are asked for as soon as the viewer starts, side by side with Niivue,
// instead of one after the other (Niivue first, then each volume): on «Slow 4G» that was most of
// the wait. Each URL is fetched once; Niivue reads the bytes from here.
const fetched = new Map();
function prefetch(url) {
  if (!fetched.has(url)) {
    fetched.set(url, fetch(url).then((r) => {
      if (!r.ok) throw new Error(`${url}: ${r.status}`);
      return r.arrayBuffer();
    }));
  }
  return fetched.get(url);
}

async function json(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
}

// Human layers, in order (Sofía's review): each one only labels what the ones before leave empty
// (synaptica.atlas.layers). Julich-Brain is the base.
const HUMAN_LAYERS = ["cerebra", "cit168", "icbm_wm"];

async function loadData() {
  const [wl, jl, pairs, ...layers] = await Promise.all([
    json(`${DATA}/waxholm/labels.json`),
    json(`${DATA}/julich/labels.json`),
    json(`${DATA}/pairs.json`),
    ...HUMAN_LAYERS.map((n) => json(`${DATA}/${n}/labels.json`)),
  ]);
  // One human brain, several label files: the rows of each layer go after the ones before, so
  // the viewer reads value k of a layer as row k + from - 1 (VolumeViewer.load). The files stay
  // apart (licences); they only meet here, on screen.
  const rows = jl.rows.map((r) => ({ ...r, source: r.index ? "julich" : null }));
  const extras = [];
  HUMAN_LAYERS.forEach((name, i) => {
    const from = rows.length;
    rows.push(...layers[i].rows.slice(1).map((r) => ({ ...r, index: r.index + from - 1, source: name })));
    // Step 4: the white matter (0.29 MB, the heaviest layer) joins after the brain is usable.
    extras.push({ name, url: `${DATA}/${name}/labels.nii.gz`, from, late: name === "icbm_wm" });
  });
  return {
    waxholm: { labels: wl },
    julich: { labels: { ...jl, rows }, extras },
    pairs: pairs.pairs,
  };
}

// A region, whichever viewer picked it: {atlas, side, id, name, acronym?, label?, areaId?, path?}
function regionFromRow(atlas, row) {
  if (atlas === "waxholm") {
    return { atlas, side: row.side, id: row.id, name: row.name, acronym: row.acronym, path: row.path };
  }
  return {
    atlas, side: row.side, id: row.id, name: row.name, label: row.label, areaId: row.area_id,
    source: row.source,
  };
}

// The pair a region belongs to, if any. Waxholm matches through its ancestors (a click on CA1
// belongs to the HF pair); the human brain through the area without side.
function pairOf(region, pairs) {
  if (region.atlas === "waxholm") {
    const path = region.path || [region.id];
    return pairs.find((p) => path.includes(p.waxholm.id)) || null;
  }
  return pairs.find((p) => p.human.some((j) => j.area_id === region.areaId)) || null;
}

// What the other viewer has to mark: {atlas, side, waxholmId} or {atlas, side, areaIds}.
function partnerOf(region, pair) {
  if (!pair) return null;
  if (region.atlas === "waxholm") {
    return { atlas: "julich", side: region.side, areaIds: pair.human.map((j) => j.area_id) };
  }
  return { atlas: "waxholm", side: region.side, waxholmId: pair.waxholm.id };
}

// The licence of a real stain, under its brain while it is shown (licence.json of its folder).
const LIC = {
  es: { licence: "Licencia", source: "Fuente", cite: "Cita" },
  en: { licence: "Licence", source: "Source", cite: "Citation" },
}[lang];
function renderLicence(box, lic) {
  box.replaceChildren(
    h("strong", {}, lic.short || lic.atlas), " · ", `${LIC.licence}: `,
    h("a", { href: lic.licence_url, rel: "license noopener" }, lic.licence), " · ",
    h("a", { href: lic.source_url, rel: "noopener" }, LIC.source),
    ...(lic.citation ? [h("br"), `${LIC.cite}: ${lic.citation}`] : []),
  );
}

// ---------------------------------------------------------------- the page (SCOPE v163)

const UI = {
  es: {
    loading: "Cargando el cerebro en 3D…",
    noGl: "Tu navegador no puede mostrar el 3D. La lista de regiones y el buscador siguen funcionando.",
    failed: "No se ha podido cargar el visor 3D. La lista de regiones y el buscador siguen funcionando.",
    picked: (name, brain) => `${name}, ${brain}`,
  },
  en: {
    loading: "Loading the brain in 3D…",
    noGl: "Your browser cannot show the 3D view. The region list and the search still work.",
    failed: "The 3D viewer could not be loaded. The region list and the search still work.",
    picked: (name, brain) => `${name}, ${brain}`,
  },
}[lang];

const BRAIN_OF = { waxholm: "rat", julich: "human" };
const ATLAS_OF = { rat: "waxholm", human: "julich" };
const narrow = matchMedia("(max-width: 799px)");

function script(src) {
  return new Promise((ok, ko) => {
    const s = document.createElement("script");
    s.src = src;
    s.onload = ok;
    s.onerror = () => ko(new Error(src));
    document.head.append(s);
  });
}

const webgl2 = () => {
  try {
    return Boolean(document.createElement("canvas").getContext("webgl2"));
  } catch {
    return false;
  }
};

async function main() {
  const brains = root.querySelector(".brains");
  const sections = Object.fromEntries(
    ["waxholm", "julich"].map((a) => [a, root.querySelector(`#${BRAIN_OF[a]}`)]),
  );
  const status = (atlas, text) => {
    const box = sections[atlas].querySelector(".stage-status");
    box.textContent = text || "";
    box.hidden = !text;
  };
  if (!webgl2()) {
    Object.keys(sections).forEach((a) => status(a, UI.noGl));
    return;
  }
  // The first brain's volumes, now (the human on a phone; both on a wide screen). The late layer
  // waits for the others, so it does not share their bandwidth.
  // The late layer is asked for only once its brain is usable (VolumeViewer.load): before, it
  // took bandwidth from Niivue itself (measured, SCOPE v164).
  const firstAtlases = narrow.matches ? ["julich"] : ["julich", "waxholm"];
  for (const a of firstAtlases) {
    prefetch(`${DATA}/${a}/labels.nii.gz`);
    prefetch(`${DATA}/${a}/coords.json`);
  }
  if (firstAtlases.includes("julich")) ["cerebra", "cit168"].forEach((n) => prefetch(`${DATA}/${n}/labels.nii.gz`));
  const data = await loadData();
  const viewers = (window.__atlas = {});
  const items = {}; // search entries per atlas, from the label tables (no 3D needed)
  const loading = {};

  // UX-1 C: on a phone, one brain at a time; the human first until Sofía says otherwise.
  let active = "julich";
  const switchBox = root.querySelector(".brain-switch");
  const showActive = () => {
    brains.dataset.active = BRAIN_OF[active];
    for (const b of switchBox.querySelectorAll("button")) {
      b.setAttribute("aria-pressed", String(ATLAS_OF[b.dataset.brain] === active));
    }
  };

  for (const atlas of ["waxholm", "julich"]) {
    const section = sections[atlas];
    const v = new VolumeViewer(section, atlas, data[atlas].labels.rows, data[atlas].extras || []);
    viewers[atlas] = v;
    items[atlas] = v.searchIndex(data[atlas].labels.tree || {});
    panelPicked(v.panel, null);
    v.onPick = (region, { partner = true, atPoint = false } = {}) => {
      const otherAtlas = atlas === "waxholm" ? "julich" : "waxholm";
      const other = viewers[otherAtlas];
      const pair = region ? pairOf(region, data.pairs) : null;
      panelPicked(v.panel, region, pair, atPoint ? P.nonePoint : P.none);
      if (region) announce(UI.picked(names(region).full, SEARCH[BRAIN_OF[atlas]]));
      if (!partner) return; // M2: the other brain follows when the slider is let go
      // Aday (v168): only a region with a counterpart moves the other brain; without one, the
      // other brain keeps its own selection, so each brain can show a different region.
      if (!pair) return;
      panelPartner(other.panel, region, pair, () => goToPair(otherAtlas));
      // Step 4: the brain that was touched is painted first; the other one in the next frame,
      // so a tap shows at once even when both brains have to change.
      const token = (other.partnerToken = {});
      requestAnimationFrame(() => setTimeout(() => {
        if (other.partnerToken !== token) return;
        const t = performance.now();
        other.highlight(region ? partnerOf(region, pair) : null);
        ((window.__atlasPerf ||= {}).partner ||= []).push(performance.now() - t);
      }));
    };
  }

  // Load one brain once: Niivue and its volume, then the canvas takes the place of the still.
  const load = (atlas) => (loading[atlas] ||= (async () => {
    const v = viewers[atlas];
    status(atlas, UI.loading);
    await niivueReady;
    await v.load(`${DATA}/${atlas}/labels.nii.gz`);
    v.section.classList.add("is-live");
    status(atlas, "");
    v.apply();
    if (v.focus.size) v.apply();
    performance.mark(`atlas-${atlas}-ready`);
  })().catch((e) => {
    status(atlas, UI.failed);
    console.error(e);
  }));

  async function goToPair(atlas) {
    if (narrow.matches && active !== atlas) {
      active = atlas;
      showActive();
    }
    await load(atlas);
    const v = viewers[atlas];
    if (v.focus.size) v.goTo(v.focus);
  }

  // A region chosen in the search or the list: in its brain, as a click would, both sides.
  async function choose(atlas, item) {
    if (narrow.matches && active !== atlas) {
      active = atlas;
      showActive();
    }
    await load(atlas);
    viewers[atlas].selectArea(item);
    sections[atlas].scrollIntoView({ block: "nearest", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  }

  const live = root.querySelector(".atlas-live");
  const announce = (text) => {
    live.textContent = text;
  };

  // Toolbar (UX-3 B): «Recortar» and «Más opciones» in view; the rest inside.
  const toolbar = root.querySelector(".atlas-tools");
  const each = (f) => Object.values(viewers).forEach((v) => v.vol && f(v));
  const press = (sel, on) => toolbar.querySelectorAll(sel).forEach((b) => b.setAttribute("aria-pressed", String(on(b))));
  const showState = () => {
    press("[data-clip]", () => state.clip);
    press("[data-view]", (b) => b.dataset.view === state.view);
    press("[data-look]", (b) => b.dataset.look === (state.mode === "stain" ? state.stain : state.mode));
    press("[data-isolate]", () => state.isolate);
  };
  toolbar.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.hasAttribute("data-more")) {
      const panel = toolbar.querySelector(".atlas-more");
      panel.hidden = !panel.hidden;
      b.setAttribute("aria-expanded", String(!panel.hidden));
      return;
    }
    if (b.hasAttribute("data-clip")) state.clip = !state.clip;
    if (b.dataset.view) {
      state.view = b.dataset.view;
      if (state.view === "slice") {
        state.clip = true; // the 3D cut and the 2D slice go together (P1)
        each((v) => v.nv.setRenderAzimuthElevation(AZIMUTH, ELEVATION));
      }
    }
    if (b.dataset.look) {
      state.mode = ["drawn", "real"].includes(b.dataset.look) ? "stain" : b.dataset.look;
      if (state.mode === "stain") state.stain = b.dataset.look;
    }
    if (b.hasAttribute("data-isolate")) state.isolate = !state.isolate;
    remember();
    showState();
    each((v) => v.apply());
  });
  toolbar.addEventListener("keydown", (e) => {
    const panel = toolbar.querySelector(".atlas-more");
    if (e.key === "Escape" && !panel.hidden) {
      panel.hidden = true;
      const more = toolbar.querySelector("[data-more]");
      more.setAttribute("aria-expanded", "false");
      more.focus();
    }
  });
  showState();
  toolbar.hidden = false;

  switchBox.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-brain]");
    if (!b) return;
    active = ATLAS_OF[b.dataset.brain];
    showActive();
    load(active);
  });
  showActive();
  switchBox.hidden = false;

  // One search for both brains (the page's box): suggestions under it, best matches first.
  searchBoth(root.querySelector("#atlas-q"), items, choose);
  // The region list: each name picks its region in its brain.
  for (const li of root.querySelectorAll(".regions li[data-key]")) {
    const atlas = ATLAS_OF[li.closest(".brain").id];
    const item = items[atlas].find((it) => it.key === li.dataset.key);
    const name = li.querySelector(".rname");
    if (!item || !name) continue;
    const b = h("button", { type: "button", class: "rname" }, ...name.childNodes);
    b.addEventListener("click", () => choose(atlas, item));
    name.replaceWith(b);
  }

  new ResizeObserver(() => each((v) => state.view !== "3d" && v.layout())).observe(brains);
  // The theme toggle changes --atlas-bg: the 3D background follows.
  new MutationObserver(() => each((v) => {
    v.nv.opts.backColor = backColour();
    v.nv.drawScene();
  })).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

  // UX-5 B: the viewer comes right after the page, by itself. On a phone, only the brain shown.
  await Promise.all(firstAtlases.map(load));
  // Step 5: «Ver en el visor» from a region page arrives with the area's key as the hash.
  const fromHash = () => {
    const key = decodeURIComponent(location.hash.slice(1));
    for (const atlas of ["waxholm", "julich"]) {
      const item = items[atlas].find((it) => it.key === key);
      if (item) return choose(atlas, item);
    }
  };
  addEventListener("hashchange", fromHash);
  fromHash();
  narrow.addEventListener("change", () => !narrow.matches && Object.keys(sections).forEach(load));
}

let niivueReady;

// One search box for both brains: its own result list (not a datalist, which filters
// differently in each browser), arrows, Enter and Escape, click or tap (S3 improvement M1).
function searchBoth(input, items, choose) {
  const list = document.getElementById("atlas-suggest");
  const all = Object.entries(items).flatMap(([atlas, its]) => its.map((it) => ({ ...it, atlas })));
  let shown = [];
  let active = -1;
  const close = () => {
    list.hidden = true;
    active = -1;
    input.setAttribute("aria-expanded", "false");
  };
  const render = () => {
    list.replaceChildren();
    if (!shown.length) list.append(h("li", { class: "empty" }, SEARCH.none));
    shown.forEach((it, i) => {
      const li = h("li", { role: "option", id: `atlas-opt-${i}`, "aria-selected": String(i === active) },
        h("strong", {}, it.short), it.short === it.full ? "" : ` ${it.full}`,
        h("span", { class: "layer" }, SEARCH[BRAIN_OF[it.atlas]]));
      li.addEventListener("pointerdown", (e) => {
        e.preventDefault(); // keep the focus in the box until chosen
        pick(it);
      });
      list.append(li);
    });
    list.hidden = false;
    input.setAttribute("aria-expanded", "true");
    if (active >= 0) input.setAttribute("aria-activedescendant", `atlas-opt-${active}`);
    else input.removeAttribute("aria-activedescendant");
  };
  const pick = (it) => {
    close();
    choose(it.atlas, it);
  };
  input.addEventListener("input", () => {
    shown = search(all, input.value, 10);
    active = shown.length ? 0 : -1;
    if (fold(input.value)) render();
    else close();
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      if (!shown.length) return;
      e.preventDefault();
      active = (active + (e.key === "ArrowDown" ? 1 : shown.length - 1)) % shown.length;
      render();
    } else if (e.key === "Enter" && active >= 0 && !list.hidden) {
      e.preventDefault();
      pick(shown[active]);
    } else if (e.key === "Escape") {
      close();
    }
  });
  input.addEventListener("blur", close);
}

if (root) {
  // UX-5 B: the page first. A module runs once the page is parsed, when its text is already on
  // screen; waiting for the «load» event as well (images, fonts) cost ~0.6 s on «Slow 4G» and
  // won nothing (measured, SCOPE v164), so the viewer starts here.
  niivueReady = script(root.dataset.niivue).then(() => ({ Niivue, NVImage, SLICE_TYPE } = window.niivue));
  main().catch((e) => console.error(e));
}

// Measurement hook (step 4, as in spikes/s3/measure.mjs): turn the loaded brains for ms and
// count the frames.
window.__spin = (ms = 3000) =>
  new Promise((done) => {
    const vs = Object.values(window.__atlas || {}).filter((v) => v.vol);
    const frames = Object.fromEntries(vs.map((v) => [v.atlas, 0]));
    const t0 = performance.now();
    const step = () => {
      const dt = performance.now() - t0;
      for (const v of vs) {
        v.nv.setRenderAzimuthElevation(AZIMUTH + dt * 0.12, ELEVATION);
        frames[v.atlas]++;
      }
      if (dt < ms) requestAnimationFrame(step);
      else done(Object.fromEntries(vs.map((v) => [v.atlas, Math.round((frames[v.atlas] * 1000) / ms)])));
    };
    requestAnimationFrame(step);
  });
