import { test, expect, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { screen, render } from "@/test/render";
import { SubscriptionForm } from "./SubscriptionForm";

test("submits subscription fields", async () => {
  const user = userEvent.setup();
  const onSubmit = vi.fn();
  render(<SubscriptionForm defaultValues={{ name: "", query: "", similarity_threshold: 0.75, enabled: true }} onSubmit={onSubmit} />);
  await user.type(screen.getByLabelText("Name"), "Risk");
  await user.type(screen.getByLabelText("Query"), "risk");
  await user.click(screen.getByRole("button", { name: "Save subscription" }));
  expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ name: "Risk", query: "risk" }));
});
