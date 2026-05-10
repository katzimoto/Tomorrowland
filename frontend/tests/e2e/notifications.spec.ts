import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { seedSession } from "./phase08e-fixtures";

test("notifications route marks items readable", async ({ page }) => {
  await seedSession(page);
  await page.route("**/api/notifications?unread_only=false", (route) => route.fulfill({ json: [{ id: "n1", subscription_id: "s1", subscription_name: "Risk", subscription_query: "risk", doc_id: "d1", doc_title: "Risk memo", similarity: 0.82, read: false, created_at: "2026-05-10T00:00:00Z" }] }));
  await page.route("**/api/notifications/n1/read", (route) => route.fulfill({ json: { id: "n1", read: true } }));
  await page.goto("/notifications");
  await expect(page.getByText("Unread")).toBeVisible();
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});
