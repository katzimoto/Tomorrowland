import { test, expect, vi } from "vitest";
import { screen, render } from "@/test/render";
import { SubscriptionsPage } from "./SubscriptionsPage";

vi.mock("@/api/subscriptions", () => ({
  listSubscriptions: vi.fn(() => Promise.resolve([{ id: "s1", user_id: "u1", name: "Vendor risk", query: "vendor risk", similarity_threshold: 0.75, enabled: true, unread_count: 2, last_notified: null, created_at: "2026-05-10T00:00:00Z", updated_at: "2026-05-10T00:00:00Z" }])),
  createSubscription: vi.fn(), updateSubscription: vi.fn(), deleteSubscription: vi.fn(),
}));

test("distinguishes saved searches from subscriptions", async () => {
  render(<SubscriptionsPage />);
  expect(await screen.findByText("Saved searches")).toBeInTheDocument();
  expect(await screen.findByText("Active subscriptions")).toBeInTheDocument();
  expect(await screen.findByText("Vendor risk")).toBeInTheDocument();
});
