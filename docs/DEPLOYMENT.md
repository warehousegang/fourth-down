# Publish Fourth Down

Prepared locally on 2026-10-24. **No deployment or personal-site change is authorized yet.** This is an Applied AI portfolio demonstration using a frozen model and static artifacts. The older RC1 reports remain historical evidence, not an additional approval cycle.

## Cost and publication target

Target **$0/month**: public repository, standard Ubuntu GitHub Actions runners, GitHub Pages, public data, no database or paid LLM. [Standard public runners are free](https://docs.github.com/en/billing/concepts/product-billing/github-actions); [Pages supports public repositories on GitHub Free](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits). The site is about 5 MB, versus Pages' 1 GB limit and 100 GB/month soft bandwidth limit. Deployment uploads expire after one day; the optional daily run has two ten-minute job limits. Do not select larger paid runners.

The connected account is `warehousegang`. Its existing `nfl-predictor` repository is private. Use a separate public `fourth-down` repository; read-only lookup found no accessible repository at that name. Stop on a collision rather than overwrite another repository or change its visibility.

## Exact publication steps — after explicit approval

1. Activate the reviewed template and publish the prepared Git history:

   ```sh
   cd '/Users/thomas/Documents/ChatGPT/nfl predictor'
   mv .github/workflows/pages.yml.disabled .github/workflows/pages.yml
   git add .github/workflows/pages.yml .github/workflows/pages.yml.disabled
   git commit -m 'Enable approved Fourth Down Pages publication'
   gh repo create warehousegang/fourth-down --public --source=. --remote=origin
   git push -u origin HEAD:main
   gh repo edit warehousegang/fourth-down --default-branch main
   ```

   The source license is MIT; data/dependency terms and attribution remain separate. Raw local datasets, environments, audit logs and retired logos are excluded. The small `ops/` bundle deliberately retains current-season original observations and forecast history.

2. In the new repository, choose **Settings → Pages → Build and deployment → Source → GitHub Actions**. Ensure Actions are enabled. No secrets or service accounts are needed. The build job has `contents: write` to retain forecasts; the separate deploy job has Pages/identity permissions. Repository rules must permit this workflow's forecast commit.

3. Run the release with a real current-data refresh:

   ```sh
   gh workflow run pages.yml --repo warehousegang/fourth-down --ref main -f refresh=true
   gh run list --repo warehousegang/fourth-down --workflow pages.yml --limit 1
   # Substitute the run ID printed above:
   gh run watch RUN_ID --repo warehousegang/fourth-down --exit-status
   ```

   The job tests the frozen pipeline, restores original evidence, refreshes the current season, generates forecasts/history/postgame scoring, tests and builds the site, then commits retained state together. A complete site is uploaded only after success. A failed refresh/test/push leaves the previous public deployment intact. No fitting, promotion or protected holdout access occurs.

4. Open **https://warehousegang.github.io/fourth-down/**. Check Upcoming Games, matchup explanations, Forecast History, Model Intelligence's simulation/research demonstration, Postgame Analysis and Architecture. Refresh a deep link such as `#intelligence`, check mobile layout, and verify source timestamps/model ID. Expired/missing probabilities must remain withheld. The first hosted run is the real-environment smoke test; it has not been claimed as already executed.

5. If daily refresh is approved, uncomment only these prepared lines under `on:` in `pages.yml`, commit and push to `main`:

   ```yaml
   schedule:
     - cron: '17 12 * * *'
   ```

   This runs about once daily at 12:17 UTC; GitHub may delay jobs. Manual dispatch is available before an interview. This is not a last-minute injury/news service: context annotations keep independent timestamps and do not influence the model. Remove the schedule to stop recurring execution. No schedule is currently active.

6. **After separate personal-site approval**, add a project card linking to the verified Pages URL: **Fourth Down — Applied AI NFL Forecasting**, with description **Explainable upcoming-game predictions, historical evaluation, forecast tracking and controlled research.** Source link: `https://github.com/warehousegang/fourth-down`. Preview/publish through the personal site's existing process. No personal-site files have been touched.

## Local preview and recovery

```sh
cd web
npm ci --ignore-scripts
npm test
npm run test:release
VITE_BASE_PATH=/fourth-down/ npm run build
VITE_BASE_PATH=/fourth-down/ npm run preview -- --port 4174 --strictPort
# Open http://127.0.0.1:4174/fourth-down/
```

The model uses only current-season win rate, scoring margin, recent margin and rest. Injuries, weather, news and prior-season strength are not predictive inputs. Original forecasts and timestamps stay unchanged; publication refreshes instead of rewriting their age. Prospective performance is unknown until eligible recorded games finish.

`ops/forecast-evidence-<season>.zip` and its checksum receipt retain original observations alongside public JSON in one Git commit. Fresh runners restore verified captures; missing/corrupt required evidence fails closed. The disposable checkout and complete-site deployment form the publication boundary: local pointer writes are not claimed to be a database transaction. New empty seasons are allowed; protected 2024–2025 seasons are rejected. Git retains previous bundles without a paid storage service.

For rollback, restore the last good source, `ops/` pair and public artifact tree from Git in a new commit; run the workflow with `refresh=false`. Preserve original timestamps and model identity. Disable optional scheduling while diagnosing source failures. Commercial operation would move long-lived history into partitioned storage and add stronger availability/monitoring; that is not required to publish this portfolio.
