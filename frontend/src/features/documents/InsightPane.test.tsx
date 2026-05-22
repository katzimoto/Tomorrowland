import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { render } from "@/test/render";
import { InsightPane } from "./InsightPane";
import * as documentsApi from "@/api/documents";
import * as commentsApi from "@/api/comments";
import * as annotationsApi from "@/api/annotations";
import * as chatApi from "@/api/chat";

vi.mock("@tanstack/react-router", () => ({
  Link: ({ children, to }: { children: React.ReactNode; to: string }) => (
    <a href={to}>{children}</a>
  ),
}));

vi.mock("@/api/documents");
vi.mock("@/api/comments");
vi.mock("@/api/annotations");
vi.mock("@/api/chat");

const mockPreview: documentsApi.DocumentPreview = {
  document_id: "doc-123",
  title: "Annual Report 2025",
  mime_type: "application/pdf",
  translation_quality: null,
  translation_score: null,
  metadata: {},
  snippet: "Fiscal year results.",
  view_count: 1,
};

const CHAT_SESSION: chatApi.ChatSession = {
  id: "session-doc",
  user_id: "user-1",
  title: "Chat: Annual Report 2025",
  scope_type: "single_document",
  scope_ids: ["doc-123"],
  created_at: "2026-05-21T10:00:00Z",
  updated_at: "2026-05-21T10:00:00Z",
  archived_at: null,
  message_count: 0,
};

beforeEach(() => {
  vi.mocked(documentsApi.getSummary).mockRejectedValue(new Error("not found"));
  vi.mocked(documentsApi.getEntities).mockRejectedValue(new Error("not found"));
  vi.mocked(documentsApi.getTags).mockRejectedValue(new Error("not found"));
  vi.mocked(documentsApi.getRelated).mockRejectedValue(new Error("not found"));
  vi.mocked(documentsApi.listDocumentVersions).mockResolvedValue([]);
  vi.mocked(commentsApi.listCommentsPage).mockResolvedValue({ comments: [], total: 0 });
  vi.mocked(annotationsApi.listAnnotations).mockResolvedValue([]);
  vi.mocked(chatApi.createChatSession).mockResolvedValue(CHAT_SESSION);
  vi.mocked(chatApi.getChatSession).mockResolvedValue({ ...CHAT_SESSION, messages: [] });
});

describe("InsightPane tabs", () => {
  it("renders Chat tab (not Q&A)", () => {
    render(<InsightPane docId="doc-123" preview={mockPreview} />);
    expect(screen.getByRole("tab", { name: "Chat" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Q&A" })).not.toBeInTheDocument();
  });

  it("mounts DocumentChatPanel when Chat tab is selected", async () => {
    render(<InsightPane docId="doc-123" preview={mockPreview} />);
    const chatTab = screen.getByRole("tab", { name: "Chat" });
    fireEvent.click(chatTab);
    await waitFor(() => {
      expect(chatApi.createChatSession).toHaveBeenCalledWith({
        scope_type: "single_document",
        scope_ids: ["doc-123"],
        title: "Chat: Annual Report 2025",
      });
    });
  });

  it("passes docTitle from preview to DocumentChatPanel", async () => {
    render(<InsightPane docId="doc-123" preview={mockPreview} />);
    const chatTab = screen.getByRole("tab", { name: "Chat" });
    fireEvent.click(chatTab);
    await waitFor(() => {
      expect(chatApi.createChatSession).toHaveBeenCalledWith(
        expect.objectContaining({ title: "Chat: Annual Report 2025" })
      );
    });
  });

  it("uses single_document scope for the chat session", async () => {
    render(<InsightPane docId="doc-123" preview={mockPreview} />);
    const chatTab = screen.getByRole("tab", { name: "Chat" });
    fireEvent.click(chatTab);
    await waitFor(() => {
      expect(chatApi.createChatSession).toHaveBeenCalledWith(
        expect.objectContaining({
          scope_type: "single_document",
          scope_ids: ["doc-123"],
        })
      );
    });
  });

  it("shows error state when session creation fails", async () => {
    vi.mocked(chatApi.createChatSession).mockRejectedValueOnce(new Error("server error"));
    render(<InsightPane docId="doc-123" preview={mockPreview} />);
    const chatTab = screen.getByRole("tab", { name: "Chat" });
    fireEvent.click(chatTab);
    await waitFor(() => {
      expect(screen.getByText("Failed to load chat.")).toBeInTheDocument();
    });
  });
});
