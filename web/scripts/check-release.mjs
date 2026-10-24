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
assert.deepEqual(readdirSync(resolve(root, "web/public/data")).sort(), ["context", "current", "demo.json", "operations", "research"]);
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
  assert(readFileSync(resolve(root, currentPath, name)).length <= 1_000_000, "Current artifact exceeds client budget");
}
const registry = json("docs/MODEL_REGISTRY.json");
assert.equal(registry.operational_model_id, original.model.id);
assert.equal(registry.promotion_approval, null);
assert.equal(registry.frozen_manifest_sha256, sha("docs/FROZEN_MODEL.json"));
for (const entry of registry.models) assert.equal(sha(entry.artifact), entry.sha256);
const declaration = json("docs/CHALLENGER_DECLARATION.json");
assert.equal(declaration.protocol_sha256, sha("docs/CHALLENGER_PROTOCOL.md"));
for (const [directory, prefix, mode] of [["operations", "operations", "forecast-operations"], ["research", "challenger", "challenger-research"], ["context", "context", "current-context"]]) {
  const path = `web/public/data/${directory}/`;
  const latest = json(path + "latest.json");
  assert.match(latest.sha256, /^[a-f0-9]{64}$/);
  assert.equal(latest.file, `${prefix}-${latest.sha256}.json`);
  assert.equal(sha(path + latest.file), latest.sha256);
  assert.equal(latest.generated_at, json(path + latest.file).generated_at);
  for (const name of readdirSync(resolve(root, path))) {
    if (name === "latest.json") continue;
    assert.equal(name, `${prefix}-${sha(path + name)}.json`);
    assert(readFileSync(resolve(root, path, name)).length <= 5_000_000, "Artifact exceeds client budget");
    const a = json(path + name);
    assert.equal(a.schema_version, 1);
    assert.equal(a.mode, mode);
    if (directory === "operations") {
      assert(a.season >= 2026 && a.schedule.every(g => g.season === a.season));
      assert.equal(a.model_id, original.model.id);
      assert.equal(a.model_freeze_sha256, sha("docs/FROZEN_MODEL.json"));
      assert.match(a.protocol.sha256, /^[a-f0-9]{64}$/);
      assert.equal(sha(`docs/protocols/${a.protocol.sha256}.md`), a.protocol.sha256);
      assert(a.catalog.length <= 10_000);
      for (const receipt of a.catalog) {
        assert.equal(receipt.artifact_file, `forecast-${a.season}-${receipt.artifact_sha256}.json`);
        assert.equal(sha(currentPath + receipt.artifact_file), receipt.artifact_sha256);
      }
    } else if (directory === "research") {
      assert.equal(a.incumbent_model_id, original.model.id);
      assert.deepEqual(a.config, declaration.config);
      assert.deepEqual(a.provenance.declaration, declaration);
      assert.equal(a.provenance.protocol_sha256, declaration.protocol_sha256);
      assert(a.predictions.every(p => p.season >= 2018 && p.season <= 2023));
      assert.equal(a.promotion.eligible, false);
      assert.equal(a.promotion.approval_required, true);
    } else {
      assert(Number.isInteger(a.season) && a.season >= 2026);
      assert.equal(a.affects_probability, false);
      assert(a.games.every(g => g.id.startsWith(`ngs-${a.season}-`) && !Object.hasOwn(g, "home_probability")));
      const expected = {
        injuries: `https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_${a.season}.csv`,
        depth_charts: `https://github.com/nflverse/nflverse-data/releases/download/depth_charts/depth_charts_${a.season}.parquet`,
        stats_team: `https://github.com/nflverse/nflverse-data/releases/download/stats_team/stats_team_week_${a.season}.csv`,
      };
      assert.deepEqual(a.sources.map(s => s.id).sort(), Object.keys(expected).sort());
      for (const source of a.sources) {
        assert.equal(source.url, expected[source.id]);
        assert.match(source.sha256, /^[a-f0-9]{64}$/);
        assert.equal(source.license_url, "https://github.com/nflverse/nflverse-data/blob/main/LICENSE.md");
      }
    }
  }
}
const lock = json("docs/ACTIONS_LOCK.json");
const portfolio = ["portfolio-artifact.yml.disabled", "portfolio-artifact.yml"].filter(name => existsSync(resolve(root, ".github/workflows", name)));
assert.equal(portfolio.length, 1, "Keep exactly one portfolio artifact workflow/template; activation requires owner approval");
for (const workflow of readdirSync(resolve(root, ".github/workflows")).filter(name => /\.yml(?:\.disabled)?$/.test(name))) {
  const content = readFileSync(resolve(root, ".github/workflows", workflow), "utf8");
  for (const match of content.matchAll(/uses:\s*([^\s#]+)/g)) {
    const [action, ref] = match[1].split("@");
    assert.match(ref || "", /^[a-f0-9]{40}$/, `Mutable action: ${match[1]}`);
    assert.equal(ref, lock.actions[action]?.sha, `Unreviewed action: ${match[1]}`);
  }
}
console.log("Frozen candidate, protocols, current/history/research/context artifacts, public assets and Action pins verified");
