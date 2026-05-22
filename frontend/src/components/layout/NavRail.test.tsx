import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@/test/render";
import { NavRail } from "./NavRail";
import { logout } from "@/api/auth";

const mockNavigate = vi.fn();

vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => vi.fn(),
  useRouter: () => ({ navigate: mockNavigate }),
  Link: ({ children, to, ...rest }: { children: React.ReactNode; to: string }) => (
    <a href={to} {...rest}>{children}</a>
  ),
}));

vi.mock("@/api/auth", () => ({
  logout: vi.fn(),
}));

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  sessionStorage.clear();
});

describe("NavRail", () => {
  it("renders navigation items", () => {
    render(<NavRail isAdmin={false} />);
    expect(screen.getByText("Search")).toBeInTheDocument();
    expect(screen.getByText("Chat")).toBeInTheDocument();
  });

  it("renders admin item when isAdmin is true", () => {
    render(<NavRail isAdmin={true} />);
    expect(screen.getByText("Admin")).toBeInTheDocument();
  });

  it("renders user info when userDisplayName is provided", () => {
    render(<NavRail isAdmin={false} userDisplayName="Alice" userEmail="alice@example.com" />);
    expect(screen.getByText("Alice")).toBeInTheDocument();
  });

  it("renders sign-out button", () => {
    render(<NavRail isAdmin={false} />);
    expect(screen.getByRole("button", { name: /sign out/i })).toBeInTheDocument();
  });

  it("calls logout and navigates to login on sign-out click", async () => {
    render(<NavRail isAdmin={false} />);
    const btn = screen.getByRole("button", { name: /sign out/i });
    fireEvent.click(btn);
    expect(logout).toHaveBeenCalledTimes(1);
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith({ to: "/login" });
    });
  });

  it("disables sign-out button while signing out", async () => {
    render(<NavRail isAdmin={false} />);
    const btn = screen.getByRole("button", { name: /sign out/i });
    fireEvent.click(btn);
    expect(btn).toBeDisabled();
  });
});
