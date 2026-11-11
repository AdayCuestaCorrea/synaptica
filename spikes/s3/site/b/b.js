// Spike S3, mock-up B: three.js with our own meshes (one glTF + Draco per atlas). Throwaway code.
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { DRACOLoader } from "three/addons/loaders/DRACOLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import {
  t, loadData, fillTexts, renderPanel, renderLicence, pairOf, partnerOf, markReady,
  colourOf, strong,
} from "../common/common.js";

fillTexts();

const draco = new DRACOLoader();
draco.setDecoderPath("../vendor/three-0.187.0/examples/jsm/libs/draco/gltf/");
draco.setDecoderConfig({ type: "wasm" });
const loader = new GLTFLoader();
loader.setDRACOLoader(draco);

const SELECT = new THREE.Color(0x3a3a3a); // emissive for the clicked region
const PARTNER = new THREE.Color(0x6a5200); // emissive for the equivalent in the other atlas
// Same initial direction in both viewers (glTF frame: x right, y up, z back): front-left-top.
const VIEW_DIR = new THREE.Vector3(-0.85, 0.45, -0.55).normalize();

const state = { cortexHidden: false, isolate: false };

class MeshViewer {
  constructor(section, atlas) {
    this.atlas = atlas;
    this.section = section;
    this.canvas = section.querySelector("canvas");
    this.panel = section.querySelector(".panel");
    this.status = section.querySelector(".status");
    this.regions = [];
    this.outline = null;
    this.selected = null; // mesh
    this.partner = null; // {side, waxholmId | areaIds}
    this.onPick = () => {};

    this.renderer = new THREE.WebGLRenderer({ canvas: this.canvas, antialias: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(
      matchMedia("(prefers-color-scheme: dark)").matches ? 0x1b1b20 : 0xf2f1ee,
    );
    this.camera = new THREE.PerspectiveCamera(35, 1, 0.1, 5000);
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x666666, 1.6));
    const key = new THREE.DirectionalLight(0xffffff, 1.4);
    key.position.set(0.3, 1, 1);
    this.camera.add(key); // light follows the camera
    this.scene.add(this.camera);
    this.controls = new OrbitControls(this.camera, this.canvas);
    this.controls.enableDamping = true;
    this.controls.addEventListener("change", () => this.requestRender());
    new ResizeObserver(() => this.resize()).observe(this.canvas);
    this.pickHandlers();
  }

  async load(url, rows) {
    const gltf = await loader.loadAsync(url);
    gltf.scene.traverse((o) => {
      if (!o.isMesh) return;
      o.geometry.computeVertexNormals();
      const x = o.userData; // node extras
      if (x.kind === "outline") {
        o.material = new THREE.MeshStandardMaterial({
          color: 0xb9b4aa, transparent: true, opacity: 0.16, depthWrite: false, roughness: 0.9,
        });
        o.renderOrder = 2; // after the opaque regions, so they show through
        this.outline = o;
      } else {
        // Same row as in labels.json: Julich-Brain nodes carry the index, Waxholm ones the id.
        // A Waxholm parent such as HF has no row of its own: take its family from a descendant.
        const row = x.index != null
          ? rows[x.index]
          : rows.find((r) => r.id === x.id) || rows.find((r) => r.path && r.path.includes(x.id));
        x.base = row ? colourOf(row) : x.color || "#888888";
        o.material = new THREE.MeshStandardMaterial({
          color: new THREE.Color(x.base), roughness: 0.55, metalness: 0,
        });
        this.regions.push(o);
      }
    });
    this.scene.add(gltf.scene);
    // Fit the camera to the brain outline.
    const box = new THREE.Box3().setFromObject(this.outline || gltf.scene);
    const centre = box.getCenter(new THREE.Vector3());
    const radius = box.getSize(new THREE.Vector3()).length() / 2;
    const dist = radius / Math.sin(THREE.MathUtils.degToRad(this.camera.fov / 2));
    this.camera.position.copy(centre).addScaledVector(VIEW_DIR, dist * 0.95);
    this.camera.near = dist / 100;
    this.camera.far = dist * 10;
    this.camera.updateProjectionMatrix();
    this.controls.target.copy(centre);
    this.controls.update();
    this.status.remove();
    this.resize();
    this.apply();
  }

  pickHandlers() {
    // A click is a press and release that barely moves: a drag rotates instead.
    let down = null;
    this.canvas.addEventListener("pointerdown", (e) => {
      down = { x: e.clientX, y: e.clientY, t: performance.now() };
    });
    this.canvas.addEventListener("pointerup", (e) => {
      if (!down) return;
      const moved = Math.hypot(e.clientX - down.x, e.clientY - down.y);
      const quick = performance.now() - down.t < 600;
      down = null;
      if (moved > 6 || !quick) return;
      const r = this.canvas.getBoundingClientRect();
      const ndc = new THREE.Vector2(
        ((e.clientX - r.left) / r.width) * 2 - 1,
        -((e.clientY - r.top) / r.height) * 2 + 1,
      );
      const ray = new THREE.Raycaster();
      ray.setFromCamera(ndc, this.camera);
      const pickable = this.regions.filter((m) => m.visible);
      const hit = ray.intersectObjects(pickable, false)[0];
      this.select(hit ? hit.object : null);
      this.onPick(hit ? this.regionOf(hit.object) : null);
    });
  }

  regionOf(mesh) {
    const x = mesh.userData;
    if (this.atlas === "waxholm") {
      return { atlas: "waxholm", side: x.side, id: x.id, name: x.name, acronym: x.acronym, path: [x.id] };
    }
    return {
      atlas: "julich", side: x.side, id: x.id, name: x.name, label: x.label, areaId: x.area_id,
    };
  }

  isPartner(mesh) {
    const p = this.partner;
    if (!p || mesh.userData.side !== p.side) return false;
    return p.waxholmId != null
      ? mesh.userData.id === p.waxholmId
      : p.areaIds.includes(mesh.userData.area_id);
  }

  select(mesh) {
    this.selected = mesh;
    if (mesh) this.partner = null; // a click here replaces a highlight coming from the other atlas
    this.apply();
  }

  highlight(partner) {
    this.selected = null;
    this.partner = partner;
    this.apply();
  }

  apply() {
    const focus = this.regions.filter((m) => m === this.selected || this.isPartner(m));
    for (const m of this.regions) {
      const on = focus.includes(m);
      m.material.emissive.copy(m === this.selected ? SELECT : on ? PARTNER : new THREE.Color(0));
      m.material.color.set(on ? strong(m.userData.base) : m.userData.base);
      const dim = focus.length > 0 && !on;
      m.visible = !(state.isolate && dim);
      m.material.transparent = dim;
      m.material.opacity = dim ? 0.3 : 1;
      m.material.depthWrite = !dim;
    }
    if (this.outline) this.outline.visible = !state.cortexHidden && !(state.isolate && focus.length);
    this.requestRender();
  }

  resize() {
    const w = this.canvas.clientWidth;
    const h = this.canvas.clientHeight;
    if (!w || !h) return;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    this.requestRender();
  }

  // Render on demand: only while something moves (damping included), to spare phone batteries.
  requestRender() {
    if (this.pending) return;
    this.pending = true;
    requestAnimationFrame(() => {
      this.pending = false;
      const moving = this.controls.update();
      this.renderer.render(this.scene, this.camera);
      this.frames = (this.frames || 0) + 1;
      if (moving || this.spinning) this.requestRender();
    });
  }
}

const data = await loadData();
const viewers = (window.__viewers = {
  waxholm: new MeshViewer(document.getElementById("waxholm"), "waxholm"),
  julich: new MeshViewer(document.getElementById("julich"), "julich"),
});
for (const [atlas, v] of Object.entries(viewers)) {
  renderLicence(v.section.querySelector(".licence"), data[atlas].licence);
  renderPanel(v.panel, null, data.pairs);
  v.onPick = (region) => {
    const other = viewers[atlas === "waxholm" ? "julich" : "waxholm"];
    renderPanel(v.panel, region, data.pairs);
    const partner = region ? partnerOf(region, pairOf(region, data.pairs)) : null;
    other.highlight(partner);
    renderPanel(other.panel, null, data.pairs);
  };
}

const cortexBtn = document.getElementById("cortex");
cortexBtn.addEventListener("click", () => {
  state.cortexHidden = !state.cortexHidden;
  cortexBtn.setAttribute("aria-pressed", String(state.cortexHidden));
  cortexBtn.textContent = state.cortexHidden ? t.cortexHidden : t.cortexShown;
  Object.values(viewers).forEach((v) => v.apply());
});
const isoBtn = document.getElementById("isolate");
isoBtn.addEventListener("click", () => {
  state.isolate = !state.isolate;
  isoBtn.setAttribute("aria-pressed", String(state.isolate));
  Object.values(viewers).forEach((v) => v.apply());
});

await Promise.all(
  Object.entries(viewers).map(([atlas, v]) =>
    v.load(`../data/${atlas}/${atlas}.glb`, data[atlas].labels.rows).then(() => markReady(atlas)),
  ),
);

// Measurement hook for results/maqueta-b.md: spin both viewers for ms and count frames.
window.__spin = (ms = 3000) =>
  new Promise((done) => {
    const vs = Object.values(viewers);
    vs.forEach((v) => {
      v.frames = 0;
      v.spinning = true;
      v.controls.autoRotate = true;
      v.controls.autoRotateSpeed = 6;
      v.requestRender();
    });
    setTimeout(() => {
      vs.forEach((v) => {
        v.spinning = false;
        v.controls.autoRotate = false;
      });
      done(Object.fromEntries(vs.map((v) => [v.atlas, Math.round((v.frames * 1000) / ms)])));
    }, ms);
  });
