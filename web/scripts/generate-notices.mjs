// Include complete license texts for every installed production dependency.
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";
import assert from "node:assert/strict";

const web = fileURLToPath(new URL("../", import.meta.url));
const lock = JSON.parse(readFileSync(resolve(web, "package-lock.json"), "utf8"));
let text = `FOURTH DOWN — THIRD-PARTY NOTICES

Generated from package-lock.json by scripts/generate-notices.mjs.
Includes all production dependencies, including transitive scheduler.
Development tools and Python packages are not bundled in this static site.
Lucide's license below includes the Feather icon attribution.

DATA ATTRIBUTION
nflverse schedules / Lee Sharpe: https://github.com/nflverse/nflverse-data
Original schedule source: https://github.com/nflverse/nfldata
License: CC BY 4.0 — https://creativecommons.org/licenses/by/4.0/
Features and forecasts are derived modifications. Not affiliated with the NFL
or nflverse. Team abbreviations are original text treatments, not official logos.
These notices grant no license to Fourth Down's own source code.
`;
for (const [path, pkg] of Object.entries(lock.packages).sort(([a], [b]) => a.localeCompare(b))) {
  if (!path || pkg.dev) continue;
  const installed = JSON.parse(readFileSync(resolve(web, path, "package.json"), "utf8"));
  assert.equal(installed.version, pkg.version, `Version mismatch: ${path}`);
  const license = ["LICENSE", "LICENSE.md", "LICENSE.txt"].find(name => existsSync(resolve(web, path, name)));
  assert(license, `Missing complete license: ${path}; review before shipping`);
  text += `\n${"=".repeat(72)}\n${installed.name}@${pkg.version} — ${pkg.license}\nSource: https://www.npmjs.com/package/${installed.name}/v/${pkg.version}\n${license}\n\n${readFileSync(resolve(web, path, license), "utf8").trimEnd()}\n`;
}
const output = resolve(web, "public/THIRD_PARTY_NOTICES.txt");
if (process.argv.includes("--check")) {
  assert.equal(readFileSync(output, "utf8"), text, "Notices are stale; regenerate and review");
  console.log("Complete production dependency notices verified");
} else {
  writeFileSync(output, text);
  console.log("Generated public/THIRD_PARTY_NOTICES.txt");
}
