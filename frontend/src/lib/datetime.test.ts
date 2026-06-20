import { describe, expect, it } from "vitest";
import { DATE_PLACEHOLDER, formatDate, formatDateTime } from "./datetime";

describe("formatDate", () => {
  it("formats a valid ISO string", () => {
    expect(formatDate("2026-06-20T12:00:00Z")).not.toBe(DATE_PLACEHOLDER);
    expect(formatDate("2026-06-20T12:00:00Z")).toMatch(/2026/);
  });

  it("returns the placeholder for null, undefined, and empty", () => {
    expect(formatDate(null)).toBe(DATE_PLACEHOLDER);
    expect(formatDate(undefined)).toBe(DATE_PLACEHOLDER);
    expect(formatDate("")).toBe(DATE_PLACEHOLDER);
  });

  it("returns the placeholder for an unparseable date instead of 'Invalid Date'", () => {
    expect(formatDate("not-a-date")).toBe(DATE_PLACEHOLDER);
  });
});

describe("formatDateTime", () => {
  it("formats a valid date", () => {
    expect(formatDateTime("2026-06-20T12:00:00Z")).toMatch(/2026/);
  });

  it("returns the placeholder for invalid input", () => {
    expect(formatDateTime(undefined)).toBe(DATE_PLACEHOLDER);
    expect(formatDateTime("garbage")).toBe(DATE_PLACEHOLDER);
  });
});
