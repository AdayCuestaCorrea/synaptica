// Phase 2, Neuro Atlas UX study: still images of the S3 prototype (mock-up C) for the static
// UX mock-ups in this folder. One image per atlas, never both brains in one file (licences).
// Throwaway code; no dependencies (Node >= 22 has WebSocket). CDP client copied from
// spikes/s3/measure.mjs.
//
//   python -m http.server 8766 --bind 127.0.0.1 --directory spikes/s3/site &
//   node spikes/atlas-ux/capture.mjs
//
// Only 127.0.0.1 is visited. The browser binary is BROWSER (default: brave).
import { spawn } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync, mkdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const BASE = process.env.BASE || "http://127.0.0.1:8766";
const BROWSER = process.env.BROWSER || "brave";
const PORT = 9334;
const OUT = join(dirname(fileURLToPath(import.meta.url)), "img");
// --atlas-bg of the site's «Noche» style (site/static/noche.css).
const ATLAS_BG = [16 / 255, 26 / 255, 51 / 255, 1];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

class CDP {
  constructor(ws) {
    this.ws = ws;
    this.id = 0;
    this.pending = new Map();
    ws.addEventListener("message", (m) => {
      const msg = JSON.parse(m.data);
      if (msg.id && this.pending.has(msg.id)) {
        const { ok, ko } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        msg.error ? ko(new Error(JSON.stringify(msg.error))) : ok(msg.result);
      }
    });
  }
  static async open(url) {
    const ws = new WebSocket(url);
    await new Promise((ok, ko) => {
      ws.addEventListener("open", ok);
      ws.addEventListener("error", ko);
    });
    return new CDP(ws);
  }
  send(method, params = {}) {
    const id = ++this.id;
    this.ws.send(JSON.stringify({ id, method, params }));
    return new Promise((ok, ko) => this.pending.set(id, { ok, ko }));
  }
  async eval(expr) {
    const r = await this.send("Runtime.evaluate", {
      expression: expr,
      awaitPromise: true,
      returnByValue: true,
    });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || expr);
    return r.result.value;
  }
}

async function browser() {
  const profile = mkdtempSync(join(tmpdir(), "atlas-ux-"));
  const proc = spawn(
    BROWSER,
    [
      "--headless=new",
      `--remote-debugging-port=${PORT}`,
      `--user-data-dir=${profile}`,
      "--no-first-run",
      "--no-default-browser-check",
      "--disable-extensions",
      "--disable-background-networking",
      "--disable-component-update",
      "--disable-sync",
      "--enable-unsafe-swiftshader",
      "about:blank",
    ],
    { stdio: "ignore" },
  );
  for (let i = 0; i < 100; i++) {
    try {
      const r = await fetch(`http://127.0.0.1:${PORT}/json/version`);
      if (r.ok) return { proc, profile };
    } catch {}
    await sleep(100);
  }
  throw new Error("browser did not start");
}

// Show one viewer alone, large, and save its canvas (with the page overlays on it).
async function shot(cdp, id, name) {
  const other = id === "waxholm" ? "julich" : "waxholm";
  await cdp.eval(`(() => {
    document.getElementById(${JSON.stringify(other)}).style.display = "none";
    const v = document.getElementById(${JSON.stringify(id)});
    v.style.display = "";
    v.querySelector(".stage").style.height = "720px";
    window.dispatchEvent(new Event("resize"));
  })()`);
  await sleep(2500);
  const box = await cdp.eval(`(() => {
    const r = document.querySelector("#${id} .stage canvas").getBoundingClientRect();
    return { x: r.x + scrollX, y: r.y + scrollY, width: r.width, height: r.height };
  })()`);
  const r = await cdp.send("Page.captureScreenshot", {
    format: "webp",
    quality: 88,
    clip: { ...box, scale: 1 },
    captureBeyondViewport: true,
  });
  writeFileSync(join(OUT, `${name}.webp`), Buffer.from(r.data, "base64"));
  await cdp.eval(`(() => {
    document.getElementById(${JSON.stringify(other)}).style.display = "";
    document.querySelectorAll(".stage").forEach((s) => (s.style.height = ""));
  })()`);
  console.log("saved", name);
}

async function pick(cdp, id, query) {
  await cdp.eval(`(() => {
    const input = document.querySelector("#${id} .search input");
    input.value = ${JSON.stringify(query)};
    input.dispatchEvent(new Event("input"));
    const li = document.querySelector("#${id} .search li[role=option]");
    li.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
    return li.textContent;
  })()`);
  await sleep(3000);
}

const click = (cdp, el) => cdp.eval(`document.getElementById(${JSON.stringify(el)}).click()`);

mkdirSync(OUT, { recursive: true });
const { proc, profile } = await browser();
try {
  const targets = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
  const cdp = await CDP.open(targets.find((t) => t.type === "page").webSocketDebuggerUrl);
  await cdp.send("Emulation.setDeviceMetricsOverride", {
    width: 1100,
    height: 1600,
    deviceScaleFactor: 2,
    mobile: false,
  });
  await cdp.send("Emulation.setEmulatedMedia", {
    features: [{ name: "prefers-color-scheme", value: "dark" }],
  });
  await cdp.send("Page.enable");
  await cdp.send("Page.navigate", { url: `${BASE}/c/` });
  for (let i = 0; i < 120; i++) {
    const ready = await cdp.eval(
      `!!(window.__viewers && __viewers.waxholm.vol && __viewers.julich.vol)`,
    ).catch(() => false);
    if (ready) break;
    await sleep(500);
  }
  await sleep(2000);
  await cdp.eval(`(() => {
    for (const v of Object.values(__viewers)) {
      v.nv.opts.backColor = ${JSON.stringify(ATLAS_BG)};
      v.nv.drawScene();
    }
  })()`);
  await sleep(1000);

  // 1. Both brains at rest, 3D only, colour mode.
  await shot(cdp, "waxholm", "rata-3d");
  await shot(cdp, "julich", "humano-3d");

  // 2. Hippocampal formation chosen in the rat; the human marks its pair. Cut open.
  await pick(cdp, "waxholm", "HF");
  await click(cdp, "clip");
  await sleep(2000);
  await shot(cdp, "waxholm", "rata-hipocampo-3d");
  await shot(cdp, "julich", "humano-hipocampo-3d");

  // 3. The same choice with the coronal slice (what «Más opciones» turns on).
  await click(cdp, "viewSlice");
  await sleep(3000);
  await shot(cdp, "waxholm", "rata-hipocampo-corte");
  await shot(cdp, "julich", "humano-hipocampo-corte");
} finally {
  proc.kill();
  await sleep(500);
  rmSync(profile, { recursive: true, force: true });
}
