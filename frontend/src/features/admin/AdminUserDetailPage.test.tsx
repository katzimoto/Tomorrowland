import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { render } from "@/test/render";
import { AdminUserDetailPage } from "./AdminUserDetailPage";
import * as adminApiModule from "@/api/admin";

const navigate = vi.fn();
vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => navigate,
  useParams: () => ({ userId: "u1" }),
}));

vi.mock("@/api/admin", () => ({
  adminApi: {
    getUser: vi.fn(),
    listGroups: vi.fn(),
    updateUser: vi.fn(),
    listUsers: vi.fn(),
    addUserToGroup: vi.fn(),
    removeUserFromGroup: vi.fn(),
  },
}));

const adminApi = vi.mocked(adminApiModule.adminApi);

const mockUser = {
  id: "u1",
  email: "alice@example.com",
  display_name: "Alice",
  auth_source: "local",
  is_admin: true,
  created_at: "2025-01-01T00:00:00Z",
  groups: [{ id: "g1", name: "admins" }],
};

const mockGroups = [
  { id: "g1", name: "admins" },
  { id: "g2", name: "analysts" },
];

beforeEach(() => {
  vi.clearAllMocks();
  adminApi.getUser.mockResolvedValue(mockUser);
  adminApi.listGroups.mockResolvedValue(mockGroups);
  adminApi.updateUser.mockResolvedValue(mockUser);
  adminApi.listUsers.mockResolvedValue([]);
  adminApi.addUserToGroup.mockResolvedValue({} as never);
  adminApi.removeUserFromGroup.mockResolvedValue(undefined as never);
});

describe("AdminUserDetailPage", () => {
  it("renders user email as heading", async () => {
    render(<AdminUserDetailPage />);
    expect(await screen.findByRole("heading", { name: "alice@example.com" })).toBeInTheDocument();
  });

  it("renders auth source", async () => {
    render(<AdminUserDetailPage />);
    expect(await screen.findByText("local")).toBeInTheDocument();
  });

  it("renders display name in edit field", async () => {
    render(<AdminUserDetailPage />);
    const input = await screen.findByDisplayValue("Alice");
    expect(input).toBeInTheDocument();
  });

  it("shows group memberships", async () => {
    render(<AdminUserDetailPage />);
    expect(await screen.findByText("admins")).toBeInTheDocument();
  });

  it("shows Save changes button when fields are dirty", async () => {
    render(<AdminUserDetailPage />);
    const input = await screen.findByDisplayValue("Alice");
    await userEvent.clear(input);
    await userEvent.type(input, "Alice Updated");
    expect(screen.getByText("Save changes")).toBeInTheDocument();
  });

  it("calls updateUser on save", async () => {
    render(<AdminUserDetailPage />);
    const input = await screen.findByDisplayValue("Alice");
    await userEvent.clear(input);
    await userEvent.type(input, "Alice Updated");
    await userEvent.click(screen.getByText("Save changes"));
    expect(adminApi.updateUser).toHaveBeenCalledWith("u1", { display_name: "Alice Updated" });
  });
});
