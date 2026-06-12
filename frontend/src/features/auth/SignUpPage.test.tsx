import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { render } from "@/test/render";
import { SignUpPage } from "./SignUpPage";
import * as authApi from "@/api/auth";
import { ApiError } from "@/api/client";

vi.mock("@/api/auth");
vi.mock("@/components/brand/TomorrowlandLogo", () => ({
  TomorrowlandLogo: () => <svg data-testid="logo" />,
}));
vi.mock("@/components/settings/LanguageSelector", () => ({
  LanguageSelector: () => <div />,
}));

const mockNavigate = vi.fn();

vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => mockNavigate,
}));

beforeEach(() => {
  vi.clearAllMocks();
  mockNavigate.mockReset();
  vi.mocked(authApi.signUp).mockResolvedValue(undefined);
});

describe("SignUpPage — rendering", () => {
  it("renders the sign-up heading", () => {
    render(<SignUpPage />);
    expect(
      screen.getByRole("heading", { name: "Create an account" }),
    ).toBeInTheDocument();
  });

  it("renders email, display name, password and confirm-password fields", () => {
    render(<SignUpPage />);
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByLabelText("Display name")).toBeInTheDocument();
    expect(screen.getAllByLabelText("Password").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByLabelText("Confirm password")).toBeInTheDocument();
  });

  it("renders the create account button", () => {
    render(<SignUpPage />);
    expect(
      screen.getByRole("button", { name: "Sign up" }),
    ).toBeInTheDocument();
  });
});

describe("SignUpPage — validation", () => {
  it("shows email validation error for a malformed email", async () => {
    render(<SignUpPage />);
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "bad-email" },
    });
    const pwInputs = screen.getAllByLabelText("Password");
    fireEvent.change(pwInputs[0], { target: { value: "secret" } });
    fireEvent.change(screen.getByLabelText("Confirm password"), {
      target: { value: "secret" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign up" }));
    await waitFor(() => {
      expect(screen.getByText("Enter a valid email")).toBeInTheDocument();
    });
    expect(authApi.signUp).not.toHaveBeenCalled();
  });

  it("shows password-mismatch error when passwords differ", async () => {
    render(<SignUpPage />);
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "user@example.com" },
    });
    const pwInputs = screen.getAllByLabelText("Password");
    fireEvent.change(pwInputs[0], { target: { value: "secret1" } });
    fireEvent.change(screen.getByLabelText("Confirm password"), {
      target: { value: "secret2" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign up" }));
    await waitFor(() => {
      expect(screen.getByText("Passwords do not match")).toBeInTheDocument();
    });
    expect(authApi.signUp).not.toHaveBeenCalled();
  });

  it("shows password required error when password is blank", async () => {
    render(<SignUpPage />);
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "user@example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign up" }));
    // Both password and confirmPassword are blank, so the error appears on both.
    await waitFor(() => {
      expect(
        screen.getAllByText("Password is required").length,
      ).toBeGreaterThanOrEqual(1);
    });
  });
});

describe("SignUpPage — submit", () => {
  async function fillAndSubmit({
    email = "user@example.com",
    displayName = "",
    password = "secret123",
    confirmPassword = "secret123",
  } = {}) {
    render(<SignUpPage />);
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: email },
    });
    if (displayName) {
      fireEvent.change(screen.getByLabelText("Display name"), {
        target: { value: displayName },
      });
    }
    const pwInputs = screen.getAllByLabelText("Password");
    fireEvent.change(pwInputs[0], { target: { value: password } });
    fireEvent.change(screen.getByLabelText("Confirm password"), {
      target: { value: confirmPassword },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign up" }));
  }

  it("calls signUp() with the typed credentials on valid submit", async () => {
    await fillAndSubmit({ email: "new@example.com", password: "pass" , confirmPassword: "pass" });
    await waitFor(() => {
      expect(authApi.signUp).toHaveBeenCalledWith(
        "new@example.com",
        "pass",
        undefined,
      );
    });
  });

  it("passes display name to signUp() when provided", async () => {
    await fillAndSubmit({
      email: "new@example.com",
      displayName: "Alice",
      password: "pass",
      confirmPassword: "pass",
    });
    await waitFor(() => {
      expect(authApi.signUp).toHaveBeenCalledWith(
        "new@example.com",
        "pass",
        "Alice",
      );
    });
  });

  it("navigates to /search after successful sign-up", async () => {
    await fillAndSubmit();
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith({
        to: "/search",
        search: { q: "", mode: "hybrid" },
      });
    });
  });

  it("shows duplicate-email error on 409 response", async () => {
    vi.mocked(authApi.signUp).mockRejectedValueOnce(
      new ApiError(409, "Conflict"),
    );
    await fillAndSubmit();
    await waitFor(() => {
      expect(
        screen.getByText("An account with this email already exists"),
      ).toBeInTheDocument();
    });
  });

  it("shows generic error for other API failures", async () => {
    vi.mocked(authApi.signUp).mockRejectedValueOnce(
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
    vi.mocked(authApi.signUp).mockRejectedValueOnce(new Error("fetch failed"));
    await fillAndSubmit();
    await waitFor(() => {
      expect(
        screen.getByText("Something went wrong. Try again."),
      ).toBeInTheDocument();
    });
  });
});
