import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { render } from "@/test/render";
import { UserTagEditor } from "./UserTagEditor";

vi.mock("@/api/documents");

import * as documentsApi from "@/api/documents";

const mockListUserTags = vi.mocked(documentsApi.listUserTags);
const mockAddUserTag = vi.mocked(documentsApi.addUserTag);
const mockDeleteUserTag = vi.mocked(documentsApi.deleteUserTag);

const EMPTY_RESPONSE: documentsApi.UserTagsResponse = {
  document_id: "doc-1",
  tags: [],
};

const TAG_PRIVATE: documentsApi.UserDocumentTag = {
  id: "tag-1",
  tag: "my-private",
  visibility: "private",
  created_at: "2026-05-22T10:00:00Z",
  owned_by_me: true,
};

const TAG_PUBLIC_OTHER: documentsApi.UserDocumentTag = {
  id: "tag-2",
  tag: "shared-tag",
  visibility: "public",
  created_at: "2026-05-22T10:00:00Z",
  owned_by_me: false,
};

beforeEach(() => {
  vi.clearAllMocks();
  mockListUserTags.mockResolvedValue(EMPTY_RESPONSE);
  mockAddUserTag.mockResolvedValue(TAG_PRIVATE);
  mockDeleteUserTag.mockResolvedValue(undefined);
});

describe("UserTagEditor", () => {
  it("shows loading state initially", () => {
    mockListUserTags.mockReturnValue(new Promise(() => {}));
    render(<UserTagEditor docId="doc-1" />);
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("shows 'No tags yet' when list is empty", async () => {
    render(<UserTagEditor docId="doc-1" />);
    await waitFor(() => {
      expect(screen.getByText("No tags yet")).toBeInTheDocument();
    });
  });

  it("renders existing tags", async () => {
    mockListUserTags.mockResolvedValue({
      document_id: "doc-1",
      tags: [TAG_PRIVATE, TAG_PUBLIC_OTHER],
    });
    render(<UserTagEditor docId="doc-1" />);
    await waitFor(() => {
      expect(screen.getByText("my-private")).toBeInTheDocument();
      expect(screen.getByText("shared-tag")).toBeInTheDocument();
    });
  });

  it("shows delete button only for owned tags", async () => {
    mockListUserTags.mockResolvedValue({
      document_id: "doc-1",
      tags: [TAG_PRIVATE, TAG_PUBLIC_OTHER],
    });
    render(<UserTagEditor docId="doc-1" />);
    await waitFor(() => screen.getByText("my-private"));
    expect(screen.getByRole("button", { name: /remove tag my-private/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /remove tag shared-tag/i })).not.toBeInTheDocument();
  });

  it("renders add input and visibility radios", async () => {
    render(<UserTagEditor docId="doc-1" />);
    await waitFor(() => screen.getByText("No tags yet"));
    expect(screen.getByLabelText("New tag text")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add tag" })).toBeInTheDocument();
    expect(screen.getByLabelText(/private/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/public/i)).toBeInTheDocument();
  });

  it("defaults visibility to private", async () => {
    render(<UserTagEditor docId="doc-1" />);
    await waitFor(() => screen.getByText("No tags yet"));
    const privateRadio = screen.getByLabelText(/private/i) as HTMLInputElement;
    expect(privateRadio.checked).toBe(true);
  });

  it("can switch visibility to public", async () => {
    render(<UserTagEditor docId="doc-1" />);
    await waitFor(() => screen.getByText("No tags yet"));
    fireEvent.click(screen.getByLabelText(/public/i));
    const publicRadio = screen.getByLabelText(/public/i) as HTMLInputElement;
    expect(publicRadio.checked).toBe(true);
  });

  it("calls addUserTag on Add button click with trimmed input", async () => {
    mockAddUserTag.mockResolvedValue(TAG_PRIVATE);
    render(<UserTagEditor docId="doc-1" />);
    await waitFor(() => screen.getByText("No tags yet"));

    const input = screen.getByLabelText("New tag text");
    fireEvent.change(input, { target: { value: "  contract  " } });
    fireEvent.click(screen.getByRole("button", { name: "Add tag" }));

    await waitFor(() => {
      expect(mockAddUserTag).toHaveBeenCalledWith("doc-1", "contract", "private");
    });
  });

  it("calls addUserTag on Enter key", async () => {
    mockAddUserTag.mockResolvedValue(TAG_PRIVATE);
    render(<UserTagEditor docId="doc-1" />);
    await waitFor(() => screen.getByText("No tags yet"));

    const input = screen.getByLabelText("New tag text");
    fireEvent.change(input, { target: { value: "enter-tag" } });
    fireEvent.keyDown(input, { key: "Enter" });

    await waitFor(() => {
      expect(mockAddUserTag).toHaveBeenCalledWith("doc-1", "enter-tag", "private");
    });
  });

  it("shows error when trying to add empty tag", async () => {
    render(<UserTagEditor docId="doc-1" />);
    await waitFor(() => screen.getByText("No tags yet"));
    const input = screen.getByLabelText("New tag text");
    fireEvent.keyDown(input, { key: "Enter" });
    expect(screen.getByRole("alert")).toHaveTextContent(/must not be empty/i);
    expect(mockAddUserTag).not.toHaveBeenCalled();
  });

  it("shows error when addUserTag API fails", async () => {
    mockAddUserTag.mockRejectedValue(new Error("Tag already exists for this document"));
    render(<UserTagEditor docId="doc-1" />);
    await waitFor(() => screen.getByText("No tags yet"));

    const input = screen.getByLabelText("New tag text");
    fireEvent.change(input, { target: { value: "dup" } });
    fireEvent.click(screen.getByRole("button", { name: "Add tag" }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("Tag already exists");
    });
  });

  it("calls deleteUserTag when delete button clicked", async () => {
    mockListUserTags.mockResolvedValue({
      document_id: "doc-1",
      tags: [TAG_PRIVATE],
    });
    render(<UserTagEditor docId="doc-1" />);
    await waitFor(() => screen.getByText("my-private"));

    fireEvent.click(screen.getByRole("button", { name: /remove tag my-private/i }));
    await waitFor(() => {
      expect(mockDeleteUserTag).toHaveBeenCalledWith("doc-1", "tag-1");
    });
  });
});
