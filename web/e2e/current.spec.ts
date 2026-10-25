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
    if(choice.state==="archived")await expect(card).toContainText("Archived pregame prediction");
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
  await page.getByText("Version and source provenance",{exact:true}).click();
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

test("48-hour boundary retains explicitly older estimates, then archives them at kickoff", async ({page}, info)=>{
  await serveArtifact(page,"current",`forecast-${original.season}`,original);
  await serveArtifact(page,"operations","operations",originalOperations);
  await page.clock.install({time:new Date(Date.parse(original.valid_until)-1000)});
  await page.goto("./");
  await expect(page.locator(".current-probabilities")).toHaveCount(originalCount);
  await expect(page.getByText("Older forecast",{exact:true})).toHaveCount(0);
  await page.clock.fastForward(1000);
  await expect(page.getByText("Older forecast",{exact:true})).toHaveCount(originalCount);
  await expect(page.getByText("Older forecasts — not fresh",{exact:true})).toBeVisible();
  const first=original.games[0];
  await expect(page.locator(".current-card").first().locator(".current-probabilities strong")).toHaveText([`${(first.away_probability*100).toFixed(1)}%`,`${(first.home_probability*100).toFixed(1)}%`]);
  await expect(page.getByRole("link",{name:"View prediction data (JSON)",exact:true})).toHaveCount(originalCount);
  const card=page.locator(".current-card").first();
  const notice=card.locator(".current-freshness-notice");
  const summary=notice.locator("summary");
  const primary=card.getByRole("link",{name:"Explore matchup intelligence"});
  const secondary=card.getByRole("link",{name:"View prediction data (JSON)"});
  await expect(notice).not.toHaveAttribute("open","");
  await expect(notice.locator("p")).not.toBeVisible();
  await expect(card.locator(".current-cutoff time").first()).toHaveAttribute("datetime",first.generated_at);
  await expect(card.locator(".current-cutoff time").nth(1)).toHaveAttribute("datetime",first.cutoff);
  await summary.focus();
  await expect(summary).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(notice.locator("p")).toBeVisible();
  await expect(notice).toContainText("Saved pregame estimate, not a live update or guarantee");
  expect((await new AxeBuilder({page}).withTags(["wcag2a","wcag2aa","wcag21aa"]).analyze()).violations).toEqual([]);
  await page.keyboard.press("Space");
  await expect(notice.locator("p")).not.toBeVisible();
  await page.keyboard.press("Tab");
  await expect(primary).toBeFocused();
  expect(await primary.evaluate(el=>getComputedStyle(el).outlineStyle)).toBe("solid");
  await page.keyboard.press("Tab");
  await expect(secondary).toBeFocused();
  const primaryBox=(await primary.boundingBox())!;
  const secondaryBox=(await secondary.boundingBox())!;
  expect(primaryBox.height).toBeGreaterThanOrEqual(44);
  expect(secondaryBox.height).toBeGreaterThanOrEqual(44);
  expect(secondaryBox.y-primaryBox.y-primaryBox.height).toBeGreaterThanOrEqual(4);
  const response=await page.request.get(new URL((await secondary.getAttribute("href"))!,page.url()).toString());
  expect(response.ok()).toBe(true);
  expect(await response.json()).toEqual(original);
  await expect(primary).toHaveAttribute("href",`#intelligence?game=${encodeURIComponent(first.id)}`);
  expect((await new AxeBuilder({page}).withTags(["wcag2a","wcag2aa","wcag21aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:`${process.env.TEST_ARTIFACT_DIR || "../artifacts"}/older-forecasts-${info.project.name}.png`,fullPage:true});
  await card.screenshot({path:`${process.env.TEST_ARTIFACT_DIR || "../artifacts"}/older-card-${info.project.name}.png`});
  await page.keyboard.press("Shift+Tab");
  await expect(primary).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(new RegExp(`#intelligence\\?game=${encodeURIComponent(first.id)}$`));
  await expect(page.getByText("Older forecast — not fresh.",{exact:true})).toBeVisible();
  await expect(page.locator(".intelligence-team-comparison strong")).toHaveText([`${(first.away_probability*100).toFixed(1)}%`,`${(first.home_probability*100).toFixed(1)}%`]);
  await page.goto("./");
  await page.clock.fastForward(Date.parse(first.kickoff)-Date.parse(original.valid_until));
  await expect(page.locator(".current-card").first()).toContainText("Archived pregame prediction");
  await expect(page.locator(".current-card").first().locator(".current-probabilities strong")).toHaveText([`${(first.away_probability*100).toFixed(1)}%`,`${(first.home_probability*100).toFixed(1)}%`]);
  await expect(page.locator(".current-card").first()).toContainText("awaiting verified game status and final result");
});

test("stale-source refresh displays original archived probabilities without minting new ones", async ({page})=>{
  const stale=structuredClone(original);
  stale.as_of=stale.generated_at=new Date(Date.parse(original.valid_until)+60000).toISOString();
  stale.games=stale.games.map((g: typeof original.games[number])=>({...g,generated_at:stale.generated_at,status:"unavailable",reason:"Source is over 48 hours old; refresh before using forecasts",home_probability:null,away_probability:null,features:{},factors:[]}));
  const ops=structuredClone(originalOperations); ops.generated_at=stale.generated_at;
  await serveArtifact(page,"current",`forecast-${stale.season}`,stale);
  await serveArtifact(page,"operations","operations",ops);
  await page.clock.install({time:new Date(stale.generated_at)});
  await page.goto("./");
  await expect(page.locator(".current-status-counts dd")).toHaveText([`${originalCount} of ${originalCount}`,"0",String(originalCount)]);
  for (const [index,g] of original.games.entries()) {
    const card=page.locator(".current-card").nth(index);
    await expect(card.locator(".current-probabilities strong")).toHaveText([`${(g.away_probability*100).toFixed(1)}%`,`${(g.home_probability*100).toFixed(1)}%`]);
    await expect(card.getByRole("link",{name:"View prediction data (JSON)",exact:true})).toHaveAttribute("href",new RegExp(saved.artifact_file+"$"));
  }
  await page.locator(".current-card").first().getByRole("link",{name:"Explore matchup intelligence"}).click();
  await expect(page.getByText("Older forecast — not fresh.",{exact:true})).toBeVisible();
  await expect(page.getByRole("region",{name:"Current matchup model factors"}).locator("tbody tr")).toHaveCount(4);
});

test("freshness counts and expanded global notice stay separate at narrow widths with visible keyboard focus", async ({page}, info)=>{
  await serveArtifact(page,"current",`forecast-${original.season}`,original);
  await serveArtifact(page,"operations","operations",originalOperations);
  await page.clock.install({time:new Date(Date.parse(original.valid_until)+1000)});
  if(info.project.name==="mobile")await page.setViewportSize({width:320,height:850});
  await page.goto("./");
  const counts=page.locator(".current-status-counts");
  await expect(counts.locator("dt")).toHaveText(["Displayable","Fresh","Older"]);
  await expect(counts.locator("dd")).toHaveText([`${originalCount} of ${originalCount}`,"0",String(originalCount)]);
  const groups=await counts.locator(":scope > div").all();
  for(let i=0;i<groups.length;i++)for(let j=i+1;j<groups.length;j++){
    const a=(await groups[i].boundingBox())!, b=(await groups[j].boundingBox())!;
    expect(a.x+a.width<=b.x || b.x+b.width<=a.x || a.y+a.height<=b.y || b.y+b.height<=a.y).toBe(true);
  }
  const notice=page.locator(".current-global-freshness");
  const summary=notice.locator("summary");
  await expect(notice.locator("p")).not.toBeVisible();
  await summary.focus();await page.keyboard.press("Enter");
  await expect(notice.locator("p")).toBeVisible();
  const a=(await summary.boundingBox())!, b=(await notice.locator("p").boundingBox())!;
  expect(b.y-a.y-a.height).toBeGreaterThanOrEqual(11);
  expect(await summary.evaluate(el=>({style:getComputedStyle(el).outlineStyle,width:getComputedStyle(el).outlineWidth,color:getComputedStyle(el).outlineColor}))).toEqual({style:"solid",width:"2px",color:"rgb(235, 214, 161)"});
  await expect(notice).toContainText("A source check is not a new prediction");
  await expect(page.getByText(/No late-breaking injuries, weather or news are included/)).toHaveCount(1);
  expect((await new AxeBuilder({page}).withTags(["wcag2a","wcag2aa","wcag21aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:`${process.env.TEST_ARTIFACT_DIR || "../artifacts"}/freshness-expanded-${info.project.name}.png`,fullPage:false,animations:"disabled"});
  await page.keyboard.press("Space");await expect(notice.locator("p")).not.toBeVisible();
  await expect(summary).toBeFocused();
});

test("missing provenance never exposes probabilities", async ({page})=>{
  await page.clock.install({time:new Date(original.generated_at)});
  await page.route("**/data/operations/latest.json",route=>route.fulfill({status:503,body:"Unavailable"}));
  await page.goto("./");
  await expect(page.getByRole("alert")).toContainText("Forecast provenance unavailable");
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
