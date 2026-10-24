import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
import { teams } from "../src/teams";

const demo = JSON.parse(readFileSync("public/data/demo.json", "utf8"));

test("all 32 actual logos load locally through real matchup selections", async ({page, baseURL}) => {
  const external: string[] = [];
  const broken: string[] = [];
  const seen = new Set<string>();
  page.on("request", request => {
    if (new URL(request.url()).origin !== new URL(baseURL!).origin) external.push(request.url());
  });
  page.on("response", response => { if (response.status() >= 400) broken.push(response.url()); });
  await page.goto("./#matchups");
  await page.getByLabel("Select week").selectOption("1");
  for (const game of demo.games.filter((g: {week:number}) => g.week === 1)) {
    await page.locator(".game-list button").filter({hasText:new RegExp(`${game.away}.*${game.home}`)}).click();
    for (const code of [game.away, game.home]) {
      const identity = teams[code];
      const logo = page.getByRole("img", {name:`${identity.city} ${identity.name}`,exact:true});
      await logo.scrollIntoViewIfNeeded();
      await expect(logo).toBeVisible();
      await expect.poll(() => logo.evaluate((node: HTMLImageElement) => node.complete && node.naturalWidth > 0)).toBe(true);
      expect(new URL((await logo.getAttribute("src"))!, page.url()).origin).toBe(new URL(page.url()).origin);
      seen.add(code);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }
  expect([...seen].sort()).toEqual(Object.keys(teams).sort());
  await expect(page.getByText("Fourth Down is independent and is not affiliated with or endorsed by the NFL or its teams.")).toBeVisible();
  const notice = page.getByRole("link", {name:"Team logo sources and rights"});
  const response = await page.request.get(new URL((await notice.getAttribute("href"))!, page.url()).href);
  expect(response.ok()).toBe(true);
  const rights = await response.text();
  expect(rights).toContain("Third-party logo artwork is excluded from the project's MIT software license.");
  expect(rights).toContain("Wikipedia's fair-use determinations do not transfer automatically to Fourth Down.");
  expect(external).toEqual([]);
  expect(broken).toEqual([]);
});

test("a failed logo retains a readable team identifier and the matchup layout", async ({page}) => {
  await page.route(/\/assets\/det-[^/]+\.png$/, route => route.fulfill({status:404,body:"Missing logo"}));
  await page.goto("./#matchups");
  await expect(page.getByRole("heading", {name:/Game on/})).toBeVisible();
  const fallback = page.getByRole("img", {name:"Detroit Lions",exact:true});
  await fallback.scrollIntoViewIfNeeded();
  await expect(fallback).toHaveText("DET");
  await expect(page.locator("img[alt='Detroit Lions']")).toHaveCount(0);
  const before = await page.locator(".team-mark").first().boundingBox();
  await page.getByLabel("Select week").selectOption("1");
  await page.locator(".game-list button").filter({hasText:/BUF.*NYJ/}).click();
  await expect(page.getByRole("img", {name:"Buffalo Bills"})).toBeVisible();
  const after = await page.locator(".team-mark").first().boundingBox();
  expect(after!.height).toBe(before!.height);
  expect(after!.width).toBe(before!.width);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
