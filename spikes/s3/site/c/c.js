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
const OFFSET = 8;
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

const state = { view: "3d", clip: false, isolate: false };

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
    for (const r of this.rows) {
      const focused = r.index && this.focus.has(r.index);
      let [red, green, blue] = r.index ? hex(focused ? strong(colourOf(r)) : colourOf(r)) : [0, 0, 0];
      let a = r.index ? 255 : 0;
      // While something is selected the rest goes grey (alpha barely shows in the 3D render of
      // a label volume), or disappears when isolating.
      if (r.index && this.focus.size && !this.focus.has(r.index)) {
        const grey = Math.round(0.15 * (red + green + blue) / 3 + 0.85 * 150);
        [red, green, blue] = [grey, grey, grey];
        if (state.isolate) a = 0;
      }
      R.push(red); G.push(green); B.push(blue); A.push(a); I.push(r.index ? r.index + OFFSET : 0);
      labels.push(r.index ? `${r.acronym || r.name} ${r.side}` : "");
    }
    return { R, G, B, A, I, labels };
  }

  apply() {
    if (!this.vol) return;
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
      const key = tile
        ? JSON.stringify([tile.leftTopWidthHeight, tile.leftTopMM, tile.fovMM, this.nv.scene.crosshairPos,
          this.canvas.width, this.canvas.height])
        : "";
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
    if (!tile) return;
    const [left, top, w, hgt] = tile.leftTopWidthHeight;
    // Niivue: horizontal mm = leftTopMM[0] + h * fovMM[0], h = (X - left) / w (also when w < 0,
    // radiological); vertical mm = leftTopMM[1] + D * fovMM[1], D = 1 - (Y - top) / height.
    const toX = (mm) => left + ((mm - tile.leftTopMM[0]) / tile.fovMM[0]) * w;
    const toY = (mm) => top + (1 - (mm - tile.leftTopMM[1]) / tile.fovMM[1]) * hgt;
    const c = this.coords;
    const fg = getComputedStyle(this.section).color;
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
    const v = raw > OFFSET ? raw - OFFSET : 0;
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
