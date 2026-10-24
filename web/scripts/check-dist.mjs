import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";
import assert from "node:assert/strict";

const web = fileURLToPath(new URL("../", import.meta.url));
for (const path of ["data/demo.json", "THIRD_PARTY_NOTICES.txt"]) {
  assert(readFileSync(resolve(web, "dist", path)).equals(readFileSync(resolve(web, "public", path))), `Dist artifact mismatch: ${path}`);
}
assert.deepEqual(readdirSync(resolve(web, "dist")).sort(), ["THIRD_PARTY_NOTICES.txt", "assets", "data", "index.html"]);
const base = process.env.VITE_BASE_PATH || "/";
assert(base.startsWith("/") && base.endsWith("/"), "Base must be an absolute path ending in /");
const html = readFileSync(resolve(web, "dist/index.html"), "utf8");
for (const [, path] of html.matchAll(/(?:src|href)="([^"]+)"/g)) {
  assert(path.startsWith(base), `Asset escapes base path: ${path}`);
  readFileSync(resolve(web, "dist", path.slice(base.length)));
}
console.log(`Static production artifact verified for ${base}`);
