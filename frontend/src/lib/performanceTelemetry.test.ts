import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  clearPerformanceTelemetryEvents,
  getPerformanceTelemetryEvents,
  installPerformanceTelemetryDiagnostics,
  measurePerformance,
  recordPerformanceEvent,
  setPerformanceTelemetryConsoleEnabled,
  startNamedPerformanceTimer,
  finishNamedPerformanceTimer,
} from "./performanceTelemetry";

beforeEach(() => {
  clearPerformanceTelemetryEvents();
  setPerformanceTelemetryConsoleEnabled(false);
  window.localStorage.clear();
});

describe("performance telemetry", () => {
  it("records low-cardinality event names, numeric durations, and status only", () => {
    const event = recordPerformanceEvent("search.request", 12.4);

    expect(event).toEqual({
      name: "search.request",
      durationMs: 12,
      at: expect.any(Number),
      status: "success",
    });
    expect(Object.keys(event).sort()).toEqual([
      "at",
      "durationMs",
      "name",
      "status",
    ]);
  });

  it("does not expose search text, document identifiers, tokens, or backend errors", async () => {
    await expect(
      measurePerformance("preview.load", async () => {
        throw new Error("doc-123 token secret vendor risk backend detail");
      }),
    ).rejects.toThrow("doc-123 token secret vendor risk backend detail");

    const serialized = JSON.stringify(getPerformanceTelemetryEvents());
    expect(serialized).toContain("preview.load");
    expect(serialized).not.toContain("vendor risk");
    expect(serialized).not.toContain("doc-123");
    expect(serialized).not.toContain("token");
    expect(serialized).not.toContain("backend detail");
  });

  it("is quiet by default but exposes local diagnostics for inspection", () => {
    const info = vi.spyOn(console, "info").mockImplementation(() => undefined);

    installPerformanceTelemetryDiagnostics();
    recordPerformanceEvent("qa.answer", 4);
    expect(info).not.toHaveBeenCalled();

    window.tomorrowlandTelemetry?.enableConsole();
    recordPerformanceEvent("qa.answer", 5);

    expect(window.tomorrowlandTelemetry?.events()).toHaveLength(2);
    expect(info).toHaveBeenCalledTimes(1);
    expect(window.tomorrowlandTelemetry?.isConsoleEnabled()).toBe(true);
  });

  it("measures named login-to-shell timers without caller payloads", () => {
    startNamedPerformanceTimer("login.shell");
    const event = finishNamedPerformanceTimer("login.shell", "login.shell");

    expect(event?.name).toBe("login.shell");
    expect(event?.durationMs).toEqual(expect.any(Number));
    expect(getPerformanceTelemetryEvents()).toHaveLength(1);
  });
});
