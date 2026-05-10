import { test, expect, vi } from "vitest";
import { screen, render } from "@/test/render";
import { HistoryPage } from "./HistoryPage";

vi.mock("@/api/history", () => ({ getActivity: vi.fn(() => Promise.resolve([])) }));
vi.mock("@tanstack/react-router", () => ({ useNavigate: () => vi.fn() }));

test("shows history privacy note", async () => {
  render(<HistoryPage />);
  expect(screen.getByText("Activity visible only to you and admins.")).toBeInTheDocument();
  expect(await screen.findByText("No history")).toBeInTheDocument();
});
