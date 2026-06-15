import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { render } from "@/test/render";
import { AdminConfigPage } from "./AdminConfigPage";
import * as adminApiModule from "@/api/admin";
import type { SystemConfigEntry } from "@/api/admin";

const navigate = vi.fn();
vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => navigate,
  Link: ({ children, to }: { children: React.ReactNode; to: string }) => (
    <a href={to}>{children}</a>
  ),
}));

const mockConfig: SystemConfigEntry[] = [
  { key: "feature.document_chat", value: true, updated_at: null, is_default: false },
  {
    key: "feature.document_chat_hierarchy_expansion",
    value: false,
    updated_at: null,
    is_default: true,
  },
  { key: "llm.model", value: "qwen3:4b", updated_at: null, is_default: true },
  {
    key: "llm.qa_system_prompt",
    value: "Answer from context only.",
    updated_at: null,
    is_default: true,
  },
  { key: "search.vector_weight", value: 0.7, updated_at: null, is_default: true },
];

const adminApi = vi.mocked(adminApiModule.adminApi);

beforeEach(() => {
  vi.clearAllMocks();
  adminApi.listConfig = vi.fn().mockResolvedValue(mockConfig);
  adminApi.updateConfig = vi
    .fn()
    .mockImplementation((key: string, value: unknown) =>
      Promise.resolve({ key, value, updated_at: "now", is_default: false }),
    );
  adminApi.resetConfig = vi
    .fn()
    .mockResolvedValue({ reset: true, keys: mockConfig.map((c) => c.key) });
});

describe("AdminConfigPage", () => {
  it("renders grouped configuration sections", async () => {
    render(<AdminConfigPage />);
    expect(await screen.findByText("Feature Flags")).toBeInTheDocument();
    expect(screen.getByText("LLM Model & Prompts")).toBeInTheDocument();
    expect(screen.getByText("Search & Retrieval")).toBeInTheDocument();
  });

  it("marks default vs overridden values", async () => {
    render(<AdminConfigPage />);
    await screen.findByText("Feature Flags");
    expect(screen.getAllByText("Default").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Overridden")).toBeInTheDocument();
  });

  it("saves a toggled feature flag", async () => {
    const user = userEvent.setup();
    render(<AdminConfigPage />);
    await screen.findByText("Feature Flags");

    // The hierarchy-expansion flag is default-off; toggle it on.
    const row = screen.getByText("feature.document_chat_hierarchy_expansion").closest("tr")!;
    const checkbox = within(row).getByRole("checkbox");
    await user.click(checkbox);
    await user.click(within(row).getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(adminApi.updateConfig).toHaveBeenCalledWith(
        "feature.document_chat_hierarchy_expansion",
        true,
      ),
    );
  });

  it("resets configuration to defaults", async () => {
    const user = userEvent.setup();
    render(<AdminConfigPage />);
    await screen.findByText("Feature Flags");

    await user.click(screen.getByRole("button", { name: /reset to defaults/i }));
    await user.click(screen.getByRole("button", { name: /^reset all$/i }));

    await waitFor(() => expect(adminApi.resetConfig).toHaveBeenCalled());
  });
});
