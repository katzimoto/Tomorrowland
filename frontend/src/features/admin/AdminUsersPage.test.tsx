import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { render } from "@/test/render";
import { AdminUsersPage } from "./AdminUsersPage";
import * as adminApiModule from "@/api/admin";

const navigate = vi.fn();
vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => navigate,
  Link: ({ children, to }: { children: React.ReactNode; to: string }) => (
    <a href={to}>{children}</a>
  ),
}));

vi.mock("@/api/admin", () => ({
  adminApi: {
    listUsers: vi.fn(),
    listGroups: vi.fn(),
  },
}));

const mockUsers = [
  {
    id: "u1",
    email: "alice@example.com",
    display_name: "Alice",
    auth_source: "local",
    is_admin: true,
    created_at: "2025-01-01T00:00:00Z",
    groups: [],
  },
  {
    id: "u2",
    email: "bob@example.com",
    display_name: null,
    auth_source: "ldap",
    is_admin: false,
    created_at: "2025-06-01T00:00:00Z",
    groups: [],
  },
];

const adminApi = vi.mocked(adminApiModule.adminApi);

beforeEach(() => {
  vi.clearAllMocks();
  adminApi.listUsers.mockResolvedValue(mockUsers);
  adminApi.listGroups.mockResolvedValue([]);
});

describe("AdminUsersPage", () => {
  it("renders the heading", async () => {
    render(<AdminUsersPage />);
    expect(await screen.findByText("Users")).toBeInTheDocument();
  });

  it("renders user rows", async () => {
    render(<AdminUsersPage />);
    expect(await screen.findByText("alice@example.com")).toBeInTheDocument();
    expect(screen.getByText("bob@example.com")).toBeInTheDocument();
  });

  it("renders display names", async () => {
    render(<AdminUsersPage />);
    expect(await screen.findByText("Alice")).toBeInTheDocument();
  });

  it("shows admin icon for admin users", async () => {
    render(<AdminUsersPage />);
    expect(await screen.findByText("alice@example.com")).toBeInTheDocument();
  });

  it("shows auth source", async () => {
    render(<AdminUsersPage />);
    expect(await screen.findByText("ldap")).toBeInTheDocument();
  });

  it("navigates to user detail on click", async () => {
    render(<AdminUsersPage />);
    const link = await screen.findByText("alice@example.com");
    await userEvent.click(link);
    expect(navigate).toHaveBeenCalledWith({
      to: "/admin/users/$userId",
      params: { userId: "u1" },
    });
  });
});
