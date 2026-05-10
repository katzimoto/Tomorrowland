import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { seedSession } from "./phase08e-fixtures";

test("comments workflow accessibility smoke", async ({ page }) => {
  await seedSession(page);
  await page.route("**/api/subscriptions", (route) => route.fulfill({ json: [] }));
  await page.goto("/subscriptions");
  await expect(page.getByText("Saved searches")).toBeVisible();
  await expect(page.getByRole("button", { name: "Subscribe" }).first()).toBeVisible();
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});
