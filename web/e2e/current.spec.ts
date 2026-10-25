import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { readFileSync, readdirSync } from "node:fs";
import { createHash } from "node:crypto";
import { displayGames, displayRecord, selectDisplayForecast } from "../src/forecast-display";
import type { Page } from "@playwright/test";
const pointer = JSON.parse(readFileSync("public/data/current/latest.json", "utf8"));
const artifact = JSON.parse(readFileSync(`public/data/current/${pointer.file}`, "utf8"));
const operationsPointer = JSON.parse(readFileSync("public/data/operations/latest.json", "utf8"));
const operations = JSON.parse(readFileSync(`public/data/operations/${operationsPointer.file}`, "utf8"));

test("current artifact, inputs, source lineage, history separation and accessibility", async ({page}, info) => {
  const errors: string[] = [];
  const historicalRequests: string[] = [];
  page.on("pageerror", e => errors.push(e.message));
  page.on("request", request => { if(request.url().endsWith("/data/demo.json")) historicalRequests.push(request.url()); });
  const now=Math.max(Date.parse(artifact.generated_at),Date.parse(operations.generated_at));
  const games=displayGames(artifact,operations,now);
  await page.clock.install({time:new Date(now)});
  await page.goto("./");
  await expect(page.getByRole("heading",{name:"Current Week Forecasts"})).toBeVisible();
  await expect(page.locator(".current-card")).toHaveCount(games.length);
  expect(historicalRequests).toEqual([]);
  await expect(page.locator(".current-card .team-logo")).toHaveCount(games.length * 2);
  // A real upcoming probability may equal the historical accuracy after rounding.
  // Verify every displayed probability against this artifact instead of banning a number.
  for(const [index,game] of games.entries()){
    const card=page.locator(".current-card").nth(index);
    const choice=selectDisplayForecast(artifact,game,operations,now);
    const saved=displayRecord(operations,choice);
    const displayable=saved!==null;
    if(choice.state==="archived")await expect(card).toContainText("Pregame prediction");
    if(displayable)await expect(card.locator(".current-probabilities strong")).toHaveText([
      `${(saved!.away_probability!*100).toFixed(1)}%`,`${(saved!.home_probability!*100).toFixed(1)}%`,
    ]);
    else await expect(card.locator(".current-probabilities")).toHaveCount(0);
  }
  if (await page.locator(".current-inputs").count()) {
    await page.locator(".current-inputs summary").first().click();
    await expect(page.locator(".current-feature-table").first()).toBeVisible();
    await expect(page.locator(".current-feature-table").first().locator("tbody tr")).toHaveCount(4);
  }
  await page.getByText("Published data and source provenance",{exact:true}).click();
  const link = page.getByRole("link",{name:"Download this forecast JSON"});
  const response = await page.request.get(new URL((await link.getAttribute("href"))!, page.url()).toString());
  expect(response.ok()).toBe(true);
  expect(await response.json()).toEqual(artifact);
  const notice = page.getByRole("link",{name:"Data attribution and license"});
  const license = await page.request.get(new URL((await notice.getAttribute("href"))!, page.url()).toString());
  expect(license.ok()).toBe(true);
  expect(await license.text()).toContain("Copyright (c) 2023 SportsDataverse");
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
  const accessibility = await new AxeBuilder({page}).withTags(["wcag2a","wcag2aa","wcag21aa"]).analyze();
  expect(accessibility.violations.map(v=>({id:v.id,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))}))).toEqual([]);
  await page.evaluate(()=>window.scrollTo(0,0));
  await page.screenshot({path:`${process.env.TEST_ARTIFACT_DIR || "../artifacts"}/current-viewport-${info.project.name}.png`,fullPage:false,scale:"css",animations:"disabled"});
  await page.screenshot({path:`${process.env.TEST_ARTIFACT_DIR || "../artifacts"}/current-forecasts-${info.project.name}.png`,fullPage:true,animations:"disabled"});
  await page.getByRole("link",{name:"2023 Matchups",exact:true}).click();
  await expect(page.getByRole("heading",{name:/Game on/})).toBeVisible();
  await page.getByRole("link",{name:"Current Week Forecasts",exact:true}).click();
  await page.reload();
  await expect(page.getByRole("heading",{name:"Current Week Forecasts"})).toBeVisible();
  expect(errors).toEqual([]);
});

// Exercise real archived inputs through checksum/schema validation and the built UI.
const saved = operations.catalog.filter((f: {eligible:boolean})=>f.eligible).at(-1);
const original = JSON.parse(readFileSync(`public/data/current/${saved.artifact_file}`,"utf8"));
const originalOperations = readdirSync("public/data/operations").filter(f=>f.startsWith("operations-")).map(f=>JSON.parse(readFileSync(`public/data/operations/${f}`,"utf8"))).find(o=>o.generated_at===original.generated_at);
const originalCount = original.games.length;
async function serveArtifact(page: Page, directory: string, prefix: string, data: typeof artifact) {
  const body=JSON.stringify(data);
  const sha256=createHash("sha256").update(body).digest("hex");
  const file=`${prefix}-${sha256}.json`;
  await page.route(`**/data/${directory}/latest.json`,route=>route.fulfill({json:{schema_version:1,file,sha256,season:data.season,generated_at:data.generated_at}}));
  await page.route(`**/data/${directory}/${file}`,route=>route.fulfill({contentType:"application/json",body}));
}

test("source expiry and kickoff preserve the saved prediction and keyboard-accessible details", async ({page}, info)=>{
  await serveArtifact(page,"current",`forecast-${original.season}`,original);
  await serveArtifact(page,"operations","operations",originalOperations);
  await page.clock.install({time:new Date(Date.parse(original.valid_until)-1000)});
  await page.goto("./");
  await expect(page.locator(".current-probabilities")).toHaveCount(originalCount);
  await page.clock.fastForward(1000);
  await expect(page.getByText("Older forecast",{exact:true})).toHaveCount(0);
  await expect(page.locator(".prediction-label")).toHaveText(Array(originalCount).fill("Pregame prediction"));
  const first=original.games[0],card=page.locator(".current-card").first();
  const probabilities=[`${(first.away_probability*100).toFixed(1)}%`,`${(first.home_probability*100).toFixed(1)}%`];
  await expect(card.locator(".current-probabilities strong")).toHaveText(probabilities);
  await expect(card.locator(".current-cutoff time")).toHaveAttribute("datetime",first.generated_at);
  await expect(card).toContainText("Predicted winner");
  const details=card.locator(".prediction-details"),summary=details.locator("summary");
  await expect(details).not.toHaveAttribute("open","");
  await summary.focus();await page.keyboard.press("Enter");
  await expect(details.getByText("Data cutoff",{exact:true})).toBeVisible();
  await expect(details.getByText("Source published",{exact:true})).toBeVisible();
  await expect(details.locator("tbody tr")).toHaveCount(4);
  expect(await summary.evaluate(el=>getComputedStyle(el).outlineStyle)).toBe("solid");
  expect((await new AxeBuilder({page}).withTags(["wcag2a","wcag2aa","wcag21aa"]).analyze()).violations).toEqual([]);
  await card.screenshot({path:methodPath(info.project.name,"prediction-details")});
  await page.keyboard.press("Space");await expect(details).not.toHaveAttribute("open","");
  const primary=card.getByRole("link",{name:"Explore matchup intelligence"});
  const secondary=card.getByRole("link",{name:"View prediction data (JSON)"});
  await primary.focus();await page.keyboard.press("Tab");await expect(secondary).toBeFocused();
  expect((await primary.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  expect((await secondary.boundingBox())!.height).toBeGreaterThanOrEqual(44);
  const response=await page.request.get(new URL((await secondary.getAttribute("href"))!,page.url()).toString());
  expect(await response.json()).toEqual(original);
  await primary.click();
  await expect(page.getByRole("heading",{name:"Matchup Intelligence",exact:true})).toBeVisible();
  await expect(page.getByText("Pregame prediction",{exact:true})).toBeVisible();
  await expect(page.locator(".intelligence-team-comparison strong")).toHaveText(probabilities);
  await page.goto("./");
  await page.clock.fastForward(Date.parse(first.kickoff)-Date.parse(original.valid_until));
  await expect(card).toContainText("Pregame prediction");
  await expect(card.locator(".current-probabilities strong")).toHaveText(probabilities);
  await expect(card).toContainText("Awaiting a verified game update");
});
const methodPath=(project:string,name:string)=>`${process.env.TEST_ARTIFACT_DIR||"../artifacts"}/${name}-${project}.png`;

test("stale-source refresh displays original archived probabilities without minting new ones", async ({page})=>{
  const stale=structuredClone(original);
  stale.as_of=stale.generated_at=new Date(Date.parse(original.valid_until)+60000).toISOString();
  stale.games=stale.games.map((g: typeof original.games[number])=>({...g,generated_at:stale.generated_at,status:"unavailable",reason:"Source is over 48 hours old; refresh before using forecasts",home_probability:null,away_probability:null,features:{},factors:[]}));
  const ops=structuredClone(originalOperations); ops.generated_at=stale.generated_at;
  await serveArtifact(page,"current",`forecast-${stale.season}`,stale);
  await serveArtifact(page,"operations","operations",ops);
  await page.clock.install({time:new Date(stale.generated_at)});
  await page.goto("./");
  await expect(page.locator(".prediction-label")).toHaveText(Array(originalCount).fill("Pregame prediction"));
  for (const [index,g] of original.games.entries()) {
    const card=page.locator(".current-card").nth(index);
    await expect(card.locator(".current-probabilities strong")).toHaveText([`${(g.away_probability*100).toFixed(1)}%`,`${(g.home_probability*100).toFixed(1)}%`]);
    await expect(card.getByRole("link",{name:"View prediction data (JSON)",exact:true})).toHaveAttribute("href",new RegExp(saved.artifact_file+"$"));
  }
  await page.locator(".current-card").first().getByRole("link",{name:"Explore matchup intelligence"}).click();
  await expect(page.getByText("Pregame prediction",{exact:true})).toBeVisible();
  await expect(page.getByRole("region",{name:"Current matchup model factors"}).locator("tbody tr")).toHaveCount(4);
});

test("scoreboard and prediction details remain readable at narrow widths with keyboard focus", async ({page}, info)=>{
  await serveArtifact(page,"current",`forecast-${original.season}`,original);
  await serveArtifact(page,"operations","operations",originalOperations);
  await page.clock.install({time:new Date(Date.parse(original.valid_until)+1000)});
  if(info.project.name==="mobile")await page.setViewportSize({width:320,height:850});
  await page.goto("./");
  const scoreboard=page.getByRole("region",{name:"Prediction Scoreboard"});
  await expect(scoreboard.locator(".scoreboard-primary dd")).toHaveText(["—","0","0 / 0","0",String(originalCount)]);
  const season=scoreboard.getByRole("button",{name:"Season to date"});
  await season.focus();await page.keyboard.press("Enter");await expect(season).toHaveAttribute("aria-pressed","true");
  const details=page.locator(".prediction-details").first(),summary=details.locator("summary");
  await summary.focus();await page.keyboard.press("Enter");
  await expect(details.getByText("Source observed",{exact:true})).toBeVisible();
  expect(await summary.evaluate(el=>getComputedStyle(el).outlineStyle)).toBe("solid");
  expect((await new AxeBuilder({page}).withTags(["wcag2a","wcag2aa","wcag21aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:methodPath(info.project.name,"scoreboard-and-details"),fullPage:true,animations:"disabled"});
  await page.keyboard.press("Space");await expect(details).not.toHaveAttribute("open","");await expect(summary).toBeFocused();
});

test("missing provenance never exposes probabilities", async ({page})=>{
  await page.clock.install({time:new Date(original.generated_at)});
  await page.route("**/data/operations/latest.json",route=>route.fulfill({status:503,body:"Unavailable"}));
  await page.goto("./");
  await expect(page.getByRole("alert").filter({hasText:"Forecast provenance unavailable"})).toBeVisible();
  await expect(page.locator(".current-probabilities")).toHaveCount(0);
});

test("current failure remains separate from historical availability", async ({page})=>{
  await page.route("**/data/current/latest.json", route=>route.fulfill({status:503,body:"Unavailable"}));
  await page.goto("./");
  await expect(page.getByRole("alert")).toContainText("Current forecasts unavailable");
  await expect(page.locator(".current-probabilities")).toHaveCount(0);
  await page.getByRole("link",{name:"2023 Matchups",exact:true}).click();
  await expect(page.getByRole("heading",{name:/Game on/})).toBeVisible();
});
