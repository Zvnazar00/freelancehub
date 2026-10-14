import { localDateKey, startOfLocalDay } from '@/shared/lib/time';
import type { TimeEntry } from '@/shared/types/domain';

export interface DayGroup {
  key: string;
  date: Date;
  totalSeconds: number;
  entries: TimeEntry[];
}

/** Stopped entries grouped by the local day they started, newest day and entry first. */
export function groupStoppedByDay(entries: readonly TimeEntry[]): DayGroup[] {
  const groups = new Map<string, DayGroup>();
  for (const e of entries) {
    if (e.status !== 'stopped') continue;
    const started = new Date(e.startedAt);
    const key = localDateKey(started);
    const g = groups.get(key) ?? { key, date: startOfLocalDay(started), totalSeconds: 0, entries: [] };
    g.totalSeconds += e.durationSeconds ?? 0;
    g.entries.push(e);
    groups.set(key, g);
  }
  return [...groups.values()]
    .sort((a, b) => b.date.getTime() - a.date.getTime())
    .map((g) => ({ ...g, entries: [...g.entries].sort((a, b) => b.startedAt.localeCompare(a.startedAt)) }));
}
