import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { render } from "@/test/render";
import { AdminAddSourceWizard } from "./AdminAddSourceWizard";
import * as adminApi from "@/api/admin";

vi.mock("@tanstack/react-router", async (importOriginal) => {
  const actual = await importOriginal() as Record<string, unknown>;
  return { ...actual, useNavigate: () => () => {} };
});

vi.mock("@/api/admin", () => ({
  adminApi: {
    connectorTypes: vi.fn(),
    listSources: vi.fn(),
    createSource: vi.fn(),
    listGroups: vi.fn(),
    grantPermission: vi.fn(),
    sourceLanguages: vi.fn(),
  },
}));

const MOCK_SOURCE_LANGUAGES = ["en", "he", "ar", "fr", "ru", "es", "zh", "ko", "th"];

const mockTypes = [
  {
    type: "folder",
    label: "Folder",
    fields: [
      { key: "path", label: "Folder path", required: true, sensitive: false, placeholder: "/data/docs" },
    ],
    supported_versions: {
      en: [{ value: "1.0", label: "1.0" }, { value: "2.0", label: "2.0" }],
      fr: [{ value: "1.0", label: "1.0" }],
    },
  },
  {
    type: "simple",
    label: "Simple",
    fields: [],
  },
];

beforeEach(() => {
  vi.mocked(adminApi.adminApi.connectorTypes).mockResolvedValue(mockTypes);
  vi.mocked(adminApi.adminApi.listGroups).mockResolvedValue([]);
  vi.mocked(adminApi.adminApi.sourceLanguages).mockResolvedValue(MOCK_SOURCE_LANGUAGES);
});

describe("AdminAddSourceWizard", () => {
  it("shows connector type selection", async () => {
    render(<AdminAddSourceWizard />);
    expect(await screen.findByText("Folder")).toBeInTheDocument();
  });

  it("shows Auto detect as the first and default language option", async () => {
    const user = userEvent.setup();
    render(<AdminAddSourceWizard />);
    await screen.findByText("Folder");
    await user.click(screen.getByText("Folder"));
    const langSelect = screen.getByLabelText("Language");
    expect(langSelect).toHaveValue("");
    // Both Language and Version dropdowns have "Auto detect"; at least one must exist
    expect(screen.getAllByRole("option", { name: "Auto detect" }).length).toBeGreaterThan(0);
  });

  it("populates language dropdown from the source-languages API", async () => {
    const user = userEvent.setup();
    render(<AdminAddSourceWizard />);
    await screen.findByText("Folder");
    await user.click(screen.getByText("Folder"));
    expect(screen.getByRole("option", { name: "English" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Hebrew" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Chinese" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Korean" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Thai" })).toBeInTheDocument();
  });

  it("shows version dropdown with language-specific versions", async () => {
    const user = userEvent.setup();
    render(<AdminAddSourceWizard />);
    await screen.findByText("Folder");
    await user.click(screen.getByText("Folder"));
    const langSelect = screen.getByLabelText("Language");
    await user.selectOptions(langSelect, "fr");
    const versionSelect = screen.getByLabelText("Version");
    expect(versionSelect).toBeInTheDocument();
  });

  it("includes auto-detect as default version option", async () => {
    const user = userEvent.setup();
    render(<AdminAddSourceWizard />);
    await screen.findByText("Folder");
    await user.click(screen.getByText("Folder"));
    expect(screen.getByLabelText("Version")).toHaveValue("auto-detect");
  });

  it("updates version options when language changes", async () => {
    const user = userEvent.setup();
    render(<AdminAddSourceWizard />);
    await screen.findByText("Folder");
    await user.click(screen.getByText("Folder"));
    const langSelect = screen.getByLabelText("Language");
    await user.selectOptions(langSelect, "en");
    expect(screen.getByText("2.0")).toBeInTheDocument();
    await user.selectOptions(langSelect, "fr");
    expect(screen.queryByText("2.0")).not.toBeInTheDocument();
  });

  it("shows no version dropdown for connector without supported_versions", async () => {
    const user = userEvent.setup();
    render(<AdminAddSourceWizard />);
    await screen.findByText("Simple");
    await user.click(screen.getByText("Simple"));
    expect(screen.queryByLabelText("Version")).not.toBeInTheDocument();
  });

  it("language dropdown shows all API languages regardless of connector supported_versions", async () => {
    const user = userEvent.setup();
    render(<AdminAddSourceWizard />);
    await screen.findByText("Simple");
    await user.click(screen.getByText("Simple"));
    expect(screen.getByRole("option", { name: "Auto detect" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Hebrew" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Korean" })).toBeInTheDocument();
  });

  it("resets to auto detect language and version when switching connector type", async () => {
    const user = userEvent.setup();
    render(<AdminAddSourceWizard />);
    await screen.findByText("Folder");
    await user.click(screen.getByText("Folder"));
    await user.selectOptions(screen.getByLabelText("Language"), "fr");
    await user.selectOptions(screen.getByLabelText("Version"), "1.0");
    const backButtons = screen.getAllByRole("button", { name: /back/i });
    await user.click(backButtons[backButtons.length - 1]);
    await user.click(screen.getByText("Simple"));
    expect(screen.getByLabelText("Language")).toHaveValue("");
  });

  it("resets version to auto-detect when changing to language that does not support current version", async () => {
    const user = userEvent.setup();
    render(<AdminAddSourceWizard />);
    await screen.findByText("Folder");
    await user.click(screen.getByText("Folder"));
    // Select "en" first so version options ["1.0", "2.0"] appear, then pick "2.0"
    await user.selectOptions(screen.getByLabelText("Language"), "en");
    await user.selectOptions(screen.getByLabelText("Version"), "2.0");
    // Switch to "fr" which only has "1.0" — "2.0" is no longer valid
    await user.selectOptions(screen.getByLabelText("Language"), "fr");
    expect(screen.getByLabelText("Version")).toHaveValue("auto-detect");
  });

  it("shows Auto detect on review screen when no language is selected", async () => {
    const user = userEvent.setup();
    render(<AdminAddSourceWizard />);
    await screen.findByText("Folder");
    await user.click(screen.getByText("Folder"));
    await user.type(screen.getByLabelText("Source name"), "My Source");
    await user.click(screen.getByRole("button", { name: /next: validate/i }));
    await user.click(screen.getByRole("button", { name: /skip validation/i }));
    await user.click(screen.getByRole("button", { name: /next: review/i }));
    const languageDt = screen.getByText("Language");
    expect(languageDt.nextElementSibling?.textContent).toBe("Auto detect");
  });

  it("shows readable language label on review screen when a language is selected", async () => {
    const user = userEvent.setup();
    render(<AdminAddSourceWizard />);
    await screen.findByText("Folder");
    await user.click(screen.getByText("Folder"));
    await user.selectOptions(screen.getByLabelText("Language"), "he");
    await user.type(screen.getByLabelText("Source name"), "My Source");
    await user.click(screen.getByRole("button", { name: /next: validate/i }));
    await user.click(screen.getByRole("button", { name: /skip validation/i }));
    await user.click(screen.getByRole("button", { name: /next: review/i }));
    const languageDt = screen.getByText("Language");
    expect(languageDt.nextElementSibling?.textContent).toBe("Hebrew");
  });

  it("sends null source_language when auto detect is selected", async () => {
    const user = userEvent.setup();
    vi.mocked(adminApi.adminApi.createSource).mockResolvedValue({
      id: "abc",
      name: "My Source",
      type: "folder",
      path: null,
      source_language: null,
      enabled: true,
      created_at: null,
      last_sync_status: null,
      last_sync_indexed: null,
      last_sync_skipped: null,
      last_sync_failed: null,
      last_sync_error: null,
      last_sync_at: null,
      last_validation_status: null,
      last_validation_error: null,
      last_validated_at: null,
    });
    vi.mocked(adminApi.adminApi.grantPermission).mockResolvedValue(undefined as never);
    render(<AdminAddSourceWizard />);
    await screen.findByText("Folder");
    await user.click(screen.getByText("Folder"));
    await user.type(screen.getByLabelText("Source name"), "My Source");
    await user.click(screen.getByRole("button", { name: /next: validate/i }));
    await user.click(screen.getByRole("button", { name: /skip validation/i }));
    await user.click(screen.getByRole("button", { name: /next: review/i }));
    await user.click(screen.getByRole("button", { name: /create source/i }));
    expect(vi.mocked(adminApi.adminApi.createSource)).toHaveBeenCalledWith(
      expect.objectContaining({ source_language: null }),
    );
  });
});
