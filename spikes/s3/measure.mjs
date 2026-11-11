// Spike S3, step 6: measures mock-up C (B was measured too, then removed) in a headless Chromium (Brave here), driven
// through the DevTools protocol. Throwaway code; no dependencies (Node >= 22 has WebSocket).
//
//   python -m http.server 8766 --bind 127.0.0.1 --directory spikes/s3/site &
//   node spikes/s3/measure.mjs   # writes spikes/s3/results/measure-c.json
//   BASE=http://127.0.0.1:8767 TAG=gzip node spikes/s3/measure.mjs   # with serve-gzip.mjs
//
// What it does, per run, in a fresh profile with the cache disabled:
// - a phone: 390 x 844 CSS px, DPR 3, touch; Chrome's "Slow 4G" preset and CPU x4;
// - weight: every response (encodedDataLength = bytes on the wire) and its host;
// - time until both viewers can be used (common.js marks "s3-interactive");
// - touch: tap a region (panel and highlight in the other atlas), drag to rotate, pinch to zoom;
// - smoothness: frames per second while both viewers spin for 3 s (window.__spin).
// Only 127.0.0.1 is visited. The browser binary is BROWSER (default: brave).

import { spawn } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const mock = "c";
const BASE = process.env.BASE || "http://127.0.0.1:8766";
const BROWSER = process.env.BROWSER || "brave";
const PORT = 9333;
const RUNS = Number(process.env.RUNS || 3);
// DevTools "Slow 4G" preset (the former "Fast 3G"): 1.6 Mbps down, 750 kbps up, 562.5 ms RTT,
// with DevTools' 0.9 factor on throughput.
const SLOW_4G = {
  offline: false,
  latency: 562.5,
  downloadThroughput: ((1.6 * 1000 * 1000) / 8) * 0.9,
  uploadThroughput: ((750 * 1000) / 8) * 0.9,
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
  const profile = mkdtempSync(join(tmpdir(), "s3-measure-"));
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

// State read from the page: what changes when the user rotates, zooms or picks.
const VIEW_STATE = {
  c: `(() => { const s = window.__viewers.waxholm.nv.scene;
        return { azimuth: +s.renderAzimuth.toFixed(1), zoom: +s.volScaleMultiplier.toFixed(3) }; })()`,
};
const PARTNER_STATE = {
  c: `(() => { const v = window.__viewers.julich; return [...v.focus].map(i => v.rows[i].name + " " + v.rows[i].side); })()`,
};

async function run(i) {
  const res = await (await fetch(`http://127.0.0.1:${PORT}/json/new?about:blank`, { method: "PUT" })).json();
  const cdp = await CDP.open(res.webSocketDebuggerUrl);
  const reqs = new Map();
  cdp.on((m) => {
    const p = m.params;
    if (m.method === "Network.requestWillBeSent") reqs.set(p.requestId, { url: p.request.url });
    if (m.method === "Network.responseReceived") {
      const r = reqs.get(p.requestId) || {};
      Object.assign(r, { status: p.response.status, mime: p.response.mimeType });
      reqs.set(p.requestId, r);
    }
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
    width: 390, height: 844, deviceScaleFactor: 3, mobile: true,
  });
  await cdp.send("Emulation.setTouchEmulationEnabled", { enabled: true, maxTouchPoints: 5 });
  await cdp.send("Network.emulateNetworkConditions", SLOW_4G);
  await cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 });

  const t0 = Date.now();
  await cdp.send("Page.navigate", { url: `${BASE}/${mock}/${process.env.QUERY || ""}` });
  let ready = false;
  while (!ready && Date.now() - t0 < 180000) {
    await sleep(200);
    try {
      ready = (await cdp.eval("document.body && document.body.dataset.ready", false)) === "1";
    } catch {}
  }
  const wallMs = Date.now() - t0;
  const s3 = await cdp.eval("window.__s3", false);
  await sleep(1500); // late requests, if any
  const gl = await cdp.eval(`(() => { const g = document.querySelector('canvas').getContext('webgl2');
      const e = g && g.getExtension('WEBGL_debug_renderer_info');
      return e ? g.getParameter(e.UNMASKED_RENDERER_WEBGL) : null; })()`, false);

  // Touch, on the rat viewer (the first one, in view on a phone).
  const box = await cdp.eval(`(() => { const r = document.querySelector('#waxholm canvas').getBoundingClientRect();
      return [r.left, r.top, r.width, r.height]; })()`, false);
  const [bx, by, bw, bh] = box;
  let picked = null;
  for (const [fx, fy] of [[0.5, 0.5], [0.45, 0.45], [0.55, 0.5], [0.4, 0.55], [0.6, 0.45], [0.5, 0.4]]) {
    await tap(cdp, bx + bw * fx, by + bh * fy);
    await sleep(1200);
    const h3 = await cdp.eval("(document.querySelector('#waxholm .panel h3') || {}).textContent || null", false);
    if (h3) {
      picked = { at: [fx, fy], panel: h3, partnerInOtherAtlas: await cdp.eval(PARTNER_STATE[mock], false) };
      break;
    }
  }
  const before = await cdp.eval(VIEW_STATE[mock], false);
  await drag(cdp, bx + bw * 0.3, by + bh * 0.5, bw * 0.4);
  await sleep(800);
  const afterDrag = await cdp.eval(VIEW_STATE[mock], false);
  await pinch(cdp, bx + bw * 0.5, by + bh * 0.5, 80);
  await sleep(800);
  const afterPinch = await cdp.eval(VIEW_STATE[mock], false);

  const fpsCpu4 = await cdp.eval("window.__spin(3000)");
  await cdp.send("Emulation.setCPUThrottlingRate", { rate: 1 });
  const fpsCpu1 = await cdp.eval("window.__spin(3000)");
  cdp.close();
  await fetch(`http://127.0.0.1:${PORT}/json/close/${res.id}`);

  // data: and blob: URLs are built inside the page (e.g. the Draco worker): not network.
  const all = [...reqs.values()];
  const local = all.filter((r) => /^(data|blob):/.test(r.url));
  const list = all.filter((r) => !/^(data|blob):/.test(r.url));
  const hosts = [...new Set(list.map((r) => new URL(r.url).host))];
  return {
    run: i,
    interactiveMs: s3 && s3.interactiveMs,
    edgesMs: s3 && s3.edges, // step 7.6: marking the contours (atlas mode), CPU x4
    wallMs,
    requests: list.length,
    bytes: list.reduce((a, r) => a + (r.bytes || 0), 0),
    hosts,
    inPage: local.map((r) => r.url.slice(0, 40)),
    failed: list.filter((r) => r.failed || r.status >= 400).map((r) => [r.url, r.status, r.failed]),
    files: list.map((r) => [new URL(r.url).pathname, r.bytes]),
    webglRenderer: gl,
    touch: { picked, before, afterDrag, afterPinch },
    fps: { cpu4: fpsCpu4, cpu1: fpsCpu1 },
  };
}

const { proc, profile, version } = await browser();
try {
  const runs = [];
  for (let i = 1; i <= RUNS; i++) runs.push(await run(i));
  const out = {
    mock,
    base: BASE,
    query: process.env.QUERY || "",
    date: new Date().toISOString(),
    browser: version,
    conditions: { viewport: "390x844 DPR 3, touch", network: { name: "Slow 4G", ...SLOW_4G }, cpu: 4 },
    runs,
  };
  const here = dirname(fileURLToPath(import.meta.url));
  const file = join(here, "results", `measure-${mock}${process.env.TAG ? "-" + process.env.TAG : ""}.json`);
  writeFileSync(file, JSON.stringify(out, null, 2) + "\n");
  console.log(JSON.stringify(runs.map(({ files, ...r }) => r), null, 1));
} finally {
  proc.kill();
  await sleep(300);
  rmSync(profile, { recursive: true, force: true });
}
