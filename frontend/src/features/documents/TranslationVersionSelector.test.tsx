import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import { render } from "@/test/render";
import { TranslationVersionSelector } from "./TranslationVersionSelector";
import * as documentsApi from "@/api/documents";

vi.mock("@/api/documents");

beforeEach(() => {
  vi.mocked(documentsApi.getTranslationVersions).mockResolvedValue([
    { version_id: "v1", version_number: 1, label: "Manual EN", quality: "high", status: "done", target_language: "en", requested_at: "2024-01-01T00:00:00Z" },
    { version_id: "v2", version_number: 2, label: "Manual EN v2", quality: "high", status: "pending", target_language: "en", requested_at: "2024-02-01T00:00:00Z" },
    { version_id: "v3", version_number: 3, label: "Manual EN v3", quality: "high", status: "available", target_language: "en", requested_at: "2024-03-01T00:00:00Z" },
    { version_id: "v4", version_number: 4, label: "Manual EN v4", quality: "high", status: "running", target_language: "en", requested_at: "2024-04-01T00:00:00Z" },
  ]);
});

describe("TranslationVersionSelector", () => {
  it("renders version options", async () => {
    render(
      <TranslationVersionSelector
        docId="doc-1"
        selectedVersionId={undefined}
        onSelect={vi.fn()}
      />
    );
    const select = await screen.findByRole("combobox", { name: "Translation version" });
    expect(select).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Manual EN" })).toBeInTheDocument();
  });

  it("marks pending and running versions as disabled", async () => {
    render(
      <TranslationVersionSelector
        docId="doc-1"
        selectedVersionId={undefined}
        onSelect={vi.fn()}
      />
    );
    const pendingOption = await screen.findByRole("option", { name: /Manual EN v2/ });
    const runningOption = await screen.findByRole("option", { name: /Manual EN v4/ });
    expect(pendingOption).toBeDisabled();
    expect(runningOption).toBeDisabled();
  });

  it("allows backend available versions to be selected", async () => {
    render(
      <TranslationVersionSelector
        docId="doc-1"
        selectedVersionId={undefined}
        onSelect={vi.fn()}
      />
    );
    const availableOption = await screen.findByRole("option", { name: "Manual EN v3" });
    expect(availableOption).not.toBeDisabled();
  });

  it("returns null when no versions exist", async () => {
    vi.mocked(documentsApi.getTranslationVersions).mockResolvedValue([]);
    render(
      <TranslationVersionSelector
        docId="doc-1"
        selectedVersionId={undefined}
        onSelect={vi.fn()}
      />
    );
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });
});
