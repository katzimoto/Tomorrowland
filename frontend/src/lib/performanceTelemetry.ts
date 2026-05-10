export type PerformanceTelemetryEventName =
  | "login.shell"
  | "navigation.route"
  | "search.request"
  | "search.firstResult"
  | "preview.load"
  | "qa.answer"
  | "sourceSync.action";

type TelemetryStatus = "success" | "error";

export interface PerformanceTelemetryEvent {
  name: PerformanceTelemetryEventName;
  durationMs: number;
  at: number;
  status: TelemetryStatus;
}

interface TelemetryDiagnostics {
  enableConsole(): void;
  disableConsole(): void;
  clear(): void;
  events(): PerformanceTelemetryEvent[];
  isConsoleEnabled(): boolean;
}

declare global {
  interface Window {
    neverlandTelemetry?: TelemetryDiagnostics;
  }
}

const MAX_EVENTS = 200;
const DEBUG_STORAGE_KEY = "neverland_perf_debug";
const events: PerformanceTelemetryEvent[] = [];
const namedTimers = new Map<string, number>();
let consoleEnabled = readInitialDebugFlag();

function now(): number {
  return typeof performance !== "undefined" &&
    typeof performance.now === "function"
    ? performance.now()
    : Date.now();
}

function readInitialDebugFlag(): boolean {
  if (typeof window === "undefined") return false;
  try {
    const params = new URLSearchParams(window.location.search);
    if (params.get("perf") === "1") {
      window.localStorage?.setItem(DEBUG_STORAGE_KEY, "1");
      return true;
    }
    return window.localStorage?.getItem(DEBUG_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

function mark(name: string): void {
  if (
    typeof performance !== "undefined" &&
    typeof performance.mark === "function"
  ) {
    performance.mark(name);
  }
}

function measure(name: string, startMark: string, endMark: string): void {
  if (
    typeof performance === "undefined" ||
    typeof performance.measure !== "function"
  )
    return;
  try {
    performance.measure(name, startMark, endMark);
  } catch {
    // Ignore User Timing API failures; in-memory telemetry is authoritative for validation.
  }
}

function persistConsoleFlag(enabled: boolean): void {
  if (typeof window === "undefined") return;
  try {
    if (enabled) window.localStorage?.setItem(DEBUG_STORAGE_KEY, "1");
    else window.localStorage?.removeItem(DEBUG_STORAGE_KEY);
  } catch {
    // Ignore storage failures; callers can still inspect the in-memory buffer.
  }
}

export function recordPerformanceEvent(
  name: PerformanceTelemetryEventName,
  durationMs: number,
  status: TelemetryStatus = "success",
): PerformanceTelemetryEvent {
  const event: PerformanceTelemetryEvent = {
    name,
    durationMs: Math.max(0, Math.round(durationMs)),
    at: Math.round(Date.now()),
    status,
  };
  events.push(event);
  if (events.length > MAX_EVENTS) events.splice(0, events.length - MAX_EVENTS);

  if (consoleEnabled) {
    // Low-cardinality event names, numeric duration, and coarse status only.
    console.info("[neverland:perf]", event);
  }
  return event;
}

export function startPerformanceTimer(): () => number {
  const start = now();
  return () => now() - start;
}

export function startNamedPerformanceTimer(name: string): void {
  namedTimers.set(name, now());
  mark(`neverland:${name}:start`);
}

export function finishNamedPerformanceTimer(
  timerName: string,
  eventName: PerformanceTelemetryEventName,
  status: TelemetryStatus = "success",
): PerformanceTelemetryEvent | null {
  const start = namedTimers.get(timerName);
  if (start === undefined) return null;
  namedTimers.delete(timerName);
  const endMark = `neverland:${timerName}:end`;
  mark(endMark);
  measure(`neverland:${eventName}`, `neverland:${timerName}:start`, endMark);
  return recordPerformanceEvent(eventName, now() - start, status);
}

export async function measurePerformance<T>(
  name: PerformanceTelemetryEventName,
  fn: () => Promise<T>,
): Promise<T> {
  const timer = startPerformanceTimer();
  const markId = `${name}:${Date.now()}:${Math.random().toString(36).slice(2)}`;
  mark(`neverland:${markId}:start`);
  try {
    const result = await fn();
    mark(`neverland:${markId}:end`);
    measure(
      `neverland:${name}`,
      `neverland:${markId}:start`,
      `neverland:${markId}:end`,
    );
    recordPerformanceEvent(name, timer(), "success");
    return result;
  } catch (error) {
    mark(`neverland:${markId}:end`);
    measure(
      `neverland:${name}`,
      `neverland:${markId}:start`,
      `neverland:${markId}:end`,
    );
    recordPerformanceEvent(name, timer(), "error");
    throw error;
  }
}

export function getPerformanceTelemetryEvents(): PerformanceTelemetryEvent[] {
  return [...events];
}

export function clearPerformanceTelemetryEvents(): void {
  events.length = 0;
  namedTimers.clear();
}

export function setPerformanceTelemetryConsoleEnabled(enabled: boolean): void {
  consoleEnabled = enabled;
  persistConsoleFlag(enabled);
}

export function isPerformanceTelemetryConsoleEnabled(): boolean {
  return consoleEnabled;
}

export function installPerformanceTelemetryDiagnostics(): void {
  if (typeof window === "undefined") return;
  window.neverlandTelemetry = {
    enableConsole: () => setPerformanceTelemetryConsoleEnabled(true),
    disableConsole: () => setPerformanceTelemetryConsoleEnabled(false),
    clear: clearPerformanceTelemetryEvents,
    events: getPerformanceTelemetryEvents,
    isConsoleEnabled: isPerformanceTelemetryConsoleEnabled,
  };
}
