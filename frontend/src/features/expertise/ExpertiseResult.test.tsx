import { test, expect } from "vitest";
import { screen, render } from "@/test/render";
import { ExpertiseResult } from "./ExpertiseResult";

test("uses neutral evidence language with backend-shaped results", () => {
  render(
    <ExpertiseResult
      result={{
        user_id: "u1",
        display_name: "Ari",
        score: 1.4,
        signals: { views: 2, annotations: 3, subscriptions: 1 },
        reason: "Has activity on matching documents",
        top_docs: [{ document_id: "d1", title: "Risk memo", score: 0.9 }],
      }}
    />
  );

  expect(screen.getByText("Ari")).toBeInTheDocument();
  expect(
    screen.getByText("Has activity on matching documents")
  ).toBeInTheDocument();
  expect(screen.getByText("Evidence, not ranking")).toBeInTheDocument();
  expect(screen.getByText("Risk memo")).toBeInTheDocument();
  expect(screen.getByText("Views")).toBeInTheDocument();
  expect(screen.getByText("Annotations")).toBeInTheDocument();
  expect(screen.queryByText("Comments")).not.toBeInTheDocument();
  expect(
    screen.queryByText(/undefined evidence items/i)
  ).not.toBeInTheDocument();
  expect(screen.queryByText(/leaderboard/i)).not.toBeInTheDocument();
});

test("does not require invented topic or evidence fields", () => {
  render(
    <ExpertiseResult
      result={{
        user_id: "u2",
        display_name: null,
        score: 0,
        signals: { views: 0, annotations: 0, subscriptions: 0 },
        reason: "Has activity on matching documents",
        top_docs: [],
      }}
    />
  );

  expect(screen.getByText("Unknown reader")).toBeInTheDocument();
  expect(screen.getByText("Evidence, not ranking")).toBeInTheDocument();
  expect(screen.queryByText(/undefined/i)).not.toBeInTheDocument();
});
