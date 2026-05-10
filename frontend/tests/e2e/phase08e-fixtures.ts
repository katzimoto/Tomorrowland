import type { Page } from "@playwright/test";

export async function seedSession(page: Page) {
  await page.addInitScript(() => sessionStorage.setItem("neverland_token", "test-token"));
  await page.route("**/api/auth/me", (route) => route.fulfill({ json: { user_id: "u1", email: "ari@example.com", display_name: "Ari", is_admin: true, groups: [] } }));
  await page.route("**/api/notifications?unread_only=true", (route) => route.fulfill({ json: [{ id: "n1", subscription_id: "s1", subscription_name: "Risk", subscription_query: "risk", doc_id: "d1", doc_title: "Risk memo", similarity: 0.82, read: false, created_at: "2026-05-10T00:00:00Z" }] }));
}
