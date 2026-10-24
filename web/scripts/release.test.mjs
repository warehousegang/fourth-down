import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, copyFileSync, readFileSync, writeFileSync, rmSync, renameSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const root = fileURLToPath(new URL("../../", import.meta.url));
const json = p => JSON.parse(readFileSync(resolve(root, p), "utf8"));
function fixture(t) {
  const dir = mkdtempSync(resolve(tmpdir(), "fourth-down-packaging-"));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const files = new Set(["docs/RELEASE_ARTIFACTS.json", "docs/FROZEN_MODEL.json", "docs/HOLDOUT_PROTOCOL_FREEZE.json", "docs/ACTIONS_LOCK.json", "web/scripts/check-release.mjs", ".github/workflows/ci.yml", ".github/workflows/pages.yml.disabled"]);
  for (const name of ["docs/RELEASE_ARTIFACTS.json", "docs/FROZEN_MODEL.json", "docs/HOLDOUT_PROTOCOL_FREEZE.json"]) {
    for (const file of Object.keys(json(name).file_sha256)) files.add(file);
  }
  for (const file of files) {
    mkdirSync(dirname(resolve(dir, file)), { recursive: true });
    copyFileSync(resolve(root, file), resolve(dir, file));
  }
  return dir;
}
const run = dir => spawnSync(process.execPath, [resolve(dir, "web/scripts/check-release.mjs")], { encoding: "utf8" });

test("portable source package passes without raw data, Python or model fitting", t => {
  const result = run(fixture(t));
  assert.equal(result.status, 0, result.stderr);
});
test("missing forecast artifact fails closed", t => {
  const dir = fixture(t);
  rmSync(resolve(dir, "web/public/data/demo.json"));
  assert.notEqual(run(dir).status, 0);
});
test("coefficient tampering fails integrity verification", t => {
  const dir = fixture(t), path = resolve(dir, "web/public/data/demo.json");
  const demo = JSON.parse(readFileSync(path, "utf8"));
  demo.model.intercept += 0.01;
  writeFileSync(path, JSON.stringify(demo));
  assert.match(run(dir).stderr, /Frozen artifact changed/);
});
test("mutable action reference fails release check", t => {
  const dir = fixture(t), path = resolve(dir, ".github/workflows/ci.yml");
  writeFileSync(path, readFileSync(path, "utf8").replace(/actions\/checkout@[a-f0-9]{40}/, "actions/checkout@v4"));
  assert.match(run(dir).stderr, /Mutable action/);
});
test("unexpected public image is rejected before distribution", t => {
  const dir = fixture(t);
  writeFileSync(resolve(dir, "web/public/unapproved.png"), "unapproved asset");
  assert.notEqual(run(dir).status, 0);
});
test("future template activation preserves packaging checks without authorizing deployment", t => {
  const dir = fixture(t);
  renameSync(resolve(dir, ".github/workflows/pages.yml.disabled"), resolve(dir, ".github/workflows/pages.yml"));
  const result = run(dir);
  assert.equal(result.status, 0, result.stderr);
});
