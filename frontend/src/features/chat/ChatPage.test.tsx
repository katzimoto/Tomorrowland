import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { render } from "@/test/render";
import { ChatPage } from "./ChatPage";
import * as chatApi from "@/api/chat";

vi.mock("@/api/chat");

vi.mock("./PreviewWithHighlight", () => ({
  PreviewWithHighlight: () => <div data-testid="preview-with-highlight" />,
}));

const mockNavigate = vi.fn();
let mockSearchParams: Record<string, unknown> = {};

vi.mock("@tanstack/react-router", () => ({
  Link: ({ children, to }: { children: React.ReactNode; to: string }) => (
    <a href={to}>{children}</a>
  ),
  useSearch: () => mockSearchParams,
  useNavigate: () => mockNavigate,
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
  vi.clearAllMocks();
  mockSearchParams = {};
  mockNavigate.mockReset();
  vi.mocked(chatApi.listChatSessions).mockResolvedValue({
    sessions: [SESSION_1, SESSION_2],
    total: 2,
  });
  vi.mocked(chatApi.createChatSession).mockResolvedValue(NEW_SESSION);
  vi.mocked(chatApi.getChatSession).mockResolvedValue(SESSION_WITH_MESSAGES);
  vi.mocked(chatApi.sendChatMessage).mockResolvedValue(ASSISTANT_REPLY);
  vi.mocked(chatApi.sendChatMessageStream).mockImplementation(
    async (_sessionId, _input, onEvent) => {
      onEvent({ type: "done", answer: ASSISTANT_REPLY.content, citations: ASSISTANT_REPLY.citations ?? [], message_id: ASSISTANT_REPLY.id });
    },
  );
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
      expect(chatApi.sendChatMessageStream).toHaveBeenCalledWith(
        "session-1",
        { content: "What about renewal?" },
        expect.any(Function),
      );
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

    // Confirm dialog appears — click the "Delete" confirm button
    const confirmBtn = await screen.findByRole("button", { name: "Delete" });
    fireEvent.click(confirmBtn);

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

  it("falls back to doc_title and chunk_text when document_title/text_excerpt absent", async () => {
    vi.mocked(chatApi.getChatSession).mockResolvedValue({
      ...SESSION_1,
      messages: [
        {
          id: "msg-a",
          session_id: "session-1",
          role: "assistant",
          content: "Answer using legacy fields.",
          citations: [
            {
              citation_id: "cit-legacy",
              document_id: "doc-2",
              doc_title: "Legacy Doc Title",
              chunk_text: "Legacy chunk excerpt.",
              score: 0.8,
              chunk_index: 0,
              source_id: null,
            },
          ],
          model: "llama3",
          latency_ms: 500,
          created_at: "2026-05-21T10:01:00Z",
        },
      ],
    });

    render(<ChatPage />);
    const sessionBtn = await screen.findByText("Contract Review");
    fireEvent.click(sessionBtn);
    await waitFor(() => {
      expect(screen.getByText("Legacy Doc Title")).toBeInTheDocument();
      expect(screen.getByText("Legacy chunk excerpt.")).toBeInTheDocument();
    });
  });

  it("falls back to document_title and text_excerpt (new field names)", async () => {
    vi.mocked(chatApi.getChatSession).mockResolvedValue({
      ...SESSION_1,
      messages: [
        {
          id: "msg-b",
          session_id: "session-1",
          role: "assistant",
          content: "Answer using new fields.",
          citations: [
            {
              citation_id: "cit-new",
              document_id: "doc-3",
              document_title: "New Doc Title",
              text_excerpt: "New excerpt text.",
              score: 0.9,
              chunk_index: 1,
              source_id: null,
            } as chatApi.DocumentChatCitation,
          ],
          model: "llama3",
          latency_ms: 500,
          created_at: "2026-05-21T10:01:00Z",
        },
      ],
    });

    render(<ChatPage />);
    const sessionBtn = await screen.findByText("Contract Review");
    fireEvent.click(sessionBtn);
    await waitFor(() => {
      expect(screen.getByText("New Doc Title")).toBeInTheDocument();
      expect(screen.getByText("New excerpt text.")).toBeInTheDocument();
    });
  });
});

describe("URL-based scope session creation", () => {
  it("auto-creates a session when valid scope params are in the URL", async () => {
    mockSearchParams = { scope: "selected_documents", ids: "doc-a,doc-b" };
    vi.mocked(chatApi.getChatSession).mockResolvedValue({
      ...NEW_SESSION,
      messages: [],
    });
    render(<ChatPage />);
    await waitFor(() => {
      expect(chatApi.createChatSession).toHaveBeenCalledWith({
        scope_type: "selected_documents",
        scope_ids: ["doc-a", "doc-b"],
        title: null,
      });
    });
  });

  it("clears URL scope params after session creation", async () => {
    mockSearchParams = { scope: "single_document", ids: "doc-x" };
    vi.mocked(chatApi.getChatSession).mockResolvedValue({
      ...NEW_SESSION,
      messages: [],
    });
    render(<ChatPage />);
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith({
        to: "/chat",
        search: {},
        replace: true,
      });
    });
  });

  it("does not auto-create when scope param is invalid", async () => {
    mockSearchParams = { scope: "not_a_real_scope", ids: "doc-x" };
    render(<ChatPage />);
    // Give async effects time to run
    await new Promise((r) => setTimeout(r, 50));
    expect(chatApi.createChatSession).not.toHaveBeenCalled();
  });

  it("does not auto-create when no scope params are present", async () => {
    mockSearchParams = {};
    render(<ChatPage />);
    await new Promise((r) => setTimeout(r, 50));
    expect(chatApi.createChatSession).not.toHaveBeenCalled();
  });
});

describe("ChatWindow loading and error states", () => {
  it("shows loading state while session messages are fetching", async () => {
    vi.mocked(chatApi.getChatSession).mockReturnValue(new Promise(() => {}));

    render(<ChatPage />);
    const sessionBtn = await screen.findByText("Contract Review");
    fireEvent.click(sessionBtn);

    // Input should not appear while session is loading
    expect(
      screen.queryByPlaceholderText("Ask a question…"),
    ).not.toBeInTheDocument();
  });

  it("disables input and send button while message is pending", async () => {
    vi.mocked(chatApi.sendChatMessageStream).mockReturnValue(new Promise(() => {}));

    render(<ChatPage />);
    const sessionBtn = await screen.findByText("Contract Review");
    fireEvent.click(sessionBtn);
    await waitFor(() =>
      expect(screen.getByPlaceholderText("Ask a question…")).toBeInTheDocument(),
    );

    const input = screen.getByPlaceholderText("Ask a question…");
    fireEvent.change(input, { target: { value: "Pending question" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => {
      expect(screen.getByPlaceholderText("Ask a question…")).toBeDisabled();
    });
  });

  it("clears input after sending a message", async () => {
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
      expect(screen.getByPlaceholderText("Ask a question…")).toHaveValue("");
    });
  });

  it("shows error state when session load fails", async () => {
    vi.mocked(chatApi.getChatSession).mockRejectedValueOnce(
      new Error("session load failed"),
    );

    render(<ChatPage />);
    const sessionBtn = await screen.findByText("Contract Review");
    fireEvent.click(sessionBtn);

    await waitFor(() => {
      expect(
        screen.getByText("Failed to load chat."),
      ).toBeInTheDocument();
    });
  });
});
