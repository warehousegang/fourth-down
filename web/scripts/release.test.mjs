import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, copyFileSync, readFileSync, writeFileSync, rmSync, renameSync, readdirSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const root = fileURLToPath(new URL("../../", import.meta.url));
const json = p => JSON.parse(readFileSync(resolve(root, p), "utf8"));
function fixture(t) {
  const dir = mkdtempSync(resolve(tmpdir(), "fourth-down-packaging-"));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const files = new Set(["docs/RELEASE_ARTIFACTS.json", "docs/FROZEN_MODEL.json", "docs/HOLDOUT_PROTOCOL_FREEZE.json", "docs/ACTIONS_LOCK.json", "web/scripts/check-release.mjs"]);
  files.add("web/public/CURRENT_DATA_NOTICE.txt");
  for (const directory of ["web/public/data/current", "web/public/data/operations", "web/public/data/research", "web/public/data/context", "docs/protocols"]) {
    for (const name of readdirSync(resolve(root, directory))) files.add(`${directory}/${name}`);
  }
  for (const name of ["MODEL_REGISTRY.json", "CHALLENGER_DECLARATION.json", "CHALLENGER_PROTOCOL.md"]) files.add(`docs/${name}`);
  for (const name of readdirSync(resolve(root, ".github/workflows"))) files.add(`.github/workflows/${name}`);
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
  const template = resolve(dir, ".github/workflows/portfolio-artifact.yml.disabled");
  if (existsSync(template)) renameSync(template, resolve(dir, ".github/workflows/portfolio-artifact.yml"));
  const result = run(dir);
  assert.equal(result.status, 0, result.stderr);
});
test("current pointer tampering is rejected", t => {
  const dir = fixture(t), path = resolve(dir, "web/public/data/current/latest.json");
  const pointer = JSON.parse(readFileSync(path, "utf8"));
  pointer.file = "../demo.json";
  writeFileSync(path, JSON.stringify(pointer));
  assert.notEqual(run(dir).status, 0);
});
for (const directory of ["operations", "research", "context"]) {
  test(`${directory} missing or altered version is rejected`, t => {
    const dir = fixture(t), pointer = json(`web/public/data/${directory}/latest.json`);
    const path = resolve(dir, `web/public/data/${directory}/${pointer.file}`);
    writeFileSync(path, readFileSync(path, "utf8") + " ");
    assert.notEqual(run(dir).status, 0);
    rmSync(path);
    assert.notEqual(run(dir).status, 0);
  });
}
test("unapproved operational model registry change fails", t => {
  const dir = fixture(t), path = resolve(dir, "docs/MODEL_REGISTRY.json"), registry = JSON.parse(readFileSync(path,"utf8"));
  registry.operational_model_id = "challenger-v1";
  writeFileSync(path, JSON.stringify(registry));
  assert.notEqual(run(dir).status, 0);
});
