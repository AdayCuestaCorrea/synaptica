// Neuro Atlas, step 4 (SCOPE v164): static server for a built site that gzips text files, as GitHub Pages
// does (html, css, js, json, md). Binary files (.glb, .nii.gz, .wasm) go as they are.
// Copied from spikes/s3/serve-gzip.mjs. Local only:  node scripts/atlas_serve.mjs DIR  → http://127.0.0.1:8767
import { createServer } from "node:http";
import { readFile, stat } from "node:fs/promises";
import { gzipSync } from "node:zlib";
import { join, extname, dirname, normalize } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = process.argv[2] || join(dirname(fileURLToPath(import.meta.url)), "..", "site", "_build");
const TYPES = {
  ".webp": "image/webp", ".svg": "image/svg+xml", ".woff2": "font/woff2",
  ".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "text/javascript",
  ".mjs": "text/javascript", ".json": "application/json", ".md": "text/markdown",
  ".glb": "model/gltf-binary", ".gz": "application/gzip", ".wasm": "application/wasm",
};
const GZIP = new Set([".html", ".css", ".js", ".mjs", ".json", ".md"]);

createServer(async (req, res) => {
  let path = normalize(decodeURIComponent(new URL(req.url, "http://x").pathname));
  if (path.includes("..")) return res.writeHead(400).end();
  let file = join(ROOT, path);
  try {
    if ((await stat(file)).isDirectory()) file = join(file, "index.html");
    let body = await readFile(file);
    const ext = extname(file);
    const headers = { "Content-Type": TYPES[ext] || "application/octet-stream" };
    if (GZIP.has(ext) && /gzip/.test(req.headers["accept-encoding"] || "")) {
      body = gzipSync(body, { level: 6 });
      headers["Content-Encoding"] = "gzip";
    }
    res.writeHead(200, headers).end(body);
  } catch {
    res.writeHead(404).end();
  }
}).listen(8767, "127.0.0.1");
