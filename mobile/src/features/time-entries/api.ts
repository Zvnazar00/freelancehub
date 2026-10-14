import { useQuery } from '@tanstack/react-query';

import { api, queryKeys } from '@/shared/api';
import { toEntry } from '@/shared/api/mappers';
import type { WireEntryPage } from '@/shared/api/wire';
import type { CurrencyCode, DecimalString, TimeEntry } from '@/shared/types/domain';

export interface EntryFilter {
  /** Local dates (user time zone on the server), inclusive. */
  from?: string;
  to?: string;
  projectId?: string;
  clientId?: string;
  billable?: boolean;
}

export interface CurrencySummary {
  currency: CurrencyCode;
  seconds: number;
  billableSeconds: number;
  amount: DecimalString;
}

export interface EntryRange {
  entries: TimeEntry[];
  /** Totals of stopped entries over the whole range, per currency (server-computed, Decimal). */
  summary: CurrencySummary[];
  /** Stopped seconds per local day. */
  days: Map<string, number>;
  /** True when the range had more entries than were loaded. Totals above are still complete. */
  truncated: boolean;
}

function wireQuery(f: EntryFilter) {
  return { from: f.from, to: f.to, project_id: f.projectId, client_id: f.clientId, billable: f.billable };
}

function mapSummary(page: WireEntryPage): CurrencySummary[] {
  return page.summary.map((s) => ({
    currency: s.currency as CurrencyCode,
    seconds: s.seconds,
    billableSeconds: s.billable_seconds,
    amount: s.amount,
  }));
}

/** Entries of a (short) range with server totals. Loads up to `maxPages` × 100 entries. */
export async function fetchEntryRange(filter: EntryFilter, signal?: AbortSignal, maxPages = 5): Promise<EntryRange> {
  const entries: TimeEntry[] = [];
  let cursor: string | null = null;
  let first: WireEntryPage | null = null;
  for (let i = 0; i < maxPages; i++) {
    const page: WireEntryPage = await api.request<WireEntryPage>('/time-entries', {
      query: { ...wireQuery(filter), limit: 100, cursor: cursor ?? undefined },
      signal,
    });
    first ??= page;
    entries.push(...page.items.map(toEntry));
    cursor = page.next_cursor;
    if (!cursor) break;
  }
  return {
    entries,
    summary: first ? mapSummary(first) : [],
    days: new Map((first?.days ?? []).map((d) => [d.date, d.seconds])),
    truncated: cursor !== null,
  };
}

export function useEntryRange(filter: EntryFilter, enabled = true) {
  return useQuery({
    queryKey: queryKeys.entries.range({ ...wireQuery(filter) }),
    queryFn: ({ signal }) => fetchEntryRange(filter, signal),
    enabled,
  });
}

/** Only the totals of a filter (one tiny page). */
export function useEntrySummary(filter: EntryFilter, enabled = true) {
  return useQuery({
    queryKey: queryKeys.entries.summary({ ...wireQuery(filter) }),
    enabled,
    queryFn: async ({ signal }) => {
      const page = await api.request<WireEntryPage>('/time-entries', { query: { ...wireQuery(filter), limit: 1 }, signal });
      return mapSummary(page);
    },
  });
}

/** Recent entries of a filter (newest first). */
export function useRecentEntries(filter: EntryFilter, limit = 5) {
  return useQuery({
    queryKey: queryKeys.entries.range({ ...wireQuery(filter), limit }),
    queryFn: async ({ signal }) => {
      const page = await api.request<WireEntryPage>('/time-entries', { query: { ...wireQuery(filter), limit }, signal });
      return page.items.map(toEntry).filter((e) => e.status === 'stopped');
    },
  });
}
