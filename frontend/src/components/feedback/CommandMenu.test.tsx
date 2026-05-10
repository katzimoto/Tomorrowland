import { test, expect, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { screen, render } from "@/test/render";
import { CommandMenu } from "./CommandMenu";

const navigate = vi.fn();
vi.mock("@tanstack/react-router", () => ({ useNavigate: () => navigate }));

test("opens with ctrl+k and filters destinations", async () => {
  const user = userEvent.setup();
  render(<CommandMenu />);
  await user.keyboard("{Control>}k{/Control}");
  expect(screen.getByRole("dialog", { name: "Command menu" })).toBeInTheDocument();
  await user.type(screen.getByPlaceholderText("Type a destination…"), "expert");
  expect(screen.getByRole("button", { name: "Expertise map" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Search" })).not.toBeInTheDocument();
});
