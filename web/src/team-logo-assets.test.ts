// @vitest-environment node
import { createHash } from "node:crypto";
import { readFileSync, readdirSync } from "node:fs";
import { expect, it } from "vitest";
import manifest from "../../docs/TEAM_LOGO_REVIEW.json";
import { teams } from "./teams";

it("ships all 32 low-resolution PNGs with matching Wikimedia provenance and hashes", () => {
  expect(manifest.assets.map(a => a.team).sort()).toEqual(Object.keys(teams).sort());
  expect(readdirSync(new URL('./assets/team-logos/', import.meta.url)).sort()).toEqual([
    'NOTICE.txt', ...Object.keys(teams).map(code => `${code.toLowerCase()}.png`),
  ].sort());
  for (const asset of manifest.assets) {
    const body = readFileSync(new URL(`../../${asset.path}`, import.meta.url));
    expect(body.subarray(0, 8).toString('hex')).toBe('89504e470d0a1a0a');
    expect(body.length).toBe(asset.bytes);
    expect(body.readUInt32BE(16)).toBe(asset.width);
    expect(body.readUInt32BE(20)).toBe(asset.height);
    expect(asset.width).toBe(250);
    expect(asset.width * asset.height).toBeLessThanOrEqual(100000);
    expect(createHash('sha256').update(body).digest('hex')).toBe(asset.sha256);
    expect(new URL(asset.source).hostname).toBe('thumb.wikimedia.org');
    expect(['en.wikipedia.org','commons.wikimedia.org']).toContain(new URL(asset.source_page).hostname);
    expect(new URL(asset.source_revision_url).searchParams.get('oldid')).toBe(String(asset.revision_id));
    expect(asset.source_page_sha256).toMatch(/^[a-f0-9]{64}$/);
    expect(asset.mit_licensed).toBe(false);
    expect(asset.owner_permission_obtained).toBe(false);
    expect(asset.source_status.length).toBeGreaterThan(20);
    expect(asset.limited_use_rationale).toContain(asset.name);
    expect(asset.unresolved_concerns.length).toBeGreaterThan(0);
  }
});

it("ships each source, status, credit and uncertainty alongside the MIT exclusion", () => {
  const notice = readFileSync(new URL('./assets/team-logos/NOTICE.txt', import.meta.url), 'utf8');
  for (const asset of manifest.assets) {
    for (const value of [asset.name, asset.source_revision_url, asset.source_status, asset.attribution, asset.sha256, ...asset.unresolved_concerns]) {
      expect(notice).toContain(value);
    }
  }
  expect(notice).toContain("Wikipedia's fair-use determinations do not transfer automatically to Fourth Down.");
  expect(notice).toContain("Third-party logo artwork is excluded from the project's MIT software license.");
  expect(readFileSync(new URL('../../LICENSE', import.meta.url), 'utf8')).toContain('web/src/assets/team-logos/ is excluded');
});
