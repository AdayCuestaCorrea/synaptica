// Neuro Atlas, step 4 (SCOPE v164): measures the atlas page of the built site in a headless
// Chromium (Brave here), driven through the DevTools protocol, under the conditions of spike S3
// (spikes/s3/measure.mjs, from which the client and touch helpers are copied). No dependencies.
//
//   uv run syn site --out DIR
//   node scripts/atlas_serve.mjs DIR &        # gzips text as GitHub Pages does; kill <PID> after
//   node scripts/atlas_measure.mjs            # writes docs/fases/atlas-medidas/<date>.json
//
// Two scenarios, RUNS each, fresh profile and no cache:
// - phone: 390 x 844 CSS px, DPR 3, touch, «Slow 4G» and CPU x4 (pessimistic: software WebGL).
//   Text and list on screen, the human brain ready (only the brain shown loads, UX-1 C), bytes,
//   a tap by parts (window.__atlasPerf.taps), drag, pinch and frames per second.
// - desktop: 1280 x 900, DPR 1, mouse, no network limit, CPU x4: both brains, so a tap on the
//   rat also repaints the human (the other brain's part of the tap).
// Only 127.0.0.1 is visited. BROWSER (default brave), BASE (default http://127.0.0.1:8767).

import { spawn } from "node:child_process";
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const BASE = process.env.BASE || "http://127.0.0.1:8767";
const BROWSER = process.env.BROWSER || "brave";
const PORT = 9335;
const RUNS = Number(process.env.RUNS || 3);
const PAGE = `${BASE}/es/atlas.html${process.env.QUERY || ""}`; // QUERY: e.g. ?ver=4 (UX-4 C trial)
// DevTools "Slow 4G" preset: 1.6 Mbps down, 750 kbps up, 562.5 ms RTT, DevTools' 0.9 factor.
const SLOW_4G = {
  offline: false,
  latency: 562.5,
  downloadThroughput: ((1.6 * 1000 * 1000) / 8) * 0.9,
  uploadThroughput: ((750 * 1000) / 8) * 0.9,
};
const NO_LIMIT = { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1 };
const SCENARIOS = {
  phone: { width: 390, height: 844, dpr: 3, mobile: true, net: SLOW_4G, cpu: 4, wait: ["julich"] },
  desktop: { width: 1280, height: 900, dpr: 1, mobile: false, net: NO_LIMIT, cpu: 4, wait: ["julich", "waxholm"] },
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

class CDP {
  constructor(ws) {
    this.ws = ws;
    this.id = 0;
    this.pending = new Map();
    this.handlers = [];
    ws.addEventListener("message", (m) => {
      const msg = JSON.parse(m.data);
      if (msg.id && this.pending.has(msg.id)) {
        const { ok, ko } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        msg.error ? ko(new Error(JSON.stringify(msg.error))) : ok(msg.result);
      } else if (msg.method) {
        for (const h of this.handlers) h(msg);
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
  on(h) {
    this.handlers.push(h);
  }
  async eval(expr, awaitPromise = true) {
    const r = await this.send("Runtime.evaluate", {
      expression: expr,
      awaitPromise,
      returnByValue: true,
    });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || expr);
    return r.result.value;
  }
  close() {
    this.ws.close();
  }
}

async function browser() {
  const profile = mkdtempSync(join(tmpdir(), "atlas-measure-"));
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
      if (r.ok) return { proc, profile, version: (await r.json()).Browser };
    } catch {}
    await sleep(100);
  }
  throw new Error("browser did not start");
}

async function tap(cdp, x, y) {
  await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x, y }] });
  await sleep(60);
  await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
}

async function drag(cdp, x, y, dx) {
  await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x, y }] });
  for (let i = 1; i <= 10; i++) {
    await cdp.send("Input.dispatchTouchEvent", {
      type: "touchMove",
      touchPoints: [{ x: x + (dx * i) / 10, y }],
    });
    await sleep(30);
  }
  await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
}

async function pinch(cdp, x, y, d) {
  const pts = (k) => [
    { x: x - 20 - k, y, id: 1 },
    { x: x + 20 + k, y, id: 2 },
  ];
  await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: pts(0) });
  for (let i = 1; i <= 10; i++) {
    await cdp.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: pts((d * i) / 10) });
    await sleep(30);
  }
  await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
}

// Mouse click for the desktop scenario.
async function click(cdp, x, y) {
  for (const type of ["mousePressed", "mouseReleased"]) {
    await cdp.send("Input.dispatchMouseEvent", { type, x, y, button: "left", clickCount: 1 });
    await sleep(60);
  }
}

const VIEW_STATE = (atlas) => `(() => { const s = window.__atlas.${atlas}.nv.scene;
  return { azimuth: +s.renderAzimuth.toFixed(1), zoom: +s.volScaleMultiplier.toFixed(3) }; })()`;

async function run(name, i) {
  const sc = SCENARIOS[name];
  const res = await (await fetch(`http://127.0.0.1:${PORT}/json/new?about:blank`, { method: "PUT" })).json();
  const cdp = await CDP.open(res.webSocketDebuggerUrl);
  const reqs = new Map();
  cdp.on((m) => {
    const p = m.params;
    if (m.method === "Network.requestWillBeSent") reqs.set(p.requestId, { url: p.request.url, t: p.timestamp });
    if (m.method === "Network.loadingFinished") {
      const r = reqs.get(p.requestId);
      if (r) r.bytes = p.encodedDataLength;
    }
    if (m.method === "Network.loadingFailed") {
      const r = reqs.get(p.requestId);
      if (r) r.failed = p.errorText;
    }
  });
  await cdp.send("Network.enable");
  await cdp.send("Network.setCacheDisabled", { cacheDisabled: true });
  await cdp.send("Page.enable");
  await cdp.send("Runtime.enable");
  await cdp.send("Emulation.setDeviceMetricsOverride", {
    width: sc.width, height: sc.height, deviceScaleFactor: sc.dpr, mobile: sc.mobile,
  });
  if (sc.mobile) await cdp.send("Emulation.setTouchEmulationEnabled", { enabled: true, maxTouchPoints: 5 });
  await cdp.send("Network.emulateNetworkConditions", sc.net);
  await cdp.send("Emulation.setCPUThrottlingRate", { rate: sc.cpu });

  const t0 = Date.now();
  await cdp.send("Page.navigate", { url: PAGE });
  const marks = sc.wait.map((a) => `atlas-${a}-ready`);
  let ready = false;
  while (!ready && Date.now() - t0 < 180000) {
    await sleep(200);
    try {
      ready = await cdp.eval(`${JSON.stringify(marks)}.every((m) => performance.getEntriesByName(m).length)`, false);
    } catch {}
  }
  const page = await cdp.eval(`(() => {
    const nav = performance.getEntriesByType("navigation")[0];
    const fcp = performance.getEntriesByName("first-contentful-paint")[0];
    const mark = (a) => (performance.getEntriesByName("atlas-" + a + "-ready")[0] || {}).startTime;
    return { firstPaintMs: fcp && Math.round(fcp.startTime), domReadyMs: Math.round(nav.domContentLoadedEventEnd),
      loadMs: Math.round(nav.loadEventEnd), humanReadyMs: Math.round(mark("julich")) || null,
      ratReadyMs: Math.round(mark("waxholm")) || null,
      // When each file started and finished arriving (ms from navigation), to see what waits.
      timeline: performance.getEntriesByType("resource").map((r) =>
        [r.name.replace(location.origin, ""), Math.round(r.startTime), Math.round(r.responseEnd)]) };
  })()`, false);
  await sleep(1500);
  const loadedBrains = await cdp.eval("Object.entries(window.__atlas).filter(([, v]) => v.vol).map(([k]) => k)", false);

  // A tap (or click) on a region of the brain in view: the human on a phone, the rat on desktop.
  const atlas = sc.mobile ? "julich" : "waxholm";
  const brain = atlas === "julich" ? "human" : "rat";
  await cdp.eval(`document.querySelector('#${brain} .stage').scrollIntoView({ block: "center" })`, false);
  await sleep(500);
  const [bx, by, bw, bh] = await cdp.eval(`(() => { const r = document.querySelector('#${brain} .stage canvas').getBoundingClientRect();
      return [r.left, r.top, r.width, r.height]; })()`, false);
  const taps = [];
  for (const [fx, fy] of [[0.5, 0.45], [0.45, 0.5], [0.55, 0.4], [0.4, 0.4], [0.6, 0.5], [0.5, 0.55]]) {
    await cdp.eval("(window.__atlasPerf ||= {}).taps = []; window.__atlasPerf.partner = []", false);
    if (sc.mobile) await tap(cdp, bx + bw * fx, by + bh * fy);
    else await click(cdp, bx + bw * fx, by + bh * fy);
    await sleep(1500);
    const got = await cdp.eval("window.__atlasPerf.taps", false);
    if (got && got.length) taps.push({ at: [fx, fy], ...got[0],
      otherBrainLater: (await cdp.eval("window.__atlasPerf.partner", false))[0] ?? null,
      panel: await cdp.eval(`(document.querySelector('#${brain} .panel h3') || {}).textContent || null`, false) });
    if (taps.length >= 3) break;
  }
  let touch = null;
  if (sc.mobile) {
    const before = await cdp.eval(VIEW_STATE(atlas), false);
    await drag(cdp, bx + bw * 0.3, by + bh * 0.5, bw * 0.4);
    await sleep(800);
    const afterDrag = await cdp.eval(VIEW_STATE(atlas), false);
    await pinch(cdp, bx + bw * 0.5, by + bh * 0.5, 80);
    await sleep(800);
    touch = { before, afterDrag, afterPinch: await cdp.eval(VIEW_STATE(atlas), false) };
  }
  const fps = await cdp.eval("window.__spin(3000)");
  cdp.close();
  await fetch(`http://127.0.0.1:${PORT}/json/close/${res.id}`);

  const list = [...reqs.values()].filter((r) => !/^(data|blob):/.test(r.url));
  const round = (x) => (x == null ? null : Math.round(x * 10) / 10);
  return {
    scenario: name, run: i, ...page, loadedBrains,
    requests: list.length,
    bytes: list.reduce((a, r) => a + (r.bytes || 0), 0),
    hosts: [...new Set(list.map((r) => new URL(r.url).host))],
    failed: list.filter((r) => r.failed).map((r) => [r.url, r.failed]),
    files: list.map((r) => [new URL(r.url).pathname, r.bytes]),
    taps: taps.map((t) => ({ ...t, read: round(t.read), thisBrain: round(t.thisBrain),
      otherBrain: round(t.otherBrain), frame: round(t.frame), otherBrainLater: round(t.otherBrainLater) })),
    touch, fps,
  };
}

const { proc, profile, version } = await browser();
try {
  const runs = [];
  for (const name of (process.env.SCENARIOS || "phone,desktop").split(",")) {
    for (let i = 1; i <= RUNS; i++) runs.push(await run(name, i));
  }
  const out = { page: PAGE, date: new Date().toISOString(), browser: version,
    scenarios: Object.fromEntries(Object.entries(SCENARIOS).map(([k, s]) => [k, { ...s, net: s.net === SLOW_4G ? "Slow 4G" : "none" }])),
    runs };
  const dir = join(dirname(fileURLToPath(import.meta.url)), "..", "docs", "fases", "atlas-medidas");
  mkdirSync(dir, { recursive: true });
  const file = join(dir, `${process.env.TAG || out.date.slice(0, 10)}.json`);
  writeFileSync(file, JSON.stringify(out, null, 2) + "\n");
  console.log(JSON.stringify(runs.map(({ files, ...r }) => r), null, 1));
} finally {
  proc.kill();
  await sleep(300);
  rmSync(profile, { recursive: true, force: true });
}
