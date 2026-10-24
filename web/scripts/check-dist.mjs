import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";
import assert from "node:assert/strict";

const web = fileURLToPath(new URL("../", import.meta.url));
const directories = ["current", "operations", "research", "context"];
const versionFiles = directories.flatMap(dir => readdirSync(resolve(web, `public/data/${dir}`)).map(name => `data/${dir}/${name}`));
for (const path of ["data/demo.json", "THIRD_PARTY_NOTICES.txt", "CURRENT_DATA_NOTICE.txt", ...versionFiles]) {
  assert(readFileSync(resolve(web, "dist", path)).equals(readFileSync(resolve(web, "public", path))), `Dist artifact mismatch: ${path}`);
}
assert.deepEqual(readdirSync(resolve(web, "dist")).sort(), ["CURRENT_DATA_NOTICE.txt", "THIRD_PARTY_NOTICES.txt", "assets", "data", "index.html"]);
assert.deepEqual(readdirSync(resolve(web, "dist/data")).sort(), [...directories, "demo.json"].sort());
for (const directory of directories) assert.deepEqual(readdirSync(resolve(web, `dist/data/${directory}`)).sort(), readdirSync(resolve(web, `public/data/${directory}`)).sort());
const logos = JSON.parse(readFileSync(resolve(web, "../docs/TEAM_LOGO_REVIEW.json"), "utf8"));
assert.equal(logos.assets.length, 32, "All teams must have a documented logo");
const builtAssets = readdirSync(resolve(web, "dist/assets"));
for (const asset of logos.assets) {
  const code = asset.team.toLowerCase();
  const files = builtAssets.filter(name => name.startsWith(`${code}-`) && name.endsWith(".png"));
  assert.equal(files.length, 1, `Missing or duplicate bundled logo: ${code}`);
  assert(readFileSync(resolve(web, "dist/assets", files[0])).equals(readFileSync(resolve(web, `src/assets/team-logos/${code}.png`))), `Logo changed during build: ${code}`);
}
const notices = builtAssets.filter(name => /^NOTICE-.*\.txt$/.test(name));
assert.equal(notices.length, 1, "Logo rights notice must ship with the application");
assert(readFileSync(resolve(web, "dist/assets", notices[0])).equals(readFileSync(resolve(web, "src/assets/team-logos/NOTICE.txt"))));
const base = process.env.VITE_BASE_PATH || "/fourth-down/";
assert(base.startsWith("/") && base.endsWith("/"), "Base must be an absolute path ending in /");
const html = readFileSync(resolve(web, "dist/index.html"), "utf8");
for (const [, path] of html.matchAll(/(?:src|href)="([^"]+)"/g)) {
  assert(path.startsWith(base), `Asset escapes base path: ${path}`);
  readFileSync(resolve(web, "dist", path.slice(base.length)));
}
console.log(`Static production artifact verified for ${base}`);
