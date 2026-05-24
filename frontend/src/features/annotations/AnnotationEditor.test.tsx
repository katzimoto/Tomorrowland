import { beforeEach, test, expect, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { screen, render, waitFor } from "@/test/render";
import { AnnotationEditor } from "./AnnotationEditor";

const mocks = vi.hoisted(() => ({
  createAnnotation: vi.fn(),
  updateAnnotation: vi.fn(),
}));

vi.mock("@/api/annotations", () => ({
  createAnnotation: mocks.createAnnotation,
  updateAnnotation: mocks.updateAnnotation,
}));

beforeEach(() => {
  mocks.createAnnotation.mockReset();
  mocks.updateAnnotation.mockReset();
  mocks.createAnnotation.mockResolvedValue({ id: "a1" });
  mocks.updateAnnotation.mockResolvedValue({ id: "a1" });
});

test("Enter submits a new annotation", async () => {
  const user = userEvent.setup();
  render(<AnnotationEditor docId="d1" />);
  await user.type(screen.getByLabelText("New annotation"), "quick note");
  await user.keyboard("{Enter}");
  await waitFor(() =>
    expect(mocks.createAnnotation).toHaveBeenCalledWith("d1", {
      body: "quick note",
      shared: false,
      position: null,
    })
  );
});

test("Shift+Enter inserts a newline instead of submitting in annotation editor", async () => {
  const user = userEvent.setup();
  render(<AnnotationEditor docId="d1" />);
  await user.type(screen.getByLabelText("New annotation"), "line one");
  await user.keyboard("{Shift>}{Enter}{/Shift}");
  expect(screen.getByLabelText("New annotation")).toHaveValue("line one\n");
  expect(mocks.createAnnotation).not.toHaveBeenCalled();
});

test("supports shared annotation toggle", async () => {
  const user = userEvent.setup();
  render(<AnnotationEditor docId="d1" />);
  await user.type(screen.getByLabelText("New annotation"), "private note");
  await user.click(
    screen.getByLabelText("Share with readers who can access this document")
  );
  expect(
    screen.getByLabelText("Share with readers who can access this document")
  ).toBeChecked();
});

test("sends create annotations through the backend-compatible API boundary", async () => {
  const user = userEvent.setup();
  render(<AnnotationEditor docId="d1" />);

  await user.type(screen.getByLabelText("New annotation"), "shared note");
  await user.click(
    screen.getByLabelText("Share with readers who can access this document")
  );
  await user.click(screen.getByRole("button", { name: "Create annotation" }));

  await waitFor(() =>
    expect(mocks.createAnnotation).toHaveBeenCalledWith("d1", {
      body: "shared note",
      shared: true,
      position: null,
    })
  );
});

test("sends update annotations with body shared and position for API mapping", async () => {
  const user = userEvent.setup();
  render(
    <AnnotationEditor
      docId="d1"
      annotation={{
        id: "a1",
        document_id: "d1",
        author_id: "u1",
        author_name: "Ari",
        body: "old note",
        position: { page: 4 },
        shared: false,
        created_at: "2026-05-01T10:00:00Z",
        can_modify: true,
      }}
    />
  );

  await user.clear(screen.getByLabelText("Edit annotation"));
  await user.type(screen.getByLabelText("Edit annotation"), "updated note");
  await user.click(
    screen.getByLabelText("Share with readers who can access this document")
  );
  await user.click(screen.getByRole("button", { name: "Save annotation" }));

  await waitFor(() =>
    expect(mocks.updateAnnotation).toHaveBeenCalledWith("a1", {
      body: "updated note",
      shared: true,
      position: { page: 4 },
    })
  );
});
