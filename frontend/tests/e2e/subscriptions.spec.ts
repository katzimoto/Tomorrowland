import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { seedSession } from "./phase08e-fixtures";

test("subscriptions route shows saved searches and passes axe", async ({ page }) => {
  await seedSession(page);
  await page.route("**/api/subscriptions", (route) => route.fulfill({ json: [{ id: "s1", user_id: "u1", name: "Vendor risk", query: "vendor risk", similarity_threshold: 0.75, enabled: true, unread_count: 1, last_notified: null, created_at: "2026-05-10T00:00:00Z", updated_at: "2026-05-10T00:00:00Z" }] }));
  await page.goto("/subscriptions");
  await expect(page.getByText("Saved searches")).toBeVisible();
  await expect(page.getByText("Active subscriptions")).toBeVisible();
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});
