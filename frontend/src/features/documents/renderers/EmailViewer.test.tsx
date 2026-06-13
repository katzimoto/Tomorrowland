import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import { render } from "@/test/render";
import { EmailViewer } from "./EmailViewer";
import type { PreviewManifest, PreviewEmailManifest } from "@/api/preview";
import * as previewApi from "@/api/preview";

vi.mock("@tanstack/react-router", () => ({
  Link: ({ children, ...rest }: Record<string, unknown>) => (
    <a href={(rest.to as string) ?? ""} {...rest}>
      {children as React.ReactNode}
    </a>
  ),
}));

vi.mock("@/api/preview", async (importOriginal) => ({
  ...(await importOriginal<typeof previewApi>()),
  getPreviewArtifactText: vi.fn(),
}));

const mockedArtifact = vi.mocked(previewApi.getPreviewArtifactText);

function makeEmail(overrides: Partial<PreviewEmailManifest> = {}): PreviewEmailManifest {
  return {
    subject: "Design proposal",
    from: "alice@example.com",
    to: ["bob@example.com"],
    cc: [],
    bcc: [],
    date: "2026-01-06T10:00:00+01:00",
    message_id: "<m1@example.com>",
    in_reply_to: null,
    has_html_body: true,
    has_text_body: true,
    quoted_ranges: [],
    inline_images: [],
    skipped_inline_images: 0,
    blocked_remote_images: 0,
    embedded_inline_images: 0,
    attachments: [],
    ...overrides,
  };
}

function makeManifest(email: PreviewEmailManifest): PreviewManifest {
  return {
    document_id: "doc-1",
    cache_key: "sha256:abc",
    kind: "email",
    renderer: "email",
    status: "ready",
    error: null,
    generated_at: null,
    retry_after_ms: null,
    navigation: { unit: "none", count: 0, items: [] },
    artifacts: [],
    email,
    office: null,
    evidence: { supports_text_search: true, anchor_unit: "body", regions_available: false },
  };
}

beforeEach(() => {
  mockedArtifact.mockReset();
  mockedArtifact.mockImplementation((_docId, artifactId) =>
    Promise.resolve(
      artifactId === "body-html"
        ? "<p>Formatted body</p>"
        : "Plain text body with secret word inside.",
    ),
  );
});

describe("EmailViewer", () => {
  it("renders header metadata", () => {
    render(<EmailViewer manifest={makeManifest(makeEmail())} docId="doc-1" />);
    expect(screen.getByText("Design proposal")).toBeInTheDocument();
    expect(screen.getByText("alice@example.com")).toBeInTheDocument();
    expect(screen.getByText("bob@example.com")).toBeInTheDocument();
  });

  it("renders the HTML body in a sandboxed iframe by default", async () => {
    render(<EmailViewer manifest={makeManifest(makeEmail())} docId="doc-1" />);
    const iframe = await screen.findByTitle("Email body");
    expect(iframe).toHaveAttribute("sandbox", "");
    await waitFor(() => {
      expect(iframe).toHaveAttribute("srcdoc", "<p>Formatted body</p>");
    });
  });

  it("switches to the text body via the toggle", async () => {
    render(<EmailViewer manifest={makeManifest(makeEmail())} docId="doc-1" />);
    fireEvent.click(screen.getByRole("button", { name: "Text" }));
    expect(await screen.findByText(/Plain text body/)).toBeInTheDocument();
  });

  it("forces the text body and highlights matches when searching", async () => {
    const onMatchCountChange = vi.fn();
    render(
      <EmailViewer
        manifest={makeManifest(makeEmail())}
        docId="doc-1"
        searchQuery="secret"
        onMatchCountChange={onMatchCountChange}
      />,
    );
    await waitFor(() => expect(onMatchCountChange).toHaveBeenCalledWith(1));
    expect(screen.queryByTitle("Email body")).not.toBeInTheDocument();
    const marks = document.querySelectorAll("mark");
    expect(marks.length).toBe(1);
    expect(marks[0]?.textContent).toBe("secret");
  });

  it("shows a notice when remote images were blocked", () => {
    render(
      <EmailViewer manifest={makeManifest(makeEmail({ blocked_remote_images: 2 }))} docId="doc-1" />,
    );
    expect(screen.getByRole("note")).toHaveTextContent("2 remote images were blocked");
  });

  it("links attachments that have a preview-available child document", () => {
    const email = makeEmail({
      attachments: [
        {
          filename: "contract.pdf",
          content_type: "application/pdf",
          size_bytes: 102400,
          document_id: "child-9",
          preview_available: true,
          inline: false,
        },
        {
          filename: "notes.txt",
          content_type: "text/plain",
          size_bytes: 12,
          document_id: null,
          preview_available: false,
          inline: false,
        },
      ],
    });
    render(<EmailViewer manifest={makeManifest(email)} docId="doc-1" />);
    const link = screen.getByRole("link", { name: "contract.pdf" });
    expect(link).toHaveAttribute("href", "/doc/$docId");
    expect(screen.getByText("notes.txt").closest("a")).toBeNull();
  });

  it("collapses quoted reply text behind a disclosure", async () => {
    mockedArtifact.mockImplementation((_docId, artifactId) =>
      Promise.resolve(
        artifactId === "body-text"
          ? "Latest reply line\nOn Mon Alice wrote:\n> older quoted line"
          : "<p>html</p>",
      ),
    );
    const email = makeEmail({
      has_html_body: false,
      quoted_ranges: [{ start_line: 1, end_line: 2, label: "On Mon Alice wrote:" }],
    });
    render(<EmailViewer manifest={makeManifest(email)} docId="doc-1" />);
    expect(await screen.findByText(/Latest reply line/)).toBeInTheDocument();
    expect(screen.getByText("Show quoted text")).toBeInTheDocument();
  });
});
