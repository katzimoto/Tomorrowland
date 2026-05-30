import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { render } from "@/test/render";
import { AdminModelProvidersPage } from "./AdminModelProvidersPage";
import * as adminApiModule from "@/api/admin";

const navigate = vi.fn();
vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => navigate,
  Link: ({ children, to }: { children: React.ReactNode; to: string }) => (
    <a href={to}>{children}</a>
  ),
}));

const mockProviders = [
  {
    id: "p1",
    name: "Local Ollama",
    provider_type: "ollama",
    description: null,
    base_url: "http://localhost:11434",
    credential_set: false,
    locality: "local",
    enabled: true,
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2025-01-01T00:00:00Z",
  },
  {
    id: "p2",
    name: "OpenAI Prod",
    provider_type: "openai",
    description: "Production OpenAI instance",
    base_url: "https://api.openai.com/v1",
    credential_set: true,
    locality: "external",
    enabled: true,
    created_at: "2025-06-01T00:00:00Z",
    updated_at: "2025-06-01T00:00:00Z",
  },
  {
    id: "p3",
    name: "Old Llama",
    provider_type: "llama-cpp",
    description: null,
    base_url: "http://localhost:8080",
    credential_set: false,
    locality: "self_hosted",
    enabled: false,
    created_at: "2025-03-01T00:00:00Z",
    updated_at: "2025-03-01T00:00:00Z",
  },
];

const mockDescriptors = [
  {
    id: "d1",
    provider_id: "p1",
    model_name: "llama3.2",
    display_name: "Llama 3.2",
    description: null,
    capabilities: null,
    context_window: 8192,
    max_output_tokens: null,
    enabled: true,
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2025-01-01T00:00:00Z",
  },
  {
    id: "d2",
    provider_id: "p1",
    model_name: "nomic-embed-text",
    display_name: null,
    description: "Embedding model",
    capabilities: null,
    context_window: null,
    max_output_tokens: null,
    enabled: true,
    created_at: "2025-01-01T00:00:00Z",
    updated_at: "2025-01-01T00:00:00Z",
  },
];

const mockTaskDefaults = [
  {
    task_type: "chat",
    provider_id: "p1",
    model_descriptor_id: "d1",
    parameters: null,
    updated_at: "2025-01-01T00:00:00Z",
  },
];

const adminApi = vi.mocked(adminApiModule.adminApi);

beforeEach(() => {
  vi.clearAllMocks();
  adminApi.listModelProviders = vi.fn().mockResolvedValue(mockProviders);
  adminApi.listTaskDefaults = vi.fn().mockResolvedValue(mockTaskDefaults);
  adminApi.listModelDescriptors = vi.fn().mockResolvedValue(mockDescriptors);
  adminApi.createModelProvider = vi.fn().mockResolvedValue(mockProviders[0]);
  adminApi.updateModelProvider = vi.fn();
  adminApi.deleteModelProvider = vi.fn();
  adminApi.testModelProvider = vi.fn();
  adminApi.discoverModels = vi.fn();
  adminApi.createModelDescriptor = vi.fn().mockResolvedValue(mockDescriptors[0]);
  adminApi.updateModelDescriptor = vi.fn();
  adminApi.deleteModelDescriptor = vi.fn();
  adminApi.setTaskDefault = vi.fn();
  adminApi.deleteTaskDefault = vi.fn();
  adminApi.reloadModelProviders = vi.fn();
});

describe("AdminModelProvidersPage", () => {
  it("renders the heading", async () => {
    render(<AdminModelProvidersPage />);
    expect(await screen.findByText("Model Providers")).toBeInTheDocument();
  });

  it("renders provider rows", async () => {
    render(<AdminModelProvidersPage />);
    const names = await screen.findAllByText("Local Ollama");
    expect(names.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("OpenAI Prod")).toBeInTheDocument();
    expect(screen.getByText("Old Llama")).toBeInTheDocument();
  });

  it("shows provider types as badges", async () => {
    render(<AdminModelProvidersPage />);
    expect(await screen.findByText("ollama")).toBeInTheDocument();
    expect(screen.getByText("openai")).toBeInTheDocument();
    expect(screen.getByText("llama-cpp")).toBeInTheDocument();
  });

  it("shows locality badges", async () => {
    render(<AdminModelProvidersPage />);
    expect(await screen.findByText("local")).toBeInTheDocument();
    expect(screen.getByText("self_hosted")).toBeInTheDocument();
    expect(screen.getByText("external")).toBeInTheDocument();
  });

  it("shows enabled/disabled state", async () => {
    render(<AdminModelProvidersPage />);
    const activeBadges = await screen.findAllByText("Active");
    expect(activeBadges.length).toBe(2);
    expect(screen.getByText("Disabled")).toBeInTheDocument();
  });

  it("shows credential set state", async () => {
    render(<AdminModelProvidersPage />);
    expect(await screen.findByText("Set")).toBeInTheDocument();
    const notSetItems = screen.getAllByText("Not set");
    expect(notSetItems.length).toBe(2);
  });

  it("shows empty state when no providers", async () => {
    adminApi.listModelProviders = vi.fn().mockResolvedValue([]);
    render(<AdminModelProvidersPage />);
    expect(await screen.findByText("No model providers configured")).toBeInTheDocument();
  });

  it("opens create dialog on Add Provider button", async () => {
    render(<AdminModelProvidersPage />);
    const addBtn = await screen.findByText("Add Provider");
    await userEvent.click(addBtn);
    expect(screen.getByText("Add Model Provider")).toBeInTheDocument();
  });

  it("creates a provider via dialog", async () => {
    render(<AdminModelProvidersPage />);
    const addBtn = await screen.findByText("Add Provider");
    await userEvent.click(addBtn);

    const nameInput = screen.getByLabelText("Name");
    await userEvent.type(nameInput, "Test Provider");
    await userEvent.click(screen.getByText("Create Provider"));

    await waitFor(() => {
      expect(adminApi.createModelProvider).toHaveBeenCalledWith(
        expect.objectContaining({ name: "Test Provider" }),
        expect.anything(),
      );
    });
  });

  it("opens edit dialog with pre-filled values", async () => {
    render(<AdminModelProvidersPage />);
    const editBtns = await screen.findAllByText("Edit");
    await userEvent.click(editBtns[0]);

    expect(await screen.findByText(/Edit Provider:/)).toBeInTheDocument();
    expect(screen.getByLabelText("Name")).toHaveValue("Local Ollama");
  });

  it("shows credential_set indicator in edit dialog", async () => {
    render(<AdminModelProvidersPage />);
    const editBtns = await screen.findAllByText("Edit");
    await userEvent.click(editBtns[1]);

    expect(await screen.findByText(/Edit Provider:/)).toBeInTheDocument();
    expect(screen.getByText(/Stored credential is set/)).toBeInTheDocument();
  });

  it("shows test result", async () => {
    adminApi.testModelProvider = vi.fn().mockResolvedValue({
      healthy: true,
      latency_ms: 42.5,
      error: null,
      provider_type: "ollama",
    });
    render(<AdminModelProvidersPage />);
    const testBtns = await screen.findAllByText("Test");
    await userEvent.click(testBtns[0]);

    await waitFor(() => {
      expect(screen.getByText(/Healthy/)).toBeInTheDocument();
    });
  });

  it("shows test error", async () => {
    adminApi.testModelProvider = vi.fn().mockResolvedValue({
      healthy: false,
      latency_ms: null,
      error: "Connection refused",
      provider_type: "ollama",
    });
    render(<AdminModelProvidersPage />);
    const testBtns = await screen.findAllByText("Test");
    await userEvent.click(testBtns[0]);

    await waitFor(() => {
      expect(screen.getByText("Connection refused")).toBeInTheDocument();
    });
  });

  it("shows discover results", async () => {
    adminApi.discoverModels = vi.fn().mockResolvedValue([
      { model_name: "llama3.2" },
      { model_name: "nomic-embed-text" },
    ]);
    render(<AdminModelProvidersPage />);
    const discoverBtns = await screen.findAllByText("Discover");
    await userEvent.click(discoverBtns[0]);

    await waitFor(() => {
      expect(screen.getByText("2 models found")).toBeInTheDocument();
    });
  });

  it("shows discover error", async () => {
    adminApi.discoverModels = vi.fn().mockRejectedValue(new Error("Timeout"));
    render(<AdminModelProvidersPage />);
    const discoverBtns = await screen.findAllByText("Discover");
    await userEvent.click(discoverBtns[0]);

    await waitFor(() => {
      expect(screen.getByText("Timeout")).toBeInTheDocument();
    });
  });

  it("shows delete confirmation dialog", async () => {
    window.confirm = vi.fn(() => true);
    adminApi.deleteModelProvider = vi.fn().mockResolvedValue(undefined);
    render(<AdminModelProvidersPage />);
    const deleteBtns = await screen.findAllByRole("button", { name: "" });
    const trashBtn = deleteBtns.find((btn) => btn.querySelector("svg.lucide-trash-2"));
    if (trashBtn) await userEvent.click(trashBtn);

    await waitFor(() => {
      const deleteHeadings = screen.getAllByText(/Delete Provider/);
      expect(deleteHeadings.length).toBeGreaterThanOrEqual(1);
    });
  });

  it("opens descriptors dialog", async () => {
    render(<AdminModelProvidersPage />);
    const modelBtns = await screen.findAllByText("Models");
    await userEvent.click(modelBtns[0]);

    expect(await screen.findByText(/Models: Local Ollama/)).toBeInTheDocument();
    const descNames = screen.getAllByText("llama3.2");
    expect(descNames.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("nomic-embed-text")).toBeInTheDocument();
  });

  it("adds a descriptor via dialog", async () => {
    render(<AdminModelProvidersPage />);
    const modelBtns = await screen.findAllByText("Models");
    await userEvent.click(modelBtns[0]);

    await screen.findByText(/Models: Local Ollama/);
    const nameInput = screen.getByLabelText("Model Name");
    await userEvent.type(nameInput, "test-model");

    const addBtns = screen.getAllByText("Add Descriptor");
    await userEvent.click(addBtns[addBtns.length - 1]);

    await waitFor(() => {
      expect(adminApi.createModelDescriptor).toHaveBeenCalledWith(
        "p1",
        expect.objectContaining({ model_name: "test-model" }),
      );
    });
  });

  it("shows task defaults section", async () => {
    render(<AdminModelProvidersPage />);
    expect(await screen.findByText("chat")).toBeInTheDocument();
    expect(screen.getByText("Task Defaults")).toBeInTheDocument();
  });

  it("shows empty state for task defaults", async () => {
    adminApi.listTaskDefaults = vi.fn().mockResolvedValue([]);
    render(<AdminModelProvidersPage />);
    expect(await screen.findByText(/No task defaults configured/)).toBeInTheDocument();
  });

  it("opens Add Task Default dialog via button", async () => {
    render(<AdminModelProvidersPage />);
    const addBtn = await screen.findByText("Add Task Default");
    await userEvent.click(addBtn);
    expect(screen.getByText("Add Task Default", { selector: "[role='heading'], h2, h3, [class*='title']" })).toBeInTheDocument();
    expect(screen.getByLabelText("Task Type")).toBeInTheDocument();
  });

  it("opens descriptor delete confirmation dialog", async () => {
    render(<AdminModelProvidersPage />);
    const modelBtns = await screen.findAllByText("Models");
    await userEvent.click(modelBtns[0]);

    await screen.findByText(/Models: Local Ollama/);
    const descRow = screen.getAllByText("llama3.2")[1].closest("tr")!;
    const rowBtns = within(descRow).getAllByRole("button");
    await userEvent.click(rowBtns[rowBtns.length - 1]);

    await waitFor(() => {
      expect(screen.getByText(/Delete Descriptor:/)).toBeInTheDocument();
    });
  });

  it("opens task default delete confirmation dialog", async () => {
    render(<AdminModelProvidersPage />);
    await screen.findByText("chat");
    const chatRow = screen.getByText("chat").closest("tr")!;
    const rowBtns = within(chatRow).getAllByRole("button");
    await userEvent.click(rowBtns[rowBtns.length - 1]);

    await waitFor(() => {
      expect(screen.getByText(/Remove Task Default:/)).toBeInTheDocument();
    });
  });
});
