import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
test("real artifact, selection, deep links, responsive pages and accessibility", async ({
  page,
}, testInfo) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("./#matchups");
  await expect(page.getByRole("heading", { name: /Game on/ })).toBeVisible();
  await expect(page.locator(".team-identifier")).toHaveText(["DET", "GB"]);
  await expect(page.locator("img")).toHaveCount(0);
  const notices = page.getByRole("link", { name: "Third-party notices" });
  const noticesURL = new URL((await notices.getAttribute("href"))!, page.url());
  const noticeResponse = await page.request.get(noticesURL.toString());
  expect(noticeResponse.ok()).toBe(true);
  expect(await noticeResponse.text()).toContain("lucide-react@0.468.0");
  await page.screenshot({
    path: `../artifacts/corrective-${testInfo.project.name}.png`,
    fullPage: true,
    animations: "disabled",
  });
  await page.getByLabel("Select week").selectOption("1");
  await page.getByRole("button", { name: /DET.*KC/ }).click();
  await expect(page).toHaveURL(/2023_01_DET_KC/);
  await expect(
    page.getByRole("region", { name: "Lions at Chiefs forecast" }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("region", { name: "Lions at Chiefs forecast" }),
  ).toBeVisible();
  for (const label of [
    "Prediction explanation",
    "Model performance",
    "Architecture",
    "2023 Matchups",
  ]) {
    await page.getByRole("link", { name: label, exact: true }).click();
    await expect(page.getByRole("main")).toBeVisible();
    if (label === "Model performance") {
      await expect(page.locator(".holdout-callout")).toContainText("partially exposed");
      await expect(page.locator(".holdout-callout")).toContainText("0.5359");
      await expect(page.locator(".holdout-callout")).toContainText("not recomputed here");
    }
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    const accessibility = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    if (label !== "2023 Matchups") {
      await page.screenshot({
        path: `../artifacts/corrective-${label.toLowerCase().replaceAll(" ", "-")}-${testInfo.project.name}.png`,
        fullPage: true,
        animations: "disabled",
      });
    }
    expect
      .soft(
        accessibility.violations.map((v) => ({
          id: v.id,
          nodes: v.nodes.map((n) => ({
            target: n.target,
            summary: n.failureSummary,
          })),
        })),
        label,
      )
      .toEqual([]);
  }
  expect(errors).toEqual([]);
});
test("failed artifact request shows explicit unavailable state", async ({
  page,
}) => {
  await page.route("**/data/demo.json", (route) =>
    route.fulfill({ status: 503, body: "Unavailable" }),
  );
  await page.goto("./#matchups");
  await expect(page.getByRole("alert")).toContainText("Forecasts unavailable");
  await expect(page.getByText("58.8%")).toHaveCount(0);
});
