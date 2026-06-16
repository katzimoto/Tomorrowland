import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { render } from "@/test/render";
import { AdminRuntimeConfigPage } from "./AdminRuntimeConfigPage";
import * as adminApiModule from "@/api/admin";
import type { RuntimeConfigSetting } from "@/api/admin";

const navigate = vi.fn();
vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => navigate,
}));

vi.mock("@/api/admin", () => ({
  adminApi: {
    listRuntimeConfig: vi.fn(),
    runtimeConfigAudit: vi.fn(),
    updateRuntimeConfig: vi.fn(),
    resetRuntimeConfig: vi.fn(),
    reloadRuntimeConfig: vi.fn(),
    validateRuntimeConfig: vi.fn(),
  },
}));

const adminApi = vi.mocked(adminApiModule.adminApi);

function setting(overrides: Partial<RuntimeConfigSetting>): RuntimeConfigSetting {
  return {
    key: "feature_rag_qa",
    category: "RAG / chat",
    display_name: "RAG question answering",
    description: "Enable corpus-level RAG question answering.",
    type: "bool",
    is_secret: false,
    is_sensitive: false,
    is_runtime_editable: true,
    requires_restart: false,
    requires_worker_restart: false,
    requires_reindex: false,
    requires_resync: false,
    enum_values: null,
    min_value: null,
    max_value: null,
    source: "default",
    safe_default: true,
    configured_value: true,
    current_effective_value: true,
    override_present: false,
    override_updated_at: null,
    ...overrides,
  };
}

const secretSetting = setting({
  key: "llm_api_key",
  category: "Model providers / LLM runtime",
  display_name: "LLM API key",
  description: "Bearer key for OpenAI-compatible generation providers.",
  type: "secret",
  is_secret: true,
  is_runtime_editable: false,
  current_effective_value: "••••••••",
  configured: true,
  safe_default: null,
  source: "env",
});

beforeEach(() => {
  vi.clearAllMocks();
  adminApi.listRuntimeConfig.mockResolvedValue({
    settings: [setting({}), secretSetting],
    categories: ["RAG / chat", "Model providers / LLM runtime"],
    precedence: "deployment-locked env > database override > env value > application default",
  });
  adminApi.runtimeConfigAudit.mockResolvedValue([]);
  adminApi.updateRuntimeConfig.mockResolvedValue(setting({}));
});

describe("AdminRuntimeConfigPage", () => {
  it("renders the heading and a setting", async () => {
    render(<AdminRuntimeConfigPage />);
    expect(await screen.findByText("Runtime Configuration")).toBeInTheDocument();
    expect(await screen.findByText("RAG question answering")).toBeInTheDocument();
  });

  it("redacts secret values and does not render an editor for them", async () => {
    render(<AdminRuntimeConfigPage />);
    expect(await screen.findByText("LLM API key")).toBeInTheDocument();
    expect(screen.getByText("secret")).toBeInTheDocument();
    // No editor input for the secret setting.
    expect(
      screen.queryByLabelText("LLM API key value"),
    ).not.toBeInTheDocument();
  });

  it("saves an edited setting", async () => {
    render(<AdminRuntimeConfigPage />);
    await screen.findByText("RAG question answering");
    // Toggle the boolean editor to make the row dirty.
    const checkbox = screen.getByRole("checkbox");
    await userEvent.click(checkbox);
    const saveBtn = screen.getByRole("button", { name: "Save" });
    await userEvent.click(saveBtn);
    await waitFor(() =>
      expect(adminApi.updateRuntimeConfig).toHaveBeenCalledWith(
        "feature_rag_qa",
        false,
      ),
    );
  });

  it("filters settings by query", async () => {
    render(<AdminRuntimeConfigPage />);
    await screen.findByText("RAG question answering");
    const search = screen.getByLabelText("Filter settings");
    await userEvent.type(search, "llm");
    await waitFor(() =>
      expect(screen.queryByText("RAG question answering")).not.toBeInTheDocument(),
    );
    expect(screen.getByText("LLM API key")).toBeInTheDocument();
  });
});
