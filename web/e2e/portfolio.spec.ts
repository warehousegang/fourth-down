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
