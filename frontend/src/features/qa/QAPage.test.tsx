import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { render } from "@/test/render";
import { QAPage } from "./QAPage";
import * as qaApi from "@/api/qa";

vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => vi.fn(),
  Link: ({ children, to }: { children: React.ReactNode; to: string }) => <a href={to}>{children}</a>,
}));

vi.mock("@/api/qa");

const mockAnswer: qaApi.QAResponse = {
  question: "What is vendor risk?",
  answer: "Vendor risk refers to the potential exposure from third-party vendors.",
  citations: [
    { doc_id: "doc-1", doc_title: "Vendor Risk Assessment 2024", chunk_text: "Vendor risk refers to…", score: 0.9 },
  ],
  model: "ollama/mistral",
};

beforeEach(() => {
  vi.mocked(qaApi.askQuestion).mockResolvedValue(mockAnswer);
});

describe("QAPage", () => {
  it("renders heading and question input", () => {
    render(<QAPage />);
    expect(screen.getByRole("heading", { name: "Q&A" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Question" })).toBeInTheDocument();
  });

  it("Ask button is disabled when input is empty", () => {
    render(<QAPage />);
    expect(screen.getByRole("button", { name: "Ask" })).toBeDisabled();
  });

  it("shows start empty state initially", () => {
    render(<QAPage />);
    expect(screen.getByText("Ask anything")).toBeInTheDocument();
  });

  it("shows answer and citation after successful query", async () => {
    render(<QAPage />);
    fireEvent.change(screen.getByRole("textbox", { name: "Question" }), {
      target: { value: "What is vendor risk?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => {
      expect(screen.getByText("Vendor risk refers to the potential exposure from third-party vendors.")).toBeInTheDocument();
      expect(screen.getByText("Vendor Risk Assessment 2024")).toBeInTheDocument();
    });
  });

  it("shows error state when query fails", async () => {
    vi.mocked(qaApi.askQuestion).mockRejectedValueOnce(new Error("network error"));
    render(<QAPage />);
    fireEvent.change(screen.getByRole("textbox", { name: "Question" }), {
      target: { value: "What is vendor risk?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => {
      expect(screen.getByText("Request failed")).toBeInTheDocument();
    });
  });
});
