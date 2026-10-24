import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { readFileSync } from "node:fs";
const pointer = JSON.parse(readFileSync("public/data/current/latest.json", "utf8"));
const artifact = JSON.parse(readFileSync(`public/data/current/${pointer.file}`, "utf8"));

test("current artifact, inputs, source lineage, history separation and accessibility", async ({page}, info) => {
  const errors: string[] = [];
  const historicalRequests: string[] = [];
  page.on("pageerror", e => errors.push(e.message));
  page.on("request", request => { if(request.url().endsWith("/data/demo.json")) historicalRequests.push(request.url()); });
  await page.clock.install({time:new Date(artifact.generated_at)});
  await page.goto("./");
  await expect(page.getByRole("heading",{name:"Current Week Forecasts"})).toBeVisible();
  await expect(page.locator(".current-card")).toHaveCount(artifact.games.length);
  expect(historicalRequests).toEqual([]);
  await expect(page.locator(".current-card .team-logo")).toHaveCount(artifact.games.length * 2);
  // A real upcoming probability may equal the historical accuracy after rounding.
  // Verify every displayed probability against this artifact instead of banning a number.
  for(const [index,game] of artifact.games.entries()){
    const card=page.locator(".current-card").nth(index);
    const displayable=game.status==="available"&&Date.parse(artifact.generated_at)<Date.parse(artifact.valid_until)
      &&game.kickoff&&Date.parse(artifact.generated_at)<Date.parse(game.kickoff);
    if(displayable)await expect(card.locator(".current-probabilities strong")).toHaveText([
      `${(game.away_probability*100).toFixed(1)}%`,`${(game.home_probability*100).toFixed(1)}%`,
    ]);
    else await expect(card.locator(".current-probabilities")).toHaveCount(0);
  }
  if (artifact.games.some((g: {status:string})=>g.status==="available")) {
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

test("current failure remains separate from historical availability", async ({page})=>{
  await page.route("**/data/current/latest.json", route=>route.fulfill({status:503,body:"Unavailable"}));
  await page.goto("./");
  await expect(page.getByRole("alert")).toContainText("Current forecasts unavailable");
  await expect(page.locator(".current-probabilities")).toHaveCount(0);
  await page.getByRole("link",{name:"2023 Matchups",exact:true}).click();
  await expect(page.getByRole("heading",{name:/Game on/})).toBeVisible();
});
