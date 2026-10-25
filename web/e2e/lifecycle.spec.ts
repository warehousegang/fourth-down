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

test("open dashboard receives a final and corrected result without changing its archived prediction",async({page})=>{
  const final=completedOperations(captured,24,17),live=structuredClone(final);
  const row=live.games[0],record=live.catalog.find(f=>f.id===row.final_forecast_id)!;
  live.generated_at=new Date(Date.parse(final.generated_at)-60_000).toISOString();
  row.status="in_progress";row.result=null;row.evaluations=[];row.analysis=null;
  live.schedule.find(g=>g.id===row.id)!.status="in_progress";
  live.metrics=structuredClone(captured.metrics);
  const current=JSON.parse(readFileSync(`public/data/current/${record.artifact_file}`,"utf8"));
  current.games=[];current.as_of=current.generated_at=live.generated_at;
  await serve(page,"current",`forecast-${current.season}`,current);
  await serve(page,"operations","operations",live);
  await page.clock.install({time:new Date(live.generated_at)});
  await page.goto("./");
  const card=page.getByRole("article",{name:"Steelers at Saints current forecast"});
  const expected=[`${(record.away_probability!*100).toFixed(1)}%`,`${(record.home_probability!*100).toFixed(1)}%`];
  await expect(card).toContainText("In progress");
  await expect(card.locator(".current-probabilities strong")).toHaveText(expected);
  await serve(page,"operations","operations",final);
  await page.clock.fastForward(60_000);
  await expect(card.getByLabel("Verified final: PIT 17 · NO 24")).toBeVisible();
  await expect(page.locator(".scoreboard-primary dd").nth(1)).toHaveText("1");
  await page.route("**/data/operations/latest.json",r=>r.fulfill({status:503,body:"Synthetic outage"}));
  await page.clock.fastForward(60_000);
  await expect(page.getByRole("alert").filter({hasText:"last verified saved evidence"})).toBeVisible();
  await expect(card.getByLabel("Verified final: PIT 17 · NO 24")).toBeVisible();
  const corrected=completedOperations(captured,17,24);
  corrected.generated_at=new Date(Date.parse(final.generated_at)+120_000).toISOString();
  corrected.games[0].result!.observed_at=corrected.generated_at;
  await serve(page,"operations","operations",corrected);
  await page.clock.fastForward(60_000);
  await expect(card.getByLabel("Verified final: PIT 24 · NO 17")).toBeVisible();
  await expect(card).toContainText("Correct prediction");
  await expect(card.locator(".current-probabilities strong")).toHaveText(expected);
  await expect(card.locator(".current-cutoff time")).toHaveAttribute("datetime",record.generated_at);
  await expect(page.locator(".scoreboard-primary dd").nth(1)).toHaveText("1");
});

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
  await expect(card).toContainText("Pregame prediction");
  await expect(card.locator(".current-probabilities strong")).toHaveText([`${(record.away_probability!*100).toFixed(1)}%`,`${(record.home_probability!*100).toFixed(1)}%`]);
  await expect(card.locator(".current-cutoff time").first()).toHaveAttribute("datetime",record.generated_at);
  await expect(card.getByLabel(`Verified final: PIT ${away} · NO ${home}`)).toBeVisible();
  if(home===away) {
    await expect(card).toContainText("Tie excluded from binary scoring");
    await expect(card).not.toContainText("Brier:");
  } else {
    await expect(card).toContainText(`Actual winner: ${home>away?"Saints":"Steelers"}`);
    await expect(card).toContainText(`Brier: ${game.evaluations.find(e=>e.primary)!.brier.toFixed(4)}`);
  }
  expect((await new AxeBuilder({page}).withTags(["wcag2a","wcag2aa","wcag21aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.evaluate(()=>{if(document.activeElement instanceof HTMLElement)document.activeElement.blur()});
  await card.screenshot({path:`${process.env.TEST_ARTIFACT_DIR||"../artifacts"}/archived-final-${home}-${away}-${info.project.name}.png`});
  await card.getByRole("link",{name:"Explore matchup intelligence"}).click();
  await expect(page.getByRole("heading",{name:"Matchup Intelligence",exact:true})).toBeVisible();
  await expect(page.getByText("Pregame prediction",{exact:true})).toBeVisible();
  await expect(page.getByLabel(`Verified final: PIT ${away} · NO ${home}`)).toBeVisible();
  await page.reload();
  await expect(page.getByText("Pregame prediction",{exact:true})).toBeVisible();
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
    for(const f of operations.catalog){f.eligible=false;f.selected_final=false;f.exclusions=[status==="missing"?"Synthetic exclusion: no eligible pregame receipt":"Game is canceled or awaiting confirmed rescheduled kickoff"]}
  }
  await serve(page,"current",`forecast-${current.season}`,current);
  await serve(page,"operations","operations",operations);
  await page.clock.install({time:new Date(operations.generated_at)});
  await page.goto("./");
  const card=page.getByRole("article",{name:"Steelers at Saints current forecast"});
  await expect(card).toBeVisible();
  if(status!=="missing") {
    await expect(card).toContainText("Pregame prediction");
    await expect(card).toContainText(status==="in_progress"?"Awaiting a verified final score":status==="unknown"?"Awaiting a verified game update":status==="postponed"?"Awaiting a confirmed schedule":"This game is not scored");
    await expect(card.locator(".current-probabilities")).toHaveCount(1);
  } else {
    await expect(card).toContainText("Prediction unavailable");
    await expect(card.getByRole("link",{name:"Inspect retained forecast history"})).toBeVisible();
    await expect(card.locator(".current-probabilities")).toHaveCount(0);
  }
  await expect(card).not.toContainText("Verified final:");
  await expect(card).not.toContainText("Brier:");
});


test("scheduled kickoff changes presentation without a backend refresh or a confirmed-live claim",async({page})=>{
  const operations=structuredClone(captured);
  const record=operations.catalog.find((f:{game_id:string;eligible:boolean})=>f.game_id==='ngs-2026-60272'&&f.eligible)!;
  const current=JSON.parse(readFileSync(`public/data/current/${record.artifact_file}`,"utf8"));
  const kickoff=Date.parse(record.kickoff);
  await serve(page,"current",`forecast-${current.season}`,current);
  await serve(page,"operations","operations",operations);
  await page.clock.install({time:new Date(kickoff-1000)});
  await page.goto("./");
  const card=page.getByRole("article",{name:"Steelers at Saints current forecast"});
  await expect(card).toContainText("Upcoming");
  const probabilities=await card.locator(".current-probabilities strong").allTextContents();
  const stamp=await card.locator(".current-cutoff time").getAttribute("datetime");
  await page.route("**/data/**/latest.json",r=>r.fulfill({status:503,body:"No new backend artifact"}));
  await page.clock.fastForward(1500);
  await expect(card).toContainText("Awaiting result update");
  await expect(card).not.toContainText("In progress");
  await expect(card.locator(".current-probabilities strong")).toHaveText(probabilities);
  await expect(card.locator(".current-cutoff time")).toHaveAttribute("datetime",stamp!);
});
