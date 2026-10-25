import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { readFileSync } from "node:fs";
import { demonstrationForecasts } from "../src/interview-demo";
import type { Operations } from "../src/operations-contracts";
import { displayGames, displayRecord, selectDisplayForecast } from "../src/forecast-display";
const pointer=JSON.parse(readFileSync("public/data/current/latest.json","utf8"));
const contextPointer=JSON.parse(readFileSync("public/data/context/latest.json","utf8"));
const context=JSON.parse(readFileSync(`public/data/context/${contextPointer.file}`,"utf8"));
const current=JSON.parse(readFileSync(`public/data/current/${pointer.file}`,"utf8"));
const operationsPointer=JSON.parse(readFileSync("public/data/operations/latest.json","utf8"));
const operations=JSON.parse(readFileSync(`public/data/operations/${operationsPointer.file}`,"utf8")) as Operations;

test("operational intelligence routes, honest evidence, responsive layout and accessibility",async({page},info)=>{
  const errors:string[]=[];page.on("pageerror",e=>errors.push(e.message));
  const now=Math.max(Date.parse(current.generated_at),Date.parse(context.generated_at),Date.parse(operations.generated_at));
  const games=displayGames(current,operations,now);
  const game=games[0];
  await page.clock.install({time:new Date(now)});
  await page.goto("./#intelligence");
  for(const [label,route] of [["Matchup Intelligence","intelligence"],["Forecast History","history"],["Postgame Analysis","postgame"],["Model Intelligence","models"]]){
    await page.getByRole("link",{name:label,exact:true}).click();
    await expect(page.getByRole("heading",{name:label,exact:true})).toBeVisible();
    if(route==="intelligence"){
      await expect(page.locator(".domain-card")).toHaveCount(12);
      const saved=game?displayRecord(operations,selectDisplayForecast(current,game,operations,now)):null;
      if((saved??(game&&"factors" in game?game:null))?.factors.length)await expect(page.getByRole("region",{name:"Current matchup model factors"})).toBeVisible();
      else if(game)await expect(page.getByText(/A required observation is unavailable/)).toBeVisible();
      else await expect(page.getByRole("heading",{name:"No upcoming matchup"})).toBeVisible();
      await expect(page.getByRole("heading",{name:"Weather, news and remaining gaps"})).toBeVisible();
      await page.locator(".domain-card details summary").first().click();
      const matching=context.games.find((g:{id:string;home:string;away:string;kickoff:string|null})=>game&&g.id===game.id&&g.home===game.home&&g.away===game.away&&g.kickoff===game.kickoff);
      if(game&&"cutoff" in game&&matching&&now<Date.parse(context.valid_until)&&(!game.kickoff||now<Date.parse(game.kickoff))){
        await expect(page.locator(".context-team")).toHaveCount(2);
        await expect(page.getByText("Starter not confirmed.",{exact:true})).toHaveCount(2);
        for(const side of ["home","away"]){
          const team=matching.teams[side];
          if(team.injuries.status==="observed"){
            await page.getByText(`Inspect ${team.team} player reports`,{exact:true}).click();
            await expect(page.getByRole("region",{name:`${team.team} observed injury reports`})).toBeVisible();
          }
        }
      }else{
        await expect(page.locator(".context-team")).toHaveCount(0);
        if(game&&"cutoff" in game)await expect(page.locator(".current-context-panel [role=status]")).toBeVisible();
      }
    }else if(route==="history"){
      const game=operations.games[0];
      if(game){
        await expect(page.getByText("Not designated before kickoff")).toHaveCount(game.final_forecast_id?0:1);
        await expect(page.locator(".forecast-timeline li")).toHaveCount(game.forecast_ids.length);
        if(game.forecast_ids.length)await page.locator(".forecast-timeline summary").first().click();
      }else await expect(page.getByRole("heading",{name:"No recorded forecasts"})).toBeVisible();
    }else if(route==="postgame"){
      const completed=operations.games.filter(g=>g.result);
      await expect(page.locator(".postgame-card")).toHaveCount(completed.length);
      await expect(page.getByRole("heading",{name:"No completed forecasted games yet"})).toHaveCount(completed.length?0:1);
      const m=operations.metrics.primary;
      await expect(page.getByRole("region",{name:"Final pregame forecast performance"}).locator("strong")).toHaveText([
        String(m.count),m.accuracy===null?"Not established":`${(m.accuracy*100).toFixed(1)}%`,
        m.brier===null?"Not established":m.brier.toFixed(4),m.log_loss===null?"Not established":m.log_loss.toFixed(4),
      ]);
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
    if(route==="intelligence"&&game&&"cutoff" in game) {await page.locator(".current-context-panel").scrollIntoViewIfNeeded();await page.screenshot({path:`${process.env.TEST_ARTIFACT_DIR || "../artifacts/execution"}/${process.env.TEST_BASE_URL?.includes("/nfl-predictor/")?"subpath":"root"}-context-${info.project.name}.png`,fullPage:false,animations:"disabled"});}
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

test("freshness expiry keeps eligible older forecasts and immutable history inspectable",async({page})=>{
  const now=Math.max(Date.parse(current.valid_until),Date.parse(current.generated_at),Date.parse(operations.generated_at))+1000;
  await page.clock.install({time:new Date(now)});
  await page.goto("./#current");
  await expect(page.getByText("Older forecasts — not fresh",{exact:true})).toBeVisible();
  const games=displayGames(current,operations,now);
  const choices=games.map(game=>selectDisplayForecast(current,game,operations,now));
  await expect(page.locator(".current-card summary strong").filter({hasText:/^Older forecast$/})).toHaveCount(choices.filter(c=>c.state==="older").length);
  await expect(page.locator(".current-card").getByText("Archived pregame prediction",{exact:true})).toHaveCount(choices.filter(c=>c.state==="archived").length);
  await page.getByRole("link",{name:"Matchup Intelligence",exact:true}).click();
  if(!games.length)await expect(page.getByRole("heading",{name:"No upcoming matchup"})).toBeVisible();
  else if(choices[0].state==="archived")await expect(page.getByText("Archived pregame prediction",{exact:true})).toBeVisible();
  else if(choices[0].state==="older")await expect(page.getByText("Older forecast — not fresh.",{exact:true})).toBeVisible();
  await page.getByRole("link",{name:"Forecast History",exact:true}).click();
  if(operations.games.length){
    await expect(page.getByText("Original record",{exact:true})).toBeVisible();
    await expect(page.locator(".forecast-timeline li").first()).toContainText("win:");
  }else await expect(page.getByRole("heading",{name:"No recorded forecasts"})).toBeVisible();
});

test("interview demonstration reproduces synthetic trials and a cited human research proposal",async({page})=>{
  await page.clock.install({time:new Date(operations.generated_at)});
  await page.goto("./#models");
  await page.getByText("Open simulation and research walkthrough",{exact:true}).click();
  if(!demonstrationForecasts(operations,Date.parse(operations.generated_at)).length){
    await expect(page.getByText(/No verified saved forecast matches an upcoming scheduled game/)).toBeVisible();
    await expect(page.getByRole("spinbutton",{name:"Simulation draws"})).toHaveCount(0);
    return;
  }
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
  await expect(page.getByRole("link",{name:"Download cited forecast inputs"})).toHaveAttribute("href",new RegExp(`data/current/forecast-${operations.season}-[a-f0-9]{64}\\.json$`));
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
  const axe=await new AxeBuilder({page}).withTags(["wcag2a","wcag2aa","wcag21aa"]).analyze();
  expect(axe.violations.map(v=>v.id)).toEqual([]);
  await page.getByRole("link",{name:"Architecture",exact:true}).click();
  await expect(page.getByText("Prepared for final publication approval",{exact:true})).toBeVisible();
  await expect(page.getByText(/Public release is NO-GO until/)).toHaveCount(0);
});
