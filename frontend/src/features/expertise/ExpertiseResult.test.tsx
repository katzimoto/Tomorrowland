import { test, expect } from "vitest";
import { screen, render } from "@/test/render";
import { ExpertiseResult } from "./ExpertiseResult";

test("uses neutral evidence language", () => {
  render(<ExpertiseResult result={{ user_id: "u1", display_name: "Ari", topics: ["risk"], evidence_count: 1, evidence: [{ doc_id: "d1", title: "Risk memo", excerpt: "Evidence excerpt" }] }} />);
  expect(screen.getByText("1 evidence item found")).toBeInTheDocument();
  expect(screen.queryByText(/leader|rank|score/i)).not.toBeInTheDocument();
});
