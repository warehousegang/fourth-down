import { test, expect } from "@playwright/test";
import { readdirSync } from "node:fs";

const origin = process.env.PORTFOLIO_URL;
const checkout = process.env.PORTFOLIO_CHECKOUT;
test.skip(!origin || !checkout, "Run against a separately prepared portfolio checkout");
test.use({ reducedMotion: "reduce" });

test("featured project enters the isolated application and hash routes reload", async ({page}, info) => {
  const failures:string[]=[];
  page.on("pageerror", error => failures.push(error.message));
  page.on("response", response => { if (response.status() >= 400) failures.push(response.url()); });
  await page.goto(origin!);
  await expect(page.getByRole("heading", {name:"Thomas Howard",exact:true})).toBeVisible();
  await expect(page.getByRole("link", {name:"Open Fourth Down"})).toHaveAttribute("href","/fourth-down/");
  await page.locator("#nfl-predictor").scrollIntoViewIfNeeded();
  await page.screenshot({path:`${process.env.TEST_ARTIFACT_DIR}/portfolio-card-${info.project.name}.png`});
  await page.getByRole("link", {name:"Open Fourth Down"}).click();
  await expect(page).toHaveURL(/\/fourth-down\/$/);
  await expect(page.getByRole("heading", {name:"Current Week Forecasts",exact:true})).toBeVisible();
  const assets = await page.locator('script[src], link[rel="stylesheet"]').evaluateAll(elements =>
    elements.map(element => element.getAttribute("src") || element.getAttribute("href")));
  expect(assets.length).toBeGreaterThan(0);
  expect(assets.every(path => path?.startsWith("/fourth-down/assets/"))).toBe(true);
  await page.goto(new URL("fourth-down/#models", origin!).href);
  await page.reload();
  await expect(page.getByRole("heading",{name:"Model Intelligence",exact:true})).toBeVisible();
  await page.goto(new URL("projects/",origin!).href);
  await expect(page.getByRole("link",{name:"Open Fourth Down"})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  expect(failures).toEqual([]);
});

test("all original portfolio HTML routes and their assets still load", async ({page}) => {
  const failures:string[]=[];
  page.on("pageerror",error => failures.push(error.message));
  page.on("response",response => {if(response.status()>=400) failures.push(response.url());});
  const pages = readdirSync(checkout!, {recursive:true}).map(String)
    .filter(path=>path.endsWith("index.html") && !path.startsWith("fourth-down/") && !path.startsWith(".git/"));
  expect(pages.length).toBeGreaterThan(15);
  for(const path of pages) {
    const url=new URL(path.replace(/index\.html$/,""),origin!).href;
    const response=await page.goto(url);
    expect(response?.ok(),url).toBe(true);
    await expect(page.locator("h1").first()).toBeVisible();
  }
  const domain=await page.request.get(new URL("CNAME",origin!).href);
  expect((await domain.text()).trim()).toBe("thomashoward.dev");
  // A static directory host must not route nonexistent portfolio pages into React.
  expect((await page.request.get(new URL("not-a-real-portfolio-page/",origin!).href)).status()).toBe(404);
  expect((await page.request.get(new URL("fourth-down/not-a-react-path/",origin!).href)).status()).toBe(404);
  expect(failures).toEqual([]);
});

// Editorial metrics must remain tied to the exact artifact shipped with the article.
test("technical article matches saved validation and links both ways", async ({page}, info) => {
  await page.goto(new URL("projects/nfl-predictor/",origin!).href);
  await expect(page.getByRole("heading",{name:"Fourth Down: from historical games to accountable NFL forecasts"})).toBeVisible();
  const artifact=await (await page.request.get(new URL("fourth-down/data/demo.json",origin!).href)).json();
  for(const model of artifact.evaluation.models) {
    await expect(page.locator(`[data-model-id="${model.id}"] td`)).toHaveText([
      `${(model.accuracy*100).toFixed(2)}%`, model.brier.toFixed(6), model.log_loss.toFixed(6),
    ]);
  }
  const delta=artifact.evaluation.brier_difference;
  const signed=(n:number)=>n.toFixed(6).replace("-","−");
  await expect(page.locator("article")).toContainText(`[${signed(delta.low)}, ${signed(delta.high)}]`);
  await expect(page.locator("article")).toContainText(signed(delta.mean));
  for(const anchor of ["data","baseline","leakage","model","evaluation","agent","related-ml"]) {
    await page.locator(`.essay-nav a[href="#${anchor}"]`).click();
    await expect(page.locator(`#${anchor}`)).toBeInViewport();
  }
  await page.goto(new URL("projects/nfl-predictor/",origin!).href);
  await page.screenshot({path:`${process.env.TEST_ARTIFACT_DIR}/technical-article-${info.project.name}.png`});
  await page.locator("#evaluation").scrollIntoViewIfNeeded();
  await page.screenshot({path:`${process.env.TEST_ARTIFACT_DIR}/article-evaluation-${info.project.name}.png`});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.getByRole("link",{name:"Open Fourth Down",exact:true}).click();
  await expect(page.getByRole("heading",{name:"Current Week Forecasts",exact:true})).toBeVisible();
  await page.getByRole("link",{name:"Technical article",exact:true}).click();
  await expect(page).toHaveURL(new URL("projects/nfl-predictor/",origin!).href);
  await page.getByRole("link",{name:"archived Forecast Lab prototype"}).click();
  await expect(page.getByRole("complementary",{name:"Archived prototype"})).toContainText("hand-authored 62% / 38%");
  await page.getByRole("link",{name:"Open Fourth Down",exact:true}).click();
  await page.getByRole("link",{name:"Thomas Howard",exact:true}).click();
  await expect(page).toHaveURL(origin!+"/");
});

test("portfolio entry points and technical article pass accessibility and layout checks", async ({page}) => {
  const {default:AxeBuilder}=await import("@axe-core/playwright");
  for(const path of ["","about/","projects/","blog/","projects/nfl-predictor/","projects/nfl-predictor/lab/"]) {
    await page.goto(new URL(path,origin!).href);
    if(path==="projects/nfl-predictor/") {
      await page.keyboard.press("Tab");
      await expect(page.getByRole("link",{name:"Skip to content"})).toBeFocused();
      await page.keyboard.press("Enter");
      await expect(page.locator("#main")).toBeFocused();
    }
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),path).toBe(true);
    const scan=await new AxeBuilder({page}).withTags(["wcag2a","wcag2aa","wcag21aa"]).analyze();
    expect(scan.violations.map(v=>({id:v.id,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))})),path).toEqual([]);
  }
});
