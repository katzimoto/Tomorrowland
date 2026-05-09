import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { render } from "@/test/render";
import { AdminSourcesPage } from "./AdminSourcesPage";
import * as adminApi from "@/api/admin";

vi.mock("@/api/admin", () => ({
  adminApi: {
    connectorTypes: vi.fn(),
    listSources: vi.fn(),
    createSource: vi.fn(),
    syncSource: vi.fn(),
  },
}));

const mockConnectorTypes = [
  {
    type: "folder",
    label: "Folder",
    fields: [{ key: "path", label: "Folder path", required: true, sensitive: false, placeholder: "/data" }],
  },
  {
    type: "nifi",
    label: "NiFi",
    fields: [
      { key: "base_url", label: "NiFi base URL", required: true, sensitive: false, placeholder: "http://nifi:8080" },
      { key: "api_token", label: "API token", required: true, sensitive: true, placeholder: "" },
    ],
  },
];

beforeEach(() => {
  vi.mocked(adminApi.adminApi.connectorTypes).mockResolvedValue(mockConnectorTypes);
  vi.mocked(adminApi.adminApi.listSources).mockResolvedValue([]);
});

describe("AdminSourcesPage", () => {
  it("shows the Sources heading", async () => {
    render(<AdminSourcesPage />);
    expect(await screen.findByRole("heading", { name: "Sources" })).toBeInTheDocument();
  });

  it("shows empty state when there are no sources", async () => {
    render(<AdminSourcesPage />);
    expect(await screen.findByText(/no sources yet/i)).toBeInTheDocument();
  });

  it("renders sources table when sources exist", async () => {
    vi.mocked(adminApi.adminApi.listSources).mockResolvedValue([
      { id: "abc-1", name: "Legal Docs", type: "folder", path: "/data/legal", source_language: "en", enabled: true, created_at: "2025-01-01" },
    ]);
    render(<AdminSourcesPage />);
    expect(await screen.findByText("Legal Docs")).toBeInTheDocument();
    expect(screen.getByText("folder")).toBeInTheDocument();
  });

  it("opens the Add Source dialog on button click", async () => {
    const user = userEvent.setup();
    render(<AdminSourcesPage />);
    // Wait for connector types to load so button is enabled
    await screen.findByRole("heading", { name: "Sources" });
    await user.click(screen.getByRole("button", { name: /add source/i }));
    expect(await screen.findByRole("dialog", { name: /add source/i })).toBeInTheDocument();
  });

  it("renders folder path field when folder type is selected", async () => {
    const user = userEvent.setup();
    render(<AdminSourcesPage />);
    await screen.findByRole("heading", { name: "Sources" });
    await user.click(screen.getByRole("button", { name: /add source/i }));
    await screen.findByRole("dialog");
    expect(screen.getByLabelText(/folder path/i)).toBeInTheDocument();
  });

  it("renders sensitive api_token field as password input for nifi", async () => {
    const user = userEvent.setup();
    render(<AdminSourcesPage />);
    await screen.findByRole("heading", { name: "Sources" });
    await user.click(screen.getByRole("button", { name: /add source/i }));
    await screen.findByRole("dialog");

    // Switch type to nifi
    const typeSelect = screen.getByLabelText(/type/i);
    await user.selectOptions(typeSelect, "nifi");

    const tokenInput = screen.getByLabelText(/api token/i);
    expect(tokenInput).toHaveAttribute("type", "password");
  });

  it("calls createSource and closes dialog on valid submit", async () => {
    vi.mocked(adminApi.adminApi.createSource).mockResolvedValue({
      id: "new-1", name: "My Folder", type: "folder", path: "/tmp", source_language: "en", enabled: true, created_at: "2025-01-01",
    });
    const user = userEvent.setup();
    render(<AdminSourcesPage />);
    await screen.findByRole("heading", { name: "Sources" });
    await user.click(screen.getByRole("button", { name: /add source/i }));
    await screen.findByRole("dialog");

    await user.type(screen.getByLabelText(/name/i), "My Folder");
    await user.type(screen.getByLabelText(/folder path/i), "/tmp/docs");
    await user.click(screen.getByRole("button", { name: /save source/i }));

    await waitFor(() => {
      expect(adminApi.adminApi.createSource).toHaveBeenCalledWith(
        expect.objectContaining({ name: "My Folder", type: "folder" }),
        expect.anything(),
      );
    });
  });
});
