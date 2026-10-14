import { create } from 'zustand';

/**
 * Server-clock offset: serverNow ≈ Date.now() + offsetMs.
 *
 * Elapsed time is always derived from the server's authoritative timestamps (started_at, pauses)
 * and the *server's* notion of now, so a wrong phone clock never changes what the timer shows.
 * The offset is estimated from each timer response (NTP-style midpoint) and persisted with the
 * timer snapshot so it is available immediately after a cold start.
 */
interface ClockState {
  offsetMs: number;
  setOffset: (offsetMs: number) => void;
}

export const useServerClock = create<ClockState>()((set) => ({
  offsetMs: 0,
  setOffset: (offsetMs) => set({ offsetMs }),
}));

/** Offset from one request/response pair; the server stamped `serverTime` roughly mid-flight. */
export function estimateOffset(serverTimeIso: string, sentAt: number, receivedAt: number): number {
  const server = Date.parse(serverTimeIso);
  if (Number.isNaN(server)) return 0;
  return Math.round(server - (sentAt + receivedAt) / 2);
}

export function serverNow(deviceNow: number = Date.now()): number {
  return deviceNow + useServerClock.getState().offsetMs;
}
