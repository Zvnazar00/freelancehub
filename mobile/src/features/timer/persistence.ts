import AsyncStorage from '@react-native-async-storage/async-storage';

import { isActiveEntry, type ActiveTimeEntry, type TimeEntry } from '@/shared/types/domain';

/**
 * Last server-confirmed timer state, persisted so the timer is visible instantly after the app is
 * killed or reopened — before the network answers. It holds timestamps only (no counters), so the
 * elapsed time shown after a restart is exactly `serverNow - started_at - pauses`.
 *
 * Not a secret: it contains the entry (project name, description, timestamps) and the clock offset.
 * The server stays authoritative: the snapshot is replaced by GET /timer/current as soon as it returns.
 */
const KEY = 'freelancehub.timer.v1';
const VERSION = 1;

export interface TimerSnapshot {
  v: typeof VERSION;
  userId: string;
  entry: ActiveTimeEntry | null;
  offsetMs: number;
  savedAt: number;
}

export async function saveTimerSnapshot(userId: string, entry: TimeEntry | null, offsetMs: number, now = Date.now()) {
  const snapshot: TimerSnapshot = {
    v: VERSION,
    userId,
    entry: entry && isActiveEntry(entry) ? entry : null,
    offsetMs,
    savedAt: now,
  };
  try {
    await AsyncStorage.setItem(KEY, JSON.stringify(snapshot));
  } catch {
    // Best effort: the server still has the state.
  }
}

export async function loadTimerSnapshot(userId: string): Promise<TimerSnapshot | null> {
  try {
    const raw = await AsyncStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<TimerSnapshot>;
    if (parsed.v !== VERSION || parsed.userId !== userId || typeof parsed.offsetMs !== 'number') return null;
    const entry = parsed.entry ?? null;
    if (entry !== null && (typeof entry.startedAt !== 'string' || !Array.isArray(entry.pauses) || !isActiveEntry(entry))) {
      return null;
    }
    return { v: VERSION, userId, entry, offsetMs: parsed.offsetMs, savedAt: parsed.savedAt ?? 0 };
  } catch {
    return null;
  }
}

export async function clearTimerSnapshot(): Promise<void> {
  try {
    await AsyncStorage.removeItem(KEY);
  } catch {
    // ignore
  }
}
