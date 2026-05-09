import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: "html",
  use: {
    baseURL: "http://localhost:5173",
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "320x720",
      use: { ...devices["iPhone SE"], viewport: { width: 320, height: 720 } },
    },
    {
      name: "768x1024",
      use: { viewport: { width: 768, height: 1024 } },
    },
    {
      name: "1024x768",
      use: { viewport: { width: 1024, height: 768 } },
    },
    {
      name: "1440x900",
      use: { viewport: { width: 1440, height: 900 } },
    },
  ],
  webServer: {
    command: "npm run dev",
    url: "http://localhost:5173",
    reuseExistingServer: !process.env.CI,
  },
});
