// Spike S3, mock-up C: Niivue with our own label volumes (one NIfTI per atlas). Throwaway code.
// Niivue is loaded as a classic script (vendor/niivue-0.69.0/niivue.umd.js): global `niivue`.
import {
  t, loadData, fillTexts, renderPanel, renderLicence, regionFromRow, pairOf, partnerOf, markReady,
  colourOf, strong,
} from "../common/common.js";

fillTexts();
const { Niivue, SLICE_TYPE } = window.niivue;

const dark = matchMedia("(prefers-color-scheme: dark)").matches;
const BACK = dark ? [0.106, 0.106, 0.125, 1] : [0.949, 0.945, 0.933, 1];
// Same starting direction in both viewers, and as in B: from the front left, slightly above.
// Measured: azimuth 90 looks at the left side, 120 at the left side from the front.
const AZIMUTH = 120;
// Niivue 0.69 lifts every value above the scale minimum to at least 2/256 of the colour table
// (its issue 1139): with ~450 labels, background and the first labels all land on entry 3-4,
// opaque. So, in this viewer only, labels move up by OFFSET when the volume is loaded: entries
// 0..OFFSET-1 are left empty and transparent. Data files keep the plain indices.
const OFFSET = 8;
const ELEVATION = 20;

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
      show3Dcrosshair: false,
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
    this.nv.setRenderAzimuthElevation(AZIMUTH, ELEVATION);
    this.nv.onLocationChange = (loc) => this.picked(loc);
    this.singleClickPicks();
    this.status.remove();
    this.apply();
  }

  // In the 3D view Niivue only reads the voxel under the pointer (depth picking) on a double
  // click, double tap or long press. To behave like B, a short click that barely moves sends it
  // the double click it listens for. 2D slices already pick on a single click.
  singleClickPicks() {
    let down = null;
    this.canvas.addEventListener("pointerdown", (e) => {
      down = { x: e.clientX, y: e.clientY, t: performance.now() };
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

  layout() {
    const nv = this.nv;
    nv.setClipPlane(state.clip ? [0, AZIMUTH - 180, 0] : [2, 0, 0]);
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
    if (v === this.selectedIndex) return;
    this.selectedIndex = v || null;
    const row = v ? this.rows[v] : null;
    this.focus = new Set(row ? [row.index] : []);
    this.apply();
    this.onPick(row ? regionFromRow(this.atlas, row) : null);
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
    this.apply();
  }
}

const data = await loadData();
const viewers = (window.__viewers = {
  waxholm: new VolumeViewer(document.getElementById("waxholm"), "waxholm", data.waxholm.labels.rows),
  julich: new VolumeViewer(document.getElementById("julich"), "julich", data.julich.labels.rows),
});
for (const [atlas, v] of Object.entries(viewers)) {
  renderLicence(v.section.querySelector(".licence"), data[atlas].licence);
  renderPanel(v.panel, null, data.pairs);
  v.onPick = (region) => {
    const other = viewers[atlas === "waxholm" ? "julich" : "waxholm"];
    renderPanel(v.panel, region, data.pairs);
    other.highlight(region ? partnerOf(region, pairOf(region, data.pairs)) : null);
    renderPanel(other.panel, null, data.pairs);
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
