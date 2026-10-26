import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { readFileSync } from "node:fs";
import type { Operations } from "../src/operations-contracts";

const pointer=JSON.parse(readFileSync("public/data/operations/latest.json","utf8"));
const operations:Operations=JSON.parse(readFileSync(`public/data/operations/${pointer.file}`,"utf8"));

test("weekly banner agrees with retained results and exhaustive enumeration",async({page},info)=>{
  const errors:string[]=[];
  page.on("pageerror",e=>errors.push(e.message));
  page.on("response",r=>{if(r.status()>=400)errors.push(r.url())});
  await page.goto("./");
  const banner=page.locator(".weekly-intelligence");
  await expect(banner).toBeVisible();
  const week=Number((await banner.locator(".eyebrow").innerText()).match(/WEEK (\d+)/)![1]);
  const rows=operations.games.filter(g=>g.week===week&&g.status==="completed"&&g.result&&!g.result.tie)
    .flatMap(g=>{
      const f=operations.catalog.find(f=>f.id===g.final_forecast_id&&f.eligible&&f.selected_final);
      if(!f||!g.evaluations.some(e=>e.primary&&e.forecast_id===f.id))return [];
      const p=f.home_probability!, won=g.result!.home_score>g.result!.away_score;
      return [{q:Math.max(p,1-p),correct:(p>=.5)===won,p:won?p:1-p}];
    });
  if(rows.length){
    expect(rows.length).toBeLessThanOrEqual(16);
    const observed=rows.filter(r=>r.correct).length, expected=rows.reduce((s,r)=>s+r.q,0);
    // Independent enumeration, not the application's convolution helper.
    const mass=Array(rows.length+1).fill(0);
    for(let mask=0;mask<2**rows.length;mask++){
      let count=0,probability=1;
      rows.forEach((r,i)=>{const won=!!(mask&(1<<i));count+=Number(won);probability*=won?r.q:1-r.q});
      mass[count]+=probability;
    }
    const tail=mass.slice(0,observed+1).reduce((a,b)=>a+b,0);
    await expect(banner.locator(".weekly-numbers dd")).toHaveText([
      `${observed} / ${rows.length}`,expected.toFixed(2),tail>0&&tail<.001?"<0.1%":`${(tail*100).toFixed(1)}%`,
    ]);
    await expect(page.locator(".scoreboard-primary dd").nth(1)).toHaveText(String(rows.length));
    await expect(page.locator(".scoreboard-primary dd").nth(2)).toHaveText(`${observed} / ${rows.length}`);
  }else await expect(banner).toContainText("Awaiting verified outcomes");
  const summary=banner.locator(".weekly-details > summary");
  await summary.focus(); await page.keyboard.press("Enter");
  await expect(banner.getByRole("heading",{name:"Sample & calculation"})).toBeVisible();
  if(rows.length){
    const loss=rows.reduce((s,r)=>s-Math.log(Math.max(1e-15,r.p)),0)/rows.length;
    await expect(banner.locator(".weekly-surprise strong")).toHaveText(loss.toFixed(4));
    await banner.getByText("Exact distribution values",{exact:true}).click();
    await expect(banner.getByRole("table")).toBeVisible();
    await expect(banner.locator("tbody tr")).toHaveCount(rows.length+1);
    await banner.getByText("Exact distribution values",{exact:true}).click();
  }
  expect((await new AxeBuilder({page}).withTags(["wcag2a","wcag2aa","wcag21aa"]).analyze()).violations).toEqual([]);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.evaluate(()=>{if(document.activeElement instanceof HTMLElement)document.activeElement.blur()});
  await banner.screenshot({path:`${process.env.TEST_ARTIFACT_DIR||"../artifacts"}/weekly-details-${info.project.name}.png`});
  await summary.focus(); await page.keyboard.press("Space");
  await expect(banner.getByRole("heading",{name:"Sample & calculation"})).not.toBeVisible();
  await page.evaluate(()=>{if(document.activeElement instanceof HTMLElement)document.activeElement.blur()});
  await banner.screenshot({path:`${process.env.TEST_ARTIFACT_DIR||"../artifacts"}/weekly-banner-${info.project.name}.png`});
  if(info.project.name==="mobile"){
    await page.setViewportSize({width:320,height:720});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await expect(summary).toBeVisible();
  }
  expect(errors).toEqual([]);
});
