import { test, expect, vi } from "vitest";
import { screen, render } from "@/test/render";
import { NotificationItem } from "./NotificationItem";

const navigate = vi.fn();
vi.mock("@tanstack/react-router", () => ({ useNavigate: () => navigate }));
vi.mock("@/api/notifications", () => ({ markRead: vi.fn(() => Promise.resolve({ id: "n1", read: true })) }));

test("renders unread notification action", () => {
  render(<NotificationItem notification={{ id: "n1", subscription_id: "s1", subscription_name: "Risk", subscription_query: "risk", doc_id: "d1", doc_title: "Doc", similarity: 0.8, read: false, created_at: "2026-05-10T00:00:00Z" }} />);
  expect(screen.getByText("New")).toBeInTheDocument();
  expect(screen.getByRole("button")).toHaveTextContent("Doc");
});
