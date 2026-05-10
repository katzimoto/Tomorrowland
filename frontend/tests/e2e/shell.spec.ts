import { test, expect } from "@playwright/test";

test.describe("App shell", () => {
  test("unauthenticated user is redirected to login", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/login/);
  });

  test("login page is accessible", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByRole("heading", { name: /sign in/i })).toBeVisible();
    await expect(page.getByLabel("Email")).toBeVisible();
    await expect(page.getByLabel("Password")).toBeVisible();
    await expect(page.getByRole("button", { name: /sign in/i })).toBeVisible();
  });

  test("expired session shows banner", async ({ page }) => {
    await page.goto("/login?expired=1");
    await expect(page.getByText(/session expired/i)).toBeVisible();
  });

  test("invalid credentials show inline error", async ({ page }) => {
    await page.route("**/api/auth/login", async (route) => {
      await route.fulfill({ status: 403, json: { detail: "Invalid credentials" } });
    });
    await page.goto("/login");
    await page.getByLabel("Email").fill("user@example.com");
    await page.getByLabel("Password").fill("wrongpassword");
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page.getByText(/something went wrong/i)).toBeVisible();
  });
});
