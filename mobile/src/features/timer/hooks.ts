import { useNow } from '@/shared/hooks/useNow';
import type { ActiveTimeEntry } from '@/shared/types/domain';

import { useTimerQuery } from './api';
import { useServerClock } from './clock';
import { elapsedSeconds, pausedAtMs } from './model';

export interface ActiveTimerView {
  entry: ActiveTimeEntry;
  /** Net elapsed seconds, derived from server timestamps and the server clock — never a counter. */
  seconds: number;
}

/** Live view of the active timer: re-renders every second while running; survives backgrounding. */
export function useActiveTimer(): ActiveTimerView | null {
  const { data } = useTimerQuery();
  const entry = data?.entry ?? null;
  const offset = useServerClock((s) => s.offsetMs);
  const now = useNow(entry?.status === 'running');
  if (!entry) return null;
  return { entry, seconds: elapsedSeconds(entry, pausedAtMs(entry) ?? now + offset) };
}
