import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { readFileSync } from "node:fs";
const pointer=JSON.parse(readFileSync("public/data/current/latest.json","utf8"));
const contextPointer=JSON.parse(readFileSync("public/data/context/latest.json","utf8"));
const context=JSON.parse(readFileSync(`public/data/context/${contextPointer.file}`,"utf8"));
const current=JSON.parse(readFileSync(`public/data/current/${pointer.file}`,"utf8"));
const operationsPointer=JSON.parse(readFileSync("public/data/operations/latest.json","utf8"));
const operations=JSON.parse(readFileSync(`public/data/operations/${operationsPointer.file}`,"utf8"));

test("operational intelligence routes, honest evidence, responsive layout and accessibility",async({page},info)=>{
  const errors:string[]=[];page.on("pageerror",e=>errors.push(e.message));
  await page.clock.install({time:new Date(Math.max(Date.parse(current.generated_at),Date.parse(context.generated_at)))});
  await page.goto("./#intelligence");
  for(const [label,route] of [["Matchup Intelligence","intelligence"],["Forecast History","history"],["Postgame Analysis","postgame"],["Model Intelligence","models"]]){
    await page.getByRole("link",{name:label,exact:true}).click();
    await expect(page.getByRole("heading",{name:label,exact:true})).toBeVisible();
    if(route==="intelligence"){
      await expect(page.locator(".domain-card")).toHaveCount(12);
      await expect(page.getByRole("region",{name:"Current matchup model factors"})).toBeVisible();
      await expect(page.getByRole("heading",{name:"Weather, news and remaining gaps"})).toBeVisible();
      await page.locator(".domain-card details summary").first().click();
      await expect(page.locator(".context-team")).toHaveCount(2);
      await expect(page.getByText("Starter not confirmed.",{exact:true})).toHaveCount(2);
      await page.getByText(/Inspect .+ player reports/).first().click();
      await expect(page.getByRole("region",{name:/observed injury reports/}).first()).toBeVisible();
    }else if(route==="history"){
      await expect(page.getByText("Not designated before kickoff")).toBeVisible();
      await expect(page.locator(".forecast-timeline li")).toHaveCount(operations.games[0].forecast_ids.length);
      await page.locator(".forecast-timeline summary").first().click();
    }else if(route==="postgame"){
      await expect(page.getByRole("heading",{name:"No completed forecasted games yet"})).toBeVisible();
      await expect(page.getByText("Not established",{exact:true})).toHaveCount(3);
    }else{
      await expect(page.getByRole("region",{name:"Research model comparison"})).toBeVisible();
      await expect(page.getByText("Research only. Not promoted.",{exact:true})).toBeVisible();
      await page.getByText("Calibration, feature contribution and promotion evidence",{exact:true}).click();
      await expect(page.getByRole("region",{name:"Research calibration"})).toBeVisible();
    }
    await expect(page.getByRole("alert")).toHaveCount(0);
    await expect(page.getByRole("link",{name:"Third-party dependency notices",exact:true})).toHaveAttribute("href",/THIRD_PARTY_NOTICES\.txt$/);
    await expect(page.getByRole("link",{name:"SportsDataverse / NFL Next Gen Stats attribution",exact:true})).toHaveAttribute("href",/CURRENT_DATA_NOTICE\.txt$/);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
    const axe=await new AxeBuilder({page}).withTags(["wcag2a","wcag2aa","wcag21aa"]).analyze();
    expect(axe.violations.map(v=>({id:v.id,nodes:v.nodes.map(n=>({target:n.target,message:n.failureSummary}))}))).toEqual([]);
    await page.evaluate(()=>window.scrollTo(0,0));
    await page.screenshot({path:`${process.env.TEST_ARTIFACT_DIR || "../artifacts/execution"}/${process.env.TEST_BASE_URL?.includes("/nfl-predictor/")?"subpath":"root"}-platform-${route}-${info.project.name}.png`,fullPage:true,animations:"disabled"});
    await page.screenshot({path:`${process.env.TEST_ARTIFACT_DIR || "../artifacts/execution"}/${process.env.TEST_BASE_URL?.includes("/nfl-predictor/")?"subpath":"root"}-viewport-${route}-${info.project.name}.png`,fullPage:false,animations:"disabled"});
    if(route==="intelligence") {await page.locator(".current-context-panel").scrollIntoViewIfNeeded();await page.screenshot({path:`${process.env.TEST_ARTIFACT_DIR || "../artifacts/execution"}/${process.env.TEST_BASE_URL?.includes("/nfl-predictor/")?"subpath":"root"}-context-${info.project.name}.png`,fullPage:false,animations:"disabled"});}
    await page.reload();
    await expect(page.getByRole("heading",{name:label,exact:true})).toBeVisible();
  }
  expect(errors).toEqual([]);
});

test("missing operational evidence preserves research and historical access",async({page})=>{
  await page.route("**/data/operations/latest.json",r=>r.fulfill({status:503,body:"Unavailable"}));
  await page.goto("./#history");
  await expect(page.getByRole("alert")).toContainText("Forecast History unavailable");
  await page.getByRole("link",{name:"Model Intelligence",exact:true}).click();
  await expect(page.getByRole("alert")).toContainText("Forecast operations data is unavailable");
  await expect(page.getByRole("region",{name:"Research model comparison"})).toBeVisible();
  await page.getByRole("link",{name:"2023 Matchups",exact:true}).click();
  await expect(page.getByRole("heading",{name:/Game on/})).toBeVisible();
});

test("expired current probabilities stay hidden while immutable history remains inspectable",async({page})=>{
  await page.clock.install({time:new Date(Date.parse(current.valid_until)+1000)});
  await page.goto("./#current");
  await expect(page.getByText(/Snapshot expired — probabilities hidden/)).toBeVisible();
  await expect(page.locator(".current-probabilities")).toHaveCount(0);
  await page.getByRole("link",{name:"Matchup Intelligence",exact:true}).click();
  await expect(page.getByText(/Current probability unavailable: Snapshot expired/)).toBeVisible();
  await page.getByRole("link",{name:"Forecast History",exact:true}).click();
  await expect(page.getByText("Original record",{exact:true})).toBeVisible();
  await expect(page.locator(".forecast-timeline li").first()).toContainText("win:");
});

test("interview demonstration reproduces synthetic trials and a cited human research proposal",async({page})=>{
  await page.clock.install({time:new Date(operations.generated_at)});
  await page.goto("./#models");
  await page.getByText("Open simulation and research walkthrough",{exact:true}).click();
  await page.getByRole("spinbutton",{name:"Simulation draws"}).fill("100000");
  await page.getByRole("spinbutton",{name:"Simulation seed"}).fill("7");
  await page.getByRole("button",{name:"Run synthetic trials"}).click();
  const result=page.getByRole("region",{name:"Synthetic simulation result"});
  await expect(result).toContainText("100,000 trials");
  const first=await result.textContent();
  await page.getByRole("button",{name:"Run synthetic trials"}).click();
  expect(await result.textContent()).toBe(first);
  await expect(page.getByText(/Synthetic outcomes do not validate model accuracy/)).toBeVisible();
  for(const name of ["Plan research","Inspect saved inputs","Draft hypothesis","Prepare human proposal"])await page.getByRole("button",{name,exact:true}).click();
  await expect(page.getByRole("region",{name:"Research walkthrough saved factors"})).toBeVisible();
  await expect(page.getByText(/Human review proposal:/)).toContainText("2024–2025 holdout remains locked");
  await expect(page.getByRole("link",{name:"Download cited forecast inputs"})).toHaveAttribute("href",/data\/current\/forecast-2026-[a-f0-9]{64}\.json$/);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
  const axe=await new AxeBuilder({page}).withTags(["wcag2a","wcag2aa","wcag21aa"]).analyze();
  expect(axe.violations.map(v=>v.id)).toEqual([]);
  await page.getByRole("link",{name:"Architecture",exact:true}).click();
  await expect(page.getByText("Prepared for final publication approval",{exact:true})).toBeVisible();
  await expect(page.getByText(/Public release is NO-GO until/)).toHaveCount(0);
});
