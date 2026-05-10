import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { seedSession } from "./phase08e-fixtures";

test("annotations private and shared labels are represented in collaboration UI", async ({ page }) => {
  await seedSession(page);
  await page.route("**/api/expertise?query=privacy", (route) => route.fulfill({ json: { query: "privacy", results: [{ user_id: "u1", display_name: "Ari", topics: ["Private note", "Shared with readers"], evidence_count: 2, evidence: [{ doc_id: "d1", title: "Private note", excerpt: "Private evidence." }, { doc_id: "d2", title: "Shared with readers", excerpt: "Shared evidence." }] }] } }));
  await page.goto("/expertise");
  await page.getByLabel("Topic").fill("privacy");
  await page.getByRole("button", { name: "Find evidence" }).click();
  await expect(page.getByText("Private note").first()).toBeVisible();
  await expect(page.getByText("Shared with readers").first()).toBeVisible();
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});
