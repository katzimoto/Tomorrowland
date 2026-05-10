import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { seedSession } from "./phase08e-fixtures";

test("expertise route uses evidence language and command menu navigates", async ({ page }) => {
  await seedSession(page);
  await page.route("**/api/expertise?query=risk", (route) => route.fulfill({ json: { query: "risk", results: [{ user_id: "u1", display_name: "Ari", topics: ["risk"], evidence_count: 1, evidence: [{ doc_id: "d1", title: "Risk memo", excerpt: "Evidence from a document." }] }] } }));
  await page.goto("/expertise");
  await page.getByLabel("Topic").fill("risk");
  await page.getByRole("button", { name: "Find evidence" }).click();
  await expect(page.getByText("1 evidence item found")).toBeVisible();
  await page.keyboard.press(process.platform === "darwin" ? "Meta+K" : "Control+K");
  await page.getByPlaceholder("Type a destination…").fill("history");
  await expect(page.getByRole("button", { name: "History" })).toBeVisible();
  const results = await new AxeBuilder({ page }).analyze();
  expect(results.violations).toEqual([]);
});
