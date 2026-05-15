import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { render } from "@/test/render";
import { AdminAddSourceWizard } from "./AdminAddSourceWizard";
import * as adminApi from "@/api/admin";

vi.mock("@/api/admin", () => ({
  adminApi: {
    connectorTypes: vi.fn(),
    listSources: vi.fn(),
    createSource: vi.fn(),
    listGroups: vi.fn(),
    grantPermission: vi.fn(),
  },
}));

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
];

beforeEach(() => {
  vi.mocked(adminApi.adminApi.connectorTypes).mockResolvedValue(mockTypes);
  vi.mocked(adminApi.adminApi.listGroups).mockResolvedValue([]);
});

describe("AdminAddSourceWizard", () => {
  it("shows connector type selection", async () => {
    render(<AdminAddSourceWizard />);
    expect(await screen.findByText("Folder")).toBeInTheDocument();
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
    expect(screen.getByText("Auto detect")).toBeInTheDocument();
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
});
