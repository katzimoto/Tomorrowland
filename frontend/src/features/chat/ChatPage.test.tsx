import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { render } from "@/test/render";
import { ChatPage } from "./ChatPage";
import * as chatApi from "@/api/chat";

vi.mock("@/api/chat");

vi.mock("@tanstack/react-router", () => ({
  Link: ({ children, to }: { children: React.ReactNode; to: string }) => (
    <a href={to}>{children}</a>
  ),
}));

const SESSION_1: chatApi.ChatSession = {
  id: "session-1",
  user_id: "user-1",
  title: "Contract Review",
  scope_type: "all_accessible_documents",
  scope_ids: [],
  created_at: "2026-05-21T10:00:00Z",
  updated_at: "2026-05-21T10:00:00Z",
  archived_at: null,
  message_count: 2,
};

const SESSION_2: chatApi.ChatSession = {
  id: "session-2",
  user_id: "user-1",
  title: "Invoice Analysis",
  scope_type: "single_document",
  scope_ids: ["doc-1"],
  created_at: "2026-05-21T11:00:00Z",
  updated_at: "2026-05-21T11:00:00Z",
  archived_at: null,
  message_count: 0,
};

const SESSION_WITH_MESSAGES: chatApi.ChatSessionWithMessages = {
  ...SESSION_1,
  messages: [
    {
      id: "msg-1",
      session_id: "session-1",
      role: "user",
      content: "What is the termination clause?",
      created_at: "2026-05-21T10:01:00Z",
    },
    {
      id: "msg-2",
      session_id: "session-1",
      role: "assistant",
      content: "Either party may terminate with 30 days notice.",
      citations: [
        {
          citation_id: "cit-1",
          document_id: "doc-1",
          doc_title: "Contract.pdf",
          chunk_text: "Either party may terminate…",
          score: 0.91,
          chunk_index: 5,
          source_id: null,
        },
      ],
      model: "llama3",
      latency_ms: 1200,
      created_at: "2026-05-21T10:01:05Z",
    },
  ],
};

const ASSISTANT_REPLY: chatApi.ChatMessage = {
  id: "msg-3",
  session_id: "session-1",
  role: "assistant",
  content: "The renewal clause auto-renews annually.",
  citations: [],
  model: "llama3",
  latency_ms: 800,
  created_at: "2026-05-21T10:02:00Z",
};

const NEW_SESSION: chatApi.ChatSession = {
  id: "session-new",
  user_id: "user-1",
  title: "New Chat",
  scope_type: "all_accessible_documents",
  scope_ids: [],
  created_at: "2026-05-21T12:00:00Z",
  updated_at: "2026-05-21T12:00:00Z",
  archived_at: null,
  message_count: 0,
};

beforeEach(() => {
  vi.mocked(chatApi.listChatSessions).mockResolvedValue({
    sessions: [SESSION_1, SESSION_2],
    total: 2,
  });
  vi.mocked(chatApi.createChatSession).mockResolvedValue(NEW_SESSION);
  vi.mocked(chatApi.getChatSession).mockResolvedValue(SESSION_WITH_MESSAGES);
  vi.mocked(chatApi.sendChatMessage).mockResolvedValue(ASSISTANT_REPLY);
  vi.mocked(chatApi.deleteChatSession).mockResolvedValue({ ok: true });
  vi.mocked(chatApi.patchChatSession).mockResolvedValue(SESSION_1);
});

describe("ChatPage", () => {
  it("renders empty state when no session is selected", () => {
    render(<ChatPage />);
    expect(
      screen.getByText("Ask questions about your documents."),
    ).toBeInTheDocument();
  });

  it("shows Start a chat button in empty state", () => {
    render(<ChatPage />);
    expect(
      screen.getByRole("button", { name: "Start a chat" }),
    ).toBeInTheDocument();
  });

  it("renders session list in sidebar", async () => {
    render(<ChatPage />);
    await waitFor(() => {
      expect(screen.getByText("Contract Review")).toBeInTheDocument();
      expect(screen.getByText("Invoice Analysis")).toBeInTheDocument();
    });
  });

  it("shows New Chat button in sidebar", async () => {
    render(<ChatPage />);
    await waitFor(() => {
      expect(
        screen.getAllByRole("button", { name: "New Chat" })[0],
      ).toBeInTheDocument();
    });
  });

  it("creates a new session and selects it when Start a chat is clicked", async () => {
    vi.mocked(chatApi.listChatSessions).mockResolvedValue({
      sessions: [],
      total: 0,
    });
    vi.mocked(chatApi.getChatSession).mockResolvedValue({
      ...NEW_SESSION,
      messages: [],
    });
    render(<ChatPage />);
    const btn = await screen.findByRole("button", { name: "Start a chat" });
    fireEvent.click(btn);
    await waitFor(() => {
      expect(chatApi.createChatSession).toHaveBeenCalledWith({
        scope_type: "all_accessible_documents",
        scope_ids: [],
        title: null,
      });
    });
  });

  it("selects a session and loads its messages", async () => {
    render(<ChatPage />);
    const sessionBtn = await screen.findByText("Contract Review");
    fireEvent.click(sessionBtn);
    await waitFor(() => {
      expect(chatApi.getChatSession).toHaveBeenCalledWith("session-1");
    });
    await waitFor(() => {
      expect(
        screen.getByText("What is the termination clause?"),
      ).toBeInTheDocument();
      expect(
        screen.getByText("Either party may terminate with 30 days notice."),
      ).toBeInTheDocument();
    });
  });

  it("sends a message and renders assistant reply", async () => {
    render(<ChatPage />);
    const sessionBtn = await screen.findByText("Contract Review");
    fireEvent.click(sessionBtn);
    await waitFor(() =>
      expect(screen.getByPlaceholderText("Ask a question…")).toBeInTheDocument(),
    );

    const input = screen.getByPlaceholderText("Ask a question…");
    fireEvent.change(input, { target: { value: "What about renewal?" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => {
      expect(chatApi.sendChatMessage).toHaveBeenCalledWith("session-1", {
        content: "What about renewal?",
      });
    });
    await waitFor(() => {
      expect(
        screen.getByText("The renewal clause auto-renews annually."),
      ).toBeInTheDocument();
    });
  });

  it("renders citation card under assistant message", async () => {
    render(<ChatPage />);
    const sessionBtn = await screen.findByText("Contract Review");
    fireEvent.click(sessionBtn);
    await waitFor(() => {
      expect(screen.getByText("Contract.pdf")).toBeInTheDocument();
    });
  });

  it("deletes selected session and returns to empty state", async () => {
    render(<ChatPage />);
    const sessionBtn = await screen.findByText("Contract Review");
    fireEvent.click(sessionBtn);

    await waitFor(() =>
      expect(screen.getByPlaceholderText("Ask a question…")).toBeInTheDocument(),
    );

    const deleteBtns = screen.getAllByRole("button", { name: "Delete chat" });
    fireEvent.click(deleteBtns[0]);

    await waitFor(() => {
      expect(chatApi.deleteChatSession).toHaveBeenCalledWith("session-1");
    });
    await waitFor(() => {
      expect(
        screen.getByText("Ask questions about your documents."),
      ).toBeInTheDocument();
    });
  });

  it("shows loading skeleton while sessions are fetching", () => {
    vi.mocked(chatApi.listChatSessions).mockReturnValue(new Promise(() => {}));
    render(<ChatPage />);
    // Skeleton rows are rendered (they don't have accessible text to target,
    // but the empty state should not yet be shown)
    expect(
      screen.queryByText("Contract Review"),
    ).not.toBeInTheDocument();
  });

  it("shows error message when session list fails", async () => {
    vi.mocked(chatApi.listChatSessions).mockRejectedValueOnce(
      new Error("network"),
    );
    render(<ChatPage />);
    await waitFor(() => {
      expect(screen.getByText("Failed to load chats.")).toBeInTheDocument();
    });
  });
});

describe("ChatCitationCard", () => {
  it("renders citation with stable key (citation_id)", async () => {
    render(<ChatPage />);
    const sessionBtn = await screen.findByText("Contract Review");
    fireEvent.click(sessionBtn);
    await waitFor(() => {
      expect(screen.getByText("Contract.pdf")).toBeInTheDocument();
      expect(screen.getByText("Either party may terminate…")).toBeInTheDocument();
    });
  });
});
