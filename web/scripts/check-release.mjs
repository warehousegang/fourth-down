import { readFileSync, readdirSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";
import { createHash } from "node:crypto";
import assert from "node:assert/strict";

const root = fileURLToPath(new URL("../../", import.meta.url));
const json = path => JSON.parse(readFileSync(resolve(root, path), "utf8"));
const sha = path => createHash("sha256").update(readFileSync(resolve(root, path))).digest("hex");
const release = json("docs/RELEASE_ARTIFACTS.json");
const original = json("docs/FROZEN_MODEL.json");
const protocol = json("docs/HOLDOUT_PROTOCOL_FREEZE.json");
for (const manifest of [release, original, protocol]) {
  for (const [path, digest] of Object.entries(manifest.file_sha256)) {
    assert.equal(sha(path), digest, `Frozen artifact changed or missing: ${path}`);
  }
}
assert.deepEqual(protocol.original_frozen_files, original.file_sha256);
const demo = json("web/public/data/demo.json");
assert.deepEqual(demo.model, original.model);
assert.equal(demo.mode, "historical-replay");
assert.equal(demo.games.length, 272);
assert(demo.games.every(g => g.season === 2023));
assert.equal(demo.evaluation.holdout_status, "locked");
assert.equal(protocol.execution_authorized, false);
assert.equal(json("docs/HOLDOUT_EXPOSURE.json").status, "partially-exposed");
assert.deepEqual(readdirSync(resolve(root, "web/public")).sort(), ["CURRENT_DATA_NOTICE.txt", "THIRD_PARTY_NOTICES.txt", "data"]);
assert.deepEqual(readdirSync(resolve(root, "web/public/data")).sort(), ["current", "demo.json"]);
const currentPath = "web/public/data/current/";
const pointer = json(currentPath + "latest.json");
assert.match(pointer.sha256, /^[a-f0-9]{64}$/);
assert(Number.isInteger(pointer.season) && pointer.season >= 2026);
assert.equal(pointer.file, `forecast-${pointer.season}-${pointer.sha256}.json`);
assert.equal(sha(currentPath + pointer.file), pointer.sha256);
for (const name of readdirSync(resolve(root, currentPath))) {
  if (name === "latest.json") continue;
  assert.match(name, /^forecast-20\d{2}-[a-f0-9]{64}\.json$/);
  const artifact = json(currentPath + name);
  assert(artifact.season >= 2026 && artifact.mode === "current-forecast");
  assert.equal(name, `forecast-${artifact.season}-${sha(currentPath + name)}.json`);
  assert.deepEqual(artifact.model, original.model);
  assert(artifact.games.every(g => g.season === artifact.season));
}
const lock = json("docs/ACTIONS_LOCK.json");
const pages = ["pages.yml.disabled", "pages.yml"].filter(name => existsSync(resolve(root, ".github/workflows", name)));
assert.equal(pages.length, 1, "Keep exactly one Pages template/workflow; activation requires separate owner approval");
for (const workflow of readdirSync(resolve(root, ".github/workflows")).filter(name => /\.yml(?:\.disabled)?$/.test(name))) {
  const content = readFileSync(resolve(root, ".github/workflows", workflow), "utf8");
  for (const match of content.matchAll(/uses:\s*([^\s#]+)/g)) {
    const [action, ref] = match[1].split("@");
    assert.match(ref || "", /^[a-f0-9]{40}$/, `Mutable action: ${match[1]}`);
    assert.equal(ref, lock.actions[action]?.sha, `Unreviewed action: ${match[1]}`);
  }
}
console.log("Frozen candidate, protocol, 2023 artifact, public assets and Action pins verified");
