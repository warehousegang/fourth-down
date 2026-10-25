import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { completedOperations } from "../test-support/lifecycle";
const captured=JSON.parse(readFileSync("public/data/operations/operations-acb075e2b1bbe89e74a4bf93810f2d19e17a3540bfc8f0d0ca4368c799623217.json","utf8"));

async function serve(page:Page, directory:string, prefix:string, data:unknown) {
  const body=JSON.stringify(data), sha256=createHash("sha256").update(body).digest("hex"), file=`${prefix}-${sha256}.json`;
  const value=data as {season:number;generated_at:string};
  await page.route(`**/data/${directory}/latest.json`,r=>r.fulfill({json:{schema_version:1,file,sha256,season:value.season,generated_at:value.generated_at}}));
  await page.route(`**/data/${directory}/${file}`,r=>r.fulfill({contentType:"application/json",body}));
}

// Synthetic results only. No test outcome is written to public artifacts.
for (const [home,away] of [[24,17],[17,24],[24,24]]) test(`archived card survives refresh and verified final ${home}-${away}`,async({page},info)=>{
  const operations=completedOperations(captured,home,away);
  const game=operations.games[0], record=operations.catalog.find(f=>f.id===game.final_forecast_id)!;
  const current=JSON.parse(readFileSync(`public/data/current/${record.artifact_file}`,"utf8"));
  current.games=[]; current.week=8; current.as_of=current.generated_at=operations.generated_at;
  // Results naturally change the upstream source file; this must not erase a pregame receipt.
  operations.source.raw_sha256="b".repeat(64);
  operations.source.retrieved_at=operations.generated_at;
  await serve(page,"current",`forecast-${current.season}`,current);
  await serve(page,"operations","operations",operations);
  await page.clock.install({time:new Date(operations.generated_at)});
  await page.goto("./");
  const card=page.getByRole("article",{name:"Steelers at Saints current forecast"});
  await expect(card).toContainText("Archived pregame prediction");
  await expect(card.locator(".current-probabilities strong")).toHaveText([`${(record.away_probability!*100).toFixed(1)}%`,`${(record.home_probability!*100).toFixed(1)}%`]);
  await expect(card.locator(".current-cutoff time").first()).toHaveAttribute("datetime",record.generated_at);
  await expect(card).toContainText(`Verified final: PIT ${away} · NO ${home}`);
  if(home===away) {
    await expect(card).toContainText("Tie excluded from binary scoring");
    await expect(card).not.toContainText("Brier:");
  } else {
    await expect(card).toContainText(`Actual winner: ${home>away?"Saints":"Steelers"}`);
    await expect(card).toContainText(`Brier: ${game.evaluations.find(e=>e.primary)!.brier.toFixed(4)}`);
  }
  expect((await new AxeBuilder({page}).withTags(["wcag2a","wcag2aa","wcag21aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await card.screenshot({path:`${process.env.TEST_ARTIFACT_DIR||"../artifacts"}/archived-final-${home}-${away}-${info.project.name}.png`});
  await card.getByRole("link",{name:"Explore matchup intelligence"}).click();
  await expect(page.getByText("Archived pregame prediction",{exact:true})).toBeVisible();
  await expect(page.locator(".current-outcome")).toContainText(`Verified final: PIT ${away} · NO ${home}`);
  await page.reload();
  await expect(page.getByText("Archived pregame prediction",{exact:true})).toBeVisible();
});


for (const status of ["in_progress","unknown","postponed","canceled","missing"] as const) test(`refreshed card handles ${status} without inventing a score`,async({page})=>{
  const operations=completedOperations(captured);
  const game=operations.games[0], record=operations.catalog.find(f=>f.id===game.final_forecast_id)!;
  const current=JSON.parse(readFileSync(`public/data/current/${record.artifact_file}`,"utf8"));
  current.games=[]; current.as_of=current.generated_at=operations.generated_at;
  const state=status==="missing"?"unknown":status;
  game.status=state; game.result=null; game.evaluations=[]; game.analysis=null;
  operations.schedule.find(g=>g.id===game.id)!.status=state;
  operations.metrics=structuredClone(captured.metrics);
  if(["postponed","canceled","missing"].includes(status)) {
    game.final_forecast_id=null;
    for(const f of operations.catalog){f.eligible=false;f.selected_final=false;f.exclusions=["Synthetic exclusion: no eligible pregame receipt"]}
  }
  await serve(page,"current",`forecast-${current.season}`,current);
  await serve(page,"operations","operations",operations);
  await page.clock.install({time:new Date(operations.generated_at)});
  await page.goto("./");
  const card=page.getByRole("article",{name:"Steelers at Saints current forecast"});
  await expect(card).toBeVisible();
  if(status==="in_progress"||status==="unknown") {
    await expect(card).toContainText("Archived pregame prediction");
    await expect(card).toContainText(status==="in_progress"?"In progress · awaiting verified final result":"awaiting verified game status and final result");
    await expect(card.locator(".current-probabilities")).toHaveCount(1);
  } else {
    await expect(card).toContainText("Prediction unavailable");
    await expect(card.getByRole("link",{name:"Inspect retained forecast history"})).toBeVisible();
    await expect(card.locator(".current-probabilities")).toHaveCount(0);
  }
  await expect(card).not.toContainText("Verified final:");
  await expect(card).not.toContainText("Brier:");
});
