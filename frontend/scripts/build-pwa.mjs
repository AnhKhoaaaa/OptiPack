/**
 * Inject exact fingerprinted Vite bundles into the generated service worker.
 * Fails the build if critical assets cannot be precached.
 * Run ONLY against dist/, never edits frontend/public/sw.js.
 */
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const frontendRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const dist = join(frontendRoot, "dist");
const html = readFileSync(join(dist, "index.html"), "utf8");
const assets = [...new Set([...html.matchAll(/(?:src|href)=["'](\/assets\/[^"']+\.(?:js|css))["']/g)].map((m) => m[1]))].sort();
if (!assets.some((path) => path.endsWith(".js")) || !assets.some((path) => path.endsWith(".css"))) {
  throw new Error("PWA build refused: Vite index.html does not reference both JS and CSS bundles.");
}
const hash = createHash("sha256");
for (const asset of assets) {
  hash.update(asset);
  hash.update(readFileSync(join(dist, asset.slice(1))));
}
const cacheName = "optipack-pwa-" + hash.digest("hex").slice(0, 12);
const swPath = join(dist, "sw.js");
let sw = readFileSync(swPath, "utf8");
if (!sw.includes("__CACHE_NAME__") || !sw.includes("__BUILD_ASSETS__")) {
  throw new Error("PWA service worker injection markers are missing.");
}
sw = sw.replace("__CACHE_NAME__", cacheName).replace("__BUILD_ASSETS__", JSON.stringify(assets));
writeFileSync(swPath, sw);
console.log("PWA build precache:", cacheName, assets.join(", "));
