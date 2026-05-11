import { describe, test, expect, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { LanguageProvider } from "./LanguageProvider";
import { useLanguage, useT } from "./index";

// Helper component that exposes language context values
function LangDisplay() {
  const { language, setLanguage, t } = useLanguage();
  return (
    <div>
      <span data-testid="lang">{language}</span>
      <span data-testid="heading">{t.auth.heading}</span>
      <button onClick={() => setLanguage("he")}>switch-he</button>
      <button onClick={() => setLanguage("en")}>switch-en</button>
    </div>
  );
}

function TDisplay() {
  const t = useT();
  return <span data-testid="search-title">{t.search.title}</span>;
}

const storageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => { store[key] = value; },
    removeItem: (key: string) => { delete store[key]; },
    clear: () => { store = {}; },
  };
})();

beforeEach(() => {
  Object.defineProperty(window, "localStorage", { value: storageMock, writable: true });
  storageMock.clear();
  document.documentElement.lang = "";
  document.documentElement.dir = "";
});

afterEach(() => {
  document.documentElement.lang = "";
  document.documentElement.dir = "";
});

describe("LanguageProvider", () => {
  test("defaults to English", () => {
    render(
      <LanguageProvider>
        <LangDisplay />
      </LanguageProvider>,
    );
    expect(screen.getByTestId("lang").textContent).toBe("en");
    expect(screen.getByTestId("heading").textContent).toBe("Sign in to Tomorrowland");
  });

  test("sets lang=en and dir=ltr on mount with default", () => {
    render(
      <LanguageProvider>
        <LangDisplay />
      </LanguageProvider>,
    );
    expect(document.documentElement.lang).toBe("en");
    expect(document.documentElement.dir).toBe("ltr");
  });

  test("switches to Hebrew and updates document lang and dir", () => {
    render(
      <LanguageProvider>
        <LangDisplay />
      </LanguageProvider>,
    );
    fireEvent.click(screen.getByText("switch-he"));
    expect(screen.getByTestId("lang").textContent).toBe("he");
    expect(document.documentElement.lang).toBe("he");
    expect(document.documentElement.dir).toBe("rtl");
  });

  test("switches back to English and restores ltr", () => {
    render(
      <LanguageProvider>
        <LangDisplay />
      </LanguageProvider>,
    );
    fireEvent.click(screen.getByText("switch-he"));
    fireEvent.click(screen.getByText("switch-en"));
    expect(screen.getByTestId("lang").textContent).toBe("en");
    expect(document.documentElement.lang).toBe("en");
    expect(document.documentElement.dir).toBe("ltr");
  });

  test("Hebrew mode shows Hebrew heading text", () => {
    render(
      <LanguageProvider>
        <LangDisplay />
      </LanguageProvider>,
    );
    fireEvent.click(screen.getByText("switch-he"));
    expect(screen.getByTestId("heading").textContent).toBe("התחברות ל-Tomorrowland");
  });

  test("persists language choice to localStorage", () => {
    render(
      <LanguageProvider>
        <LangDisplay />
      </LanguageProvider>,
    );
    fireEvent.click(screen.getByText("switch-he"));
    expect(storageMock.getItem("tomorrowland_lang")).toBe("he");
  });

  test("reads persisted language from localStorage on mount", () => {
    storageMock.setItem("tomorrowland_lang", "he");
    render(
      <LanguageProvider>
        <LangDisplay />
      </LanguageProvider>,
    );
    expect(screen.getByTestId("lang").textContent).toBe("he");
    expect(document.documentElement.lang).toBe("he");
    expect(document.documentElement.dir).toBe("rtl");
  });

  test("useT returns English translations by default", () => {
    render(
      <LanguageProvider>
        <TDisplay />
      </LanguageProvider>,
    );
    expect(screen.getByTestId("search-title").textContent).toBe("Search");
  });

  test("useT returns Hebrew translations after switch", () => {
    render(
      <LanguageProvider>
        <LangDisplay />
        <TDisplay />
      </LanguageProvider>,
    );
    fireEvent.click(screen.getByText("switch-he"));
    expect(screen.getByTestId("search-title").textContent).toBe("חיפוש");
  });
});
