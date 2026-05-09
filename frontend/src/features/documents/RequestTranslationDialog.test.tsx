import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { render } from "@/test/render";
import { RequestTranslationDialog } from "./RequestTranslationDialog";
import * as documentsApi from "@/api/documents";

vi.mock("@/api/documents");
vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => vi.fn(),
  Link: ({ children, to }: { children: React.ReactNode; to: string }) => <a href={to}>{children}</a>,
}));

beforeEach(() => {
  vi.mocked(documentsApi.requestTranslation).mockResolvedValue({ queued: true });
});

describe("RequestTranslationDialog", () => {
  it("renders dialog when open", () => {
    render(<RequestTranslationDialog docId="doc-1" open onClose={vi.fn()} />);
    expect(screen.getByRole("heading", { name: /request high-quality translation/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /request translation/i })).toBeInTheDocument();
  });

  it("does not render when closed", () => {
    render(<RequestTranslationDialog docId="doc-1" open={false} onClose={vi.fn()} />);
    expect(screen.queryByRole("heading", { name: /request high-quality translation/i })).not.toBeInTheDocument();
  });

  it("calls onClose when Cancel is clicked", () => {
    const onClose = vi.fn();
    render(<RequestTranslationDialog docId="doc-1" open onClose={onClose} />);
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onClose).toHaveBeenCalled();
  });

  it("submits request and shows success state", async () => {
    render(<RequestTranslationDialog docId="doc-1" open onClose={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /request translation/i }));
    await waitFor(() => {
      expect(documentsApi.requestTranslation).toHaveBeenCalledWith("doc-1");
    });
  });
});
