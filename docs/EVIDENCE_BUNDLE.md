# Local observation persistence

`ml.evidence_bundle` exports and imports a bounded, season-specific ZIP of immutable source captures and forecast history. It supports handing local evidence to a clean checkout so future refreshes can prove what was known before kickoff. It performs no network calls, remote artifact discovery, scheduling, deployment, fitting, or model promotion.

The bundle includes only these exact content-addressed paths for an explicitly requested season ≥2026:

- `data/current/<season>/raw-<sha256>.csv`
- `data/current/<season>/snapshot-<sha256>.json`
- `web/public/data/current/forecast-<season>-<sha256>.json`
- `web/public/data/operations/operations-<sha256>.json`, after checking its declared season

It excludes every `latest.json`, model, research artifact, historical dataset, credential, arbitrary file and protected-season directory. Frozen model/source code and checksum-addressed lifecycle protocols remain in Git; restore the appropriate checkout separately. The bundle preserves source and forecast bytes exactly, including original observation and generation timestamps. Import never makes evidence fresher.

## Commands

Run from the repository root with the existing approved Python environment:

```sh
python -m ml.evidence_bundle export --season 2026
```

The JSON receipt reports the bundle path, SHA-256, manifest SHA-256, counts and compressed size. Export defaults to ignored `artifacts/evidence-bundles/`. Store that receipt with the reviewed bundle. Import requires the bundle checksum from that trusted receipt:

```sh
python -m ml.evidence_bundle import /path/to/evidence-2026-<sha256>.zip \
  --season 2026 --sha256 <bundle-sha256> \
  --manifest-sha256 <manifest-sha256>
```

`--root /path/to/clean-checkout` directs restoration to another local checkout/evidence directory. Existing identical versions are accepted; different bytes at any destination cause preflight failure before import writes. New files are fully staged and linked into place without overwriting. An I/O failure may leave a subset of complete immutable versions; rerunning the same import safely resumes. This is not a cross-file transaction or a defense against a malicious process changing the destination filesystem concurrently.

After importing, run the existing refresh command against an explicit captured source or acquire fresh current-season evidence through the authorized refresh path. `python -m ml.refresh --snapshot data/current/2026/snapshot-<sha256>.json` regenerates current and operations pointers using actual execution time. An old source remains stale and may yield unavailable forecasts. Import deliberately leaves any existing pointers unchanged; it never rolls the dashboard back to an old `latest.json`. A source-only capture directory does not become a runnable checkout without the project code and frozen manifests.

## Verification and bounds

The ZIP contains one canonical `manifest.json` with each relative path, byte size and SHA-256. Import verifies the externally supplied archive checksum, optional manifest checksum, exact inventory and every content address before writing. It rejects duplicate ZIP/JSON members, traversal, absolute/Windows paths, links, special/encrypted files, unlisted members, mixed/protected seasons, unsupported compression and differing destination bytes.

Source CSVs must pass the existing season-isolated 272-game normalizer. Captures must reproduce exactly from their raw source bytes. Forecasts must match the frozen model and original input captures; their feature values, explanations and probabilities are independently reproduced without fitting. Operations records must reference included source and forecast versions with matching original per-game inputs and probabilities. Hashes detect corruption; they are not signatures or proof that an untrusted archive was produced by the project. Accept bundles only through a reviewed/trusted handoff, preserving the checksum outside the archive.

Limits are 4,096 evidence files, 5,000,000 bytes per entry, 128 MiB total uncompressed (including manifest), 64 MiB archive size, and a 200:1 maximum per-entry compression ratio. Exceeding a bound stops import/export; it does not silently discard history. Future season-long archives may need a reviewed partition/retention design before increasing those limits.

A GitHub Actions restore/upload integration is still unimplemented and disabled. This local mechanism supplies the verified bytes and commands needed to prepare it. Remote selection of the last successful trusted bundle, retention sufficient to bridge runs, checksum receipt preservation, source outage handling and owner scheduling approval remain operational prerequisites. A fresh runner without restored captures must not invent an earlier observation time.

## Verified locally

The real 2026 export/import CLI roundtrip restored nine immutable files into an empty temporary directory: two observation snapshots, one raw source, three forecast versions and three operations versions. The ZIP was 96,362 bytes; SHA-256 `6666b5ca61f53ca60101b5a1a89a6bc5696cae4247b5ef701544a2acd046ddbd`, manifest SHA-256 `18f7c8ac925b700e1134d18ab12859f9e1dc12ce612a7acd5e2e7b6057493bc0`. No pointer was restored and no original file was modified. These are receipt-specific counts, not permanent limits. Adversarial synthetic tests cover exact-byte repetition, unsafe paths, protected seasons, corrupt/dependent evidence, archive bounds, symlinks, conflicting destination files and pointer preservation.
