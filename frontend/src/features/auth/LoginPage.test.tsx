import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { render } from "@/test/render";
import { LoginPage } from "./LoginPage";
import * as authApi from "@/api/auth";
import { ApiError } from "@/api/client";

vi.mock("@/api/auth");
vi.mock("@/lib/performanceTelemetry", () => ({
  startNamedPerformanceTimer: vi.fn(),
}));
vi.mock("@/components/brand/TomorrowlandLogo", () => ({
  TomorrowlandLogo: () => <svg data-testid="logo" />,
}));
vi.mock("@/components/settings/LanguageSelector", () => ({
  LanguageSelector: () => <div />,
}));

const mockNavigate = vi.fn();
let mockSearchParams: Record<string, unknown> = {};

vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => mockNavigate,
  useSearch: () => mockSearchParams,
}));

beforeEach(() => {
  vi.clearAllMocks();
  mockSearchParams = {};
  mockNavigate.mockReset();
  vi.mocked(authApi.login).mockResolvedValue(undefined);
});

describe("LoginPage — rendering", () => {
  it("renders the sign-in heading", () => {
    render(<LoginPage />);
    expect(
      screen.getByRole("heading", { name: "Sign in to Tomorrowland" }),
    ).toBeInTheDocument();
  });

  it("renders email and password inputs", () => {
    render(<LoginPage />);
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByLabelText("Password")).toBeInTheDocument();
  });

  it("renders the sign-in button", () => {
    render(<LoginPage />);
    expect(
      screen.getByRole("button", { name: "Sign in" }),
    ).toBeInTheDocument();
  });

  it("shows session-expired banner when expired param is truthy", () => {
    mockSearchParams = { expired: "1" };
    render(<LoginPage />);
    expect(
      screen.getByText("Your session expired. Sign in again."),
    ).toBeInTheDocument();
  });

  it("does not show session-expired banner by default", () => {
    render(<LoginPage />);
    expect(
      screen.queryByText("Your session expired. Sign in again."),
    ).not.toBeInTheDocument();
  });
});

describe("LoginPage — validation", () => {
  it("shows email validation error when email is blank on submit", async () => {
    render(<LoginPage />);
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "secret" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => {
      expect(screen.getByText("Enter a valid email")).toBeInTheDocument();
    });
    expect(authApi.login).not.toHaveBeenCalled();
  });

  it("shows email validation error for a malformed email", async () => {
    render(<LoginPage />);
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "not-an-email" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "secret" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => {
      expect(screen.getByText("Enter a valid email")).toBeInTheDocument();
    });
  });

  it("shows password validation error when password is blank on submit", async () => {
    render(<LoginPage />);
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "user@example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    await waitFor(() => {
      expect(screen.getByText("Password is required")).toBeInTheDocument();
    });
    expect(authApi.login).not.toHaveBeenCalled();
  });
});

describe("LoginPage — submit", () => {
  async function fillAndSubmit(
    email = "user@example.com",
    password = "password123",
  ) {
    render(<LoginPage />);
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: email },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: password },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  }

  it("calls login() with the typed credentials on valid submit", async () => {
    await fillAndSubmit();
    await waitFor(() => {
      expect(authApi.login).toHaveBeenCalledWith(
        "user@example.com",
        "password123",
      );
    });
  });

  it("navigates to /search after successful login", async () => {
    await fillAndSubmit();
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith({ to: "/search" });
    });
  });

  it("navigates to the returnTo URL when provided", async () => {
    mockSearchParams = { return: "/documents" };
    await fillAndSubmit();
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith({ to: "/documents" });
    });
  });

  it("ignores a returnTo URL that does not start with /", async () => {
    mockSearchParams = { return: "https://evil.com/steal" };
    await fillAndSubmit();
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith({ to: "/search" });
    });
  });

  it("shows bad-credentials error on 401 response", async () => {
    vi.mocked(authApi.login).mockRejectedValueOnce(
      new ApiError(401, "Unauthorized"),
    );
    await fillAndSubmit();
    await waitFor(() => {
      expect(
        screen.getByText("Email or password is incorrect."),
      ).toBeInTheDocument();
    });
  });

  it("shows generic error for non-401 API failures", async () => {
    vi.mocked(authApi.login).mockRejectedValueOnce(
      new ApiError(500, "Internal Server Error"),
    );
    await fillAndSubmit();
    await waitFor(() => {
      expect(
        screen.getByText("Something went wrong. Try again."),
      ).toBeInTheDocument();
    });
  });

  it("shows generic error for network errors", async () => {
    vi.mocked(authApi.login).mockRejectedValueOnce(new Error("fetch failed"));
    await fillAndSubmit();
    await waitFor(() => {
      expect(
        screen.getByText("Something went wrong. Try again."),
      ).toBeInTheDocument();
    });
  });
});
