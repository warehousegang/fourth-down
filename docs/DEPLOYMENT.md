# Fourth Down on ThomasHoward.dev

Approved destination: **https://thomashoward.dev/fourth-down/**. This integration is prepared locally only. Pushing, deploying, DNS and production settings changes remain unauthorized.

## Inspected configuration and proposed change

On 2026-10-24, `warehousegang/thomashowarddev` was at `0df446445f199b0e7f1329f5817b97b22cf7b1e8`. Its Pages API reports legacy branch publishing from `main` at `/`, custom domain `thomashoward.dev`, and a successful built-in `pages-build-deployment` run. There is no repository workflow to replace. HTTPS returned 200 with an approved certificate. `CNAME`, the current HTTPS enforcement setting, DNS and Pages source remain unchanged.

The local review checkout is `/Users/thomas/Documents/Codex/2026-10-24/files-pasted-by-the-user-codex/thomashowarddev-integration`, branch `codex/fourth-down-integration`. The original `/Users/thomas/PycharmProjects/thomashowarddev` checkout is untouched.

The website changes comprise the compiled `fourth-down/` directory, the featured cards in `index.html` and `projects/index.html`, the Writing index entry, the outdated About paragraph and related-article link labels, the rewritten technical article at `projects/nfl-predictor/` with a small scoped table stylesheet, an archive banner on the old illustrative lab, and README corrections. Existing article URLs and legacy section anchors are preserved. Shared CSS, JavaScript, images, résumé and domain configuration remain unchanged. The application links back to the article and portfolio, using same-origin URLs under `/fourth-down/` and the public portfolio origin for standalone root builds. The new directory contains no Python, raw training data, Git metadata or credentials. Its `release.json` identifies the source commit, `/fourth-down/` base and every static file checksum. No portfolio deployment workflow change is necessary: the existing branch publisher copies these static files alongside the existing site.

Fourth Down source, ML and tests remain in this separate repository. Vite defaults to `/fourth-down/`; `VITE_BASE_PATH=/` remains available for standalone testing. The SHA-pinned `portfolio-artifact.yml.disabled` replaces the unused standalone Pages template. It refreshes only the current season, retains forecast evidence in its own Git history and produces a seven-day `fourth-down-static` download. It has no Pages deployment job, portfolio token, cross-repository push or active schedule. Building an artifact does not update the public website.

## Local build and import

Use the matching Python environment for ML tests; the importer itself uses only Python's standard library. From this repository, with reviewed changes committed:

```sh
cd '/Users/thomas/Documents/ChatGPT/nfl predictor'
(cd web && npm ci --ignore-scripts && npm test && npm run test:release && npm run build)
python3 scripts/portfolio_artifact.py pack --output artifacts/portfolio/fourth-down-static.tar.gz
python3 scripts/portfolio_artifact.py install \
  --archive artifacts/portfolio/fourth-down-static.tar.gz \
  --sha256 VERIFIED_SHA256_PRINTED_BY_PACK \
  --portfolio '/Users/thomas/Documents/Codex/2026-10-24/files-pasted-by-the-user-codex/thomashowarddev-integration'
```

The installer requires the expected archive SHA256, verifies the file manifest/base path, rejects traversal/symlinks and refuses to discard local edits in an existing installed release. It replaces only `fourth-down/`. Review the resulting Git diff before publication. The source directory must be committed before packaging so the artifact has an unambiguous source revision.

Preview the integrated website with a plain directory server, matching Pages path behavior:

```sh
cd '/Users/thomas/Documents/Codex/2026-10-24/files-pasted-by-the-user-codex/thomashowarddev-integration'
python3 -m http.server 4180 --bind 127.0.0.1
# http://127.0.0.1:4180/ and http://127.0.0.1:4180/fourth-down/#models
```

There is no SPA catch-all rewrite: Fourth Down uses hash routes. `/fourth-down` redirects to the directory's trailing slash; `/fourth-down/#models` survives refresh; unknown portfolio paths remain 404s. Existing root-relative and relative portfolio assets retain their original locations.

## Exact publication steps — only after approval

1. Approve the source and portfolio integration commits. Refresh current forecasts before publication or an interview if the saved snapshot has expired; never relabel old timestamps. In the Fourth Down environment, run `python -m ml.refresh`, then `python scripts/forecast_state.py save`, test and commit the new forecast/evidence files, rebuild, package and import as above. Do not fit/promote models or open 2024–2025.
2. If the planned separate public source repository has not been created, publish it without changing the existing private `nfl-predictor` repository:

   ```sh
   cd '/Users/thomas/Documents/ChatGPT/nfl predictor'
   gh repo create warehousegang/fourth-down --public --source=. --remote=origin
   git push -u origin HEAD:main
   gh repo edit warehousegang/fourth-down --default-branch main
   ```

   Stop on an existing repository/name collision. Do **not** enable Pages on the Fourth Down repository or add a second CNAME. Hosting remains with `thomashowarddev`.
3. In the portfolio review checkout, inspect `git diff 0df446445f199b0e7f1329f5817b97b22cf7b1e8 --stat` including the article, cards, Writing index, archived-lab banner and compiled application. Fetch the latest portfolio `main` and reconcile any intervening edits before proceeding. Once this exact integration is approved, push the feature branch and merge it through a reviewed pull request. The merge to `main` triggers the existing Pages deployment:

   ```sh
   cd '/Users/thomas/Documents/Codex/2026-10-24/files-pasted-by-the-user-codex/thomashowarddev-integration'
   git fetch origin
   # Reconcile/retest if origin/main moved from the inspected baseline.
   git push -u origin codex/fourth-down-integration
   gh pr create --repo warehousegang/thomashowarddev --base main \
     --head codex/fourth-down-integration \
     --title 'Feature Fourth Down under /fourth-down/' \
     --body 'Integrates the verified Fourth Down artifact, updates project positioning and the technical article from saved evidence, and adds bidirectional navigation. Preserves existing routes, shared assets, CNAME and branch-based Pages publishing. ML source and tests remain separate.'
   # After approval of the exact pull request, merge it in GitHub.
   gh run list --repo warehousegang/thomashowarddev --limit 3
   gh run watch DEPLOYMENT_RUN_ID --repo warehousegang/thomashowarddev --exit-status
   ```

4. Verify the live homepage card, `/projects/`, `/about/`, `/blog/`, `/resume/`, `/projects/nfl-predictor/`, article-to-app and app-to-article links, the archived lab, `/fourth-down/` and a refreshed `#models` deep link. Compare `/fourth-down/release.json` with the approved source commit/checksums; inspect current forecast age and model ID. This is the first hosted verification, not an already-completed local test. Do not change DNS or Pages settings.

## Future refreshes and rollback

For optional hosted artifact generation, after approval rename `.github/workflows/portfolio-artifact.yml.disabled` to `portfolio-artifact.yml` in the Fourth Down repository, commit and push. Run:

```sh
gh workflow run portfolio-artifact.yml --repo warehousegang/fourth-down --ref main -f refresh=true
gh run list --repo warehousegang/fourth-down --workflow portfolio-artifact.yml --limit 1
gh run watch BUILD_RUN_ID --repo warehousegang/fourth-down --exit-status
gh run download BUILD_RUN_ID --repo warehousegang/fourth-down \
  --name fourth-down-static --dir artifacts/portfolio/downloaded
```

Verify the checksum against that approved run, import the archive using the same installer, review/commit only `fourth-down/`, and publish through the website's normal merge. The commented daily cron may be enabled only with recurring-run approval; it prepares artifacts and never updates the website automatically. No new cross-repository credentials are required. Manual promotion is intentional for this small portfolio; public forecasts expire visibly until the next artifact is imported.

For a data/application rollback, import the previous approved archive/checksum and commit the resulting `fourth-down/` diff. Alternatively restore the complete `fourth-down/` tree from a known-good portfolio commit. Preserve original probabilities and timestamps. To remove the entire integration, revert the portfolio integration commits in reverse order (the editorial/application update, then `58d5f46b5cfb73db69c75c59eb96aefd5c7f3698`), or revert the single squash commit if publication used squash merge. This restores the original cards and essay and removes the new directory without changing `CNAME`. The pre-integration baseline is `0df446445f199b0e7f1329f5817b97b22cf7b1e8`. Reverting just the editorial update returns to the earlier locally prepared application. Verify the resulting tree against the intended baseline before publication. Review and approve the revert before merging. Git history retains the older artifact; a seven-day Actions upload is not the only rollback copy.

## Cost

**$0 additional recurring hosting cost** using the existing public Pages site and standard public-repository Actions runners. Existing domain registration/renewal is unchanged. There is no server, paid sports feed, LLM subscription or new service. [GitHub Pages availability and limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits) and [Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions) support this setup. The current static application is about 5 MB; seven retained compressed daily artifacts are about 5 MB. No schedule, workflow dispatch, push or deployment was executed during preparation.
