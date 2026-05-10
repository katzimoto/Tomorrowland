import { test, expect, vi } from "vitest";
import { screen, render } from "@/test/render";
import { NotificationsPage } from "./NotificationsPage";

vi.mock("@/api/notifications", () => ({ listNotifications: vi.fn(() => Promise.resolve([{ id: "n1", subscription_id: "s1", subscription_name: "Risk", subscription_query: "risk", doc_id: "d1", doc_title: "Doc", similarity: 0.8, read: false, created_at: "2026-05-10T00:00:00Z" }])), markRead: vi.fn() }));
vi.mock("@tanstack/react-router", () => ({ useNavigate: () => vi.fn() }));

test("groups unread notifications first", async () => {
  render(<NotificationsPage />);
  expect(await screen.findByText("Unread")).toBeInTheDocument();
  expect(await screen.findByText("Doc")).toBeInTheDocument();
});
