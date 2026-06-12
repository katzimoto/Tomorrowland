import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { render } from "@/test/render";
import { ChatWindow } from "./ChatWindow";
import type { ChatSession, ChatSessionWithMessages } from "@/api/chat";
import * as chatApi from "@/api/chat";

vi.mock("@/api/chat");

const SESSION: ChatSession = {
  id: "sess-1",
  user_id: "u1",
  title: "Test Chat",
  scope_type: "all_accessible_documents",
  scope_ids: [],
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  archived_at: null,
  message_count: 0,
};

const EMPTY_SESSION: ChatSessionWithMessages = {
  ...SESSION,
  messages: [],
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(chatApi.getChatSession).mockResolvedValue(EMPTY_SESSION);
  vi.mocked(chatApi.sendChatMessageStream).mockImplementation(
    async (_id, _input, onEvent) => {
      onEvent({
        type: "done",
        answer: "The answer is 42.",
        citations: [],
        message_id: "msg-reply",
      });
    },
  );
});

async function sendMessage(text: string) {
  const input = await screen.findByPlaceholderText("Ask a question…");
  fireEvent.change(input, { target: { value: text } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
}

describe("ChatWindow — streaming error path", () => {
  it("shows inline error state after send failure", async () => {
    vi.mocked(chatApi.sendChatMessageStream).mockRejectedValue(
      new Error("network"),
    );

    render(<ChatWindow session={SESSION} />);
    await sendMessage("Hello?");

    // The error appears in both the toast notification and the inline EmptyState.
    await waitFor(() => {
      expect(
        screen.getAllByText("Failed to send message. Please try again.").length,
      ).toBeGreaterThanOrEqual(2);
    });
  });

  it("shows a Retry button in the inline error state", async () => {
    vi.mocked(chatApi.sendChatMessageStream).mockRejectedValue(
      new Error("network"),
    );

    render(<ChatWindow session={SESSION} />);
    await sendMessage("Hello?");

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
    });
  });

  it("restores the input value after a send failure so the user can retry", async () => {
    vi.mocked(chatApi.sendChatMessageStream).mockRejectedValue(
      new Error("network"),
    );

    render(<ChatWindow session={SESSION} />);
    await sendMessage("Hello?");

    await waitFor(() => {
      expect(screen.getByPlaceholderText("Ask a question…")).toHaveValue(
        "Hello?",
      );
    });
  });

  it("preserves the user message in the list after a send failure", async () => {
    vi.mocked(chatApi.sendChatMessageStream).mockRejectedValue(
      new Error("network"),
    );

    render(<ChatWindow session={SESSION} />);
    await sendMessage("My important question");

    await waitFor(() => {
      expect(screen.getByText("My important question")).toBeInTheDocument();
    });
  });

  it("clears the error state and re-sends when Retry is clicked", async () => {
    vi.mocked(chatApi.sendChatMessageStream)
      .mockRejectedValueOnce(new Error("network"))
      .mockImplementationOnce(async (_id, _input, onEvent) => {
        onEvent({
          type: "done",
          answer: "Success on retry.",
          citations: [],
          message_id: "msg-retry",
        });
      });

    render(<ChatWindow session={SESSION} />);
    await sendMessage("Will this work?");

    const retryBtn = await screen.findByRole("button", { name: "Retry" });
    fireEvent.click(retryBtn);

    await waitFor(() => {
      expect(
        screen.queryByRole("button", { name: "Retry" }),
      ).not.toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByText("Success on retry.")).toBeInTheDocument();
    });
  });

  it("hides the error state when the user sends a new message successfully", async () => {
    vi.mocked(chatApi.sendChatMessageStream)
      .mockRejectedValueOnce(new Error("network"))
      .mockImplementationOnce(async (_id, _input, onEvent) => {
        onEvent({
          type: "done",
          answer: "New answer.",
          citations: [],
          message_id: "msg-new",
        });
      });

    render(<ChatWindow session={SESSION} />);
    await sendMessage("First message");

    // Error state should be visible
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
    });

    // Type a new message and click Send (input was restored to "First message")
    const input = screen.getByPlaceholderText("Ask a question…");
    fireEvent.change(input, { target: { value: "Second message" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => {
      expect(
        screen.queryByRole("button", { name: "Retry" }),
      ).not.toBeInTheDocument();
    });
  });

  it("does not show the error state when send succeeds", async () => {
    render(<ChatWindow session={SESSION} />);
    await sendMessage("A normal message");

    await waitFor(() => {
      expect(screen.getByText("The answer is 42.")).toBeInTheDocument();
    });
    expect(
      screen.queryByText("Failed to send message. Please try again."),
    ).not.toBeInTheDocument();
  });
});
