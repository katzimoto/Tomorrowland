import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import { render } from "@/test/render";
import { MessageBubble } from "./MessageBubble";
import type { ChatMessage } from "@/api/chat";

function makeMsg(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    id: "msg-1",
    session_id: "sess-1",
    role: "assistant",
    content: "Test answer.",
    citations: [],
    model: "llama3",
    latency_ms: 100,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("MessageBubble", () => {
  it("renders message content", () => {
    render(<MessageBubble message={makeMsg()} />);
    expect(screen.getByText("Test answer.")).toBeInTheDocument();
  });

  it("renders grounding note for assistant messages", () => {
    render(<MessageBubble message={makeMsg()} />);
    expect(screen.getByText(/based only on/i)).toBeInTheDocument();
  });

  it("renders citation list when citations exist", () => {
    render(
      <MessageBubble
        message={makeMsg({
          citations: [
            {
              citation_id: "cit-1",
              document_id: "doc-1",
              doc_title: "Contract.pdf",
              chunk_text: "some text",
              score: 0.9,
              chunk_index: 0,
              source_id: null,
            },
          ],
        })}
      />
    );
    expect(screen.getByText("Sources")).toBeInTheDocument();
  });

  describe("debug panel", () => {
    it("shows debug panel when rewritten_query is present", () => {
      render(
        <MessageBubble
          message={makeMsg({ rewritten_query: "termination clause contract" })}
        />
      );
      expect(screen.getByText("Debug")).toBeInTheDocument();
      expect(
        screen.getByText("termination clause contract")
      ).toBeInTheDocument();
    });

    it("does not show debug panel when rewritten_query is absent", () => {
      render(<MessageBubble message={makeMsg()} />);
      expect(screen.queryByText("Debug")).not.toBeInTheDocument();
    });

    it("does not show debug panel for user messages even with rewritten_query", () => {
      render(
        <MessageBubble
          message={makeMsg({ role: "user", rewritten_query: "should not show" })}
        />
      );
      expect(screen.queryByText("Debug")).not.toBeInTheDocument();
    });
  });
});
