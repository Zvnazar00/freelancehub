import { addDays, localDateKey } from '@/shared/lib/time';

/** Inclusive local-date range of the week containing `weekStartDate`. */
export function weekRange(weekStartDate: Date) {
  return { from: localDateKey(weekStartDate), to: localDateKey(addDays(weekStartDate, 6)) };
}
