// Spike S3, mock-up C: Niivue with our own label volumes (one NIfTI per atlas). Throwaway code.
// Niivue is loaded as a classic script (vendor/niivue-0.69.0/niivue.umd.js): global `niivue`.
import {
  t, lang, loadData, fillTexts, renderLicence, regionFromRow, pairOf, partnerOf, markReady,
  colourOf, strong,
} from "../common/common.js";

fillTexts();
const { Niivue, SLICE_TYPE } = window.niivue;

const dark = matchMedia("(prefers-color-scheme: dark)").matches;
const BACK = dark ? [0.106, 0.106, 0.125, 1] : [0.949, 0.945, 0.933, 1];
// Step 7.3 (Sofía, P2): a true side view, no diagonal. Azimuth 90 looks at the left side.
const AZIMUTH = 90;
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

// Step 7.4 (P3, P6): panels of C. Written here, not in common.js, so mock-up B stays as it is.
const P = {
  es: {
    none: "Ninguna región seleccionada.",
    side: { L: "hemisferio izquierdo", R: "hemisferio derecho" },
    id: "ID",
    mpm: "etiqueta del mapa",
    origName: "Nombre original del atlas, en inglés: la traducción la revisa Sofía en la Fase 2.",
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
    side: { L: "left hemisphere", R: "right hemisphere" },
    id: "ID",
    mpm: "map label",
    origName: null,
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

function facts(region) {
  const p = h("p", { class: "facts" }, `${P.side[region.side] || ""} · ${P.id}: `);
  p.append(h("code", {}, String(region.id)));
  if (region.label != null) p.append(` · ${P.mpm}: ${region.label}`);
  return p;
}

// The panel of the viewer that was clicked.
function panelPicked(box, region, pair) {
  box.replaceChildren();
  if (!region) return box.append(h("p", { class: "muted" }, P.none));
  box.append(title(region), facts(region));
  if (!pair) {
    box.append(h("p", { class: "muted" }, abbr(region), ": ", P.noPairHere));
  } else {
    const other = region.atlas === "waxholm"
      ? pair.julich.map((j) => j.name).join(", ")
      : `${pair.waxholm.name} (${pair.waxholm.acronym})`;
    const p = h("p", { class: "pair" }, `${P.inOther}: ${other}. `);
    p.append(h("span", { class: "grade" }, `${P.grade}: ${pair.grade}`));
    box.append(p);
  }
  if (P.origName) box.append(h("p", { class: "muted small" }, P.origName));
}

// The panel of the other viewer: what was selected there on its behalf, or why nothing was.
function panelPartner(box, source, pair) {
  box.replaceChildren();
  if (!source) return box.append(h("p", { class: "muted" }, P.none));
  const species = source.atlas === "waxholm" ? P.rat : P.human;
  if (!pair) {
    box.append(h("p", { class: "muted" }, P.noPairThere(`${names(source).short} (${species})`)));
    return;
  }
  const shown = source.atlas === "waxholm"
    ? pair.julich.map((j) => ({ name: j.name, id: j.area_id }))
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
  list.append(` · ${P.side[source.side]}`);
  const g = h("p", { class: "pair" }, h("span", { class: "grade" }, `${P.grade}: ${pair.grade}`));
  box.append(head, list, g);
  if (P.origName) box.append(h("p", { class: "muted small" }, P.origName));
}

// Step 7.6 (P4): one way of looking at a time. "color": the calm palette; "atlas": black and
// white, grey fill and contours, like a printed atlas plate; "stain": a drawn Nissl-like stain
// (step 7.7), always with the notice that it is an illustration.
const MODES = ["color", "atlas", "stain"];
const askedMode = new URLSearchParams(location.search).get("mode");
const state = {
  view: "3d", clip: false, isolate: false, mode: MODES.includes(askedMode) ? askedMode : "color",
};
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
    [/dentate gyrus|^DG |granule cell layer|granular layer|layer 2\b|cerebellum, unspecified/i, 0.9],
    [/glomerular/i, 0.35],
  ],
};
const NOTICE = {
  es: "Ilustración, no es una tinción real",
  en: "Illustration, not a real stain",
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
  constructor(section, atlas, rows) {
    this.atlas = atlas;
    this.section = section;
    this.rows = rows;
    this.canvas = section.querySelector("canvas");
    this.panel = section.querySelector(".panel");
    this.status = section.querySelector(".status");
    this.focus = new Set(); // row indices shown at full strength
    this.selectedIndex = null;
    this.n = rows.length; // atlas mode: the edge voxels of region r hold r + n (step 7.6)
    this.edges = null; // set the first time the atlas mode is chosen
    this.onPick = () => {};
    this.nv = new Niivue({
      backColor: BACK,
      show3Dcrosshair: false, // on in "3D + slice": the 3D view shows where the 2D slice is
      isColorbar: false,
      dragAndDropEnabled: false,
      loadingText: "",
      crosshairColor: [1, 0.85, 0.2, 1],
      crosshairWidth: 1,
      isOrientCube: false,
      clipPlaneColor: [0, 0, 0, 0], // cut without drawing the plane
      logLevel: "error",
      // ?dpr=1 renders at one pixel per CSS pixel (measured in results/maqueta-c.md); 0 = device.
      forceDevicePixelRatio: Number(new URLSearchParams(location.search).get("dpr") || 0),
    });
  }

  async load(url) {
    await this.nv.attachToCanvas(this.canvas);
    this.nv.setInterpolation(true); // nearest neighbour: labels must not blend
    await this.nv.loadVolumes([{ url, name: url.split("/").pop() }]);
    this.vol = this.nv.volumes[0];
    const img = this.vol.img;
    for (let i = 0; i < img.length; i++) if (img[i]) img[i] += OFFSET;
    this.vol.calMinMax();
    this.coords = await (await fetch(`../data/${this.atlas}/coords.json`)).json();
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
    this.status.remove();
    this.apply();
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
    this.canvas.addEventListener("pointerdown", (e) => {
      down = { x: e.clientX, y: e.clientY, t: performance.now() };
      this.lastClick = at(e);
    });
    this.canvas.addEventListener("pointermove", (e) => {
      if (down && Math.hypot(e.clientX - down.x, e.clientY - down.y) > 6) this.tag.hidden = true;
    });
    this.canvas.addEventListener("pointerup", (e) => {
      if (!down) return;
      const quick = performance.now() - down.t < 600;
      const still = Math.hypot(e.clientX - down.x, e.clientY - down.y) <= 6;
      down = null;
      if (!quick || !still) return;
      const r = this.canvas.getBoundingClientRect();
      const dpr = this.nv.uiData.dpr || 1;
      if (this.nv.inRenderTile((e.clientX - r.left) * dpr, (e.clientY - r.top) * dpr) < 0) return;
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
        }
        // While something is selected the rest goes grey (alpha barely shows in the 3D render
        // of a label volume), or disappears when isolating.
        if (r.index && this.focus.size && !focused) {
          if (state.mode === "color") {
            const grey = Math.round(0.15 * (rgb[0] + rgb[1] + rgb[2]) / 3 + 0.85 * 150);
            rgb = [grey, grey, grey];
          }
          if (state.isolate) a = 0;
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
    (window.__s3 ||= {}).edges = { ...(window.__s3.edges || {}), [this.atlas]: this.edges.ms };
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
    if (state.mode === "atlas") this.markEdges();
    this.cleanSlice();
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
      range.addEventListener("input", () => this.setPlane(axis, range.value / 1000));
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
        this.canvas.width, this.canvas.height, state.view, state.mode, state.isolate, [...this.focus],
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
    if (state.mode === "stain") this.drawNotice(g, 8 * dpr, 8 * dpr, dpr);
    if (!tile) return;
    const [left, top, w, hgt] = tile.leftTopWidthHeight;
    // Niivue: horizontal mm = leftTopMM[0] + h * fovMM[0], h = (X - left) / w (also when w < 0,
    // radiological); vertical mm = leftTopMM[1] + D * fovMM[1], D = 1 - (Y - top) / height.
    const toX = (mm) => left + ((mm - tile.leftTopMM[0]) / tile.fovMM[0]) * w;
    const toY = (mm) => top + (1 - (mm - tile.leftTopMM[1]) / tile.fovMM[1]) * hgt;
    if (state.mode === "atlas") this.drawContours(g, toX, toY, dpr);
    if (state.mode === "stain") {
      this.paintStain(g, tile, dpr);
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
    const fg = state.mode === "stain" ? "rgb(40 30 50)" : getComputedStyle(this.section).color;
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
    if (state.mode === "stain") this.drawNotice(g, x0 + 8 * dpr, top + 28 * dpr, dpr);
  }

  drawNotice(g, x, y, dpr) {
    g.save();
    g.font = `600 ${12 * dpr}px system-ui, sans-serif`;
    g.textBaseline = "top";
    g.textAlign = "left";
    const pad = 5 * dpr;
    const w = g.measureText(NOTICE).width + 2 * pad;
    const hh = 12 * dpr + 2 * pad;
    g.fillStyle = "rgb(255 248 225 / 0.95)";
    g.strokeStyle = "rgb(150 100 0)";
    g.lineWidth = dpr;
    g.beginPath();
    g.roundRect(x, y, w, hh, 4 * dpr);
    g.fill();
    g.stroke();
    g.fillStyle = "rgb(90 55 0)";
    g.fillText(NOTICE, x + pad, y + pad + dpr);
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
    const raw = loc && loc.values && loc.values[0] ? Math.round(loc.values[0].value) : 0;
    const v = this.regionOf(raw);
    this.showTag(v ? this.rows[v] : null);
    if (v === this.selectedIndex) return;
    this.selectedIndex = v || null;
    const row = v ? this.rows[v] : null;
    this.focus = new Set(row ? [row.index] : []);
    this.apply();
    this.onPick(row ? regionFromRow(this.atlas, row) : null);
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

  // Highlight what the other atlas asked for: same side, by Waxholm ancestor or Julich area.
  highlight(partner) {
    this.selectedIndex = null;
    this.focus = new Set(
      partner
        ? this.rows
            .filter((r) => r.index && r.side === partner.side)
            .filter((r) =>
              partner.waxholmId != null
                ? (r.path || []).includes(partner.waxholmId)
                : partner.areaIds.includes(r.area_id),
            )
            .map((r) => r.index)
        : [],
    );
    if (this.tag) this.tag.hidden = true;
    if (!this.vol) return; // still loading
    this.apply();
    if (this.focus.size) this.goTo(this.focus);
  }
}

const data = await loadData();
const viewers = (window.__viewers = {
  waxholm: new VolumeViewer(document.getElementById("waxholm"), "waxholm", data.waxholm.labels.rows),
  julich: new VolumeViewer(document.getElementById("julich"), "julich", data.julich.labels.rows),
});
for (const [atlas, v] of Object.entries(viewers)) {
  renderLicence(v.section.querySelector(".licence"), data[atlas].licence);
  panelPicked(v.panel, null);
  v.onPick = (region) => {
    const other = viewers[atlas === "waxholm" ? "julich" : "waxholm"];
    const pair = region ? pairOf(region, data.pairs) : null;
    panelPicked(v.panel, region, pair);
    other.highlight(region ? partnerOf(region, pair) : null);
    panelPartner(other.panel, region, pair);
  };
}

function toggle(id, apply) {
  const b = document.getElementById(id);
  b.addEventListener("click", () => {
    apply(b);
    Object.values(viewers).forEach((v) => v.apply());
  });
  return b;
}
const b3d = toggle("view3d", () => {
  state.view = "3d";
  b3d.setAttribute("aria-pressed", "true");
  bSlice.setAttribute("aria-pressed", "false");
});
const bSlice = toggle("viewSlice", () => {
  state.view = "slice";
  state.clip = true; // the 3D cut and the 2D slice go together (P1)
  Object.values(viewers).forEach((v) => v.nv.setRenderAzimuthElevation(AZIMUTH, ELEVATION));
  document.getElementById("clip").setAttribute("aria-pressed", "true");
  b3d.setAttribute("aria-pressed", "false");
  bSlice.setAttribute("aria-pressed", "true");
});
toggle("clip", (b) => {
  state.clip = !state.clip;
  b.setAttribute("aria-pressed", String(state.clip));
});
// Step 7.6: the mode selector, one mode at a time.
const modeButtons = [...document.querySelectorAll("[data-mode]")];
const showMode = () =>
  modeButtons.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.mode === state.mode)));
showMode();
for (const b of modeButtons) {
  if (!MODES.includes(b.dataset.mode)) continue;
  toggle(b.id, () => {
    state.mode = b.dataset.mode;
    showMode();
  });
}
toggle("isolate", (b) => {
  state.isolate = !state.isolate;
  b.setAttribute("aria-pressed", String(state.isolate));
});
new ResizeObserver(() => state.view !== "3d" && Object.values(viewers).forEach((v) => v.layout()))
  .observe(document.querySelector(".viewers"));

await Promise.all(
  Object.entries(viewers).map(([atlas, v]) =>
    v.load(`../data/${atlas}/labels.nii.gz`).then(() => markReady(atlas)),
  ),
);

// Measurement hook for results/maqueta-c.md: rotate both renders for ms and count frames.
window.__spin = (ms = 3000) =>
  new Promise((done) => {
    const vs = Object.values(viewers);
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
