/**
 * Locale-aware date formatting that degrades gracefully.
 *
 * `new Date(value).toLocaleString()` renders the literal string "Invalid Date"
 * when `value` is null, undefined, empty, or unparseable. These helpers return
 * a neutral em dash placeholder instead, so the UI never surfaces the raw
 * "Invalid Date" text to users.
 */

export const DATE_PLACEHOLDER = "—";

type DateInput = string | number | Date | null | undefined;

function toValidDate(value: DateInput): Date | null {
  if (value === null || value === undefined || value === "") return null;
  const d = value instanceof Date ? value : new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** Format a value as a localized date (e.g. "Jun 20, 2026"), or "—" when invalid. */
export function formatDate(value: DateInput, options?: Intl.DateTimeFormatOptions): string {
  const d = toValidDate(value);
  return d ? d.toLocaleDateString(undefined, options) : DATE_PLACEHOLDER;
}

/** Format a value as a localized date+time, or "—" when invalid. */
export function formatDateTime(value: DateInput, options?: Intl.DateTimeFormatOptions): string {
  const d = toValidDate(value);
  return d ? d.toLocaleString(undefined, options) : DATE_PLACEHOLDER;
}
