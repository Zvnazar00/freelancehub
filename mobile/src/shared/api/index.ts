import { create } from 'zustand';

import { createApiClient } from './client';
import { API_BASE_URL } from './config';
import { createTokenStorage } from './tokens';

export { ApiError, errorMessageKey, isApiError } from './errors';
export { queryClient, queryKeys } from './queryClient';

type SessionListener = { onSession?: Parameters<typeof createApiClient>[0]['onSession']; onExpired?: () => void };
const listeners: SessionListener = {};

/** Registers auth-store callbacks (kept out of this module to avoid an import cycle). */
export function setSessionListeners(next: SessionListener): void {
  listeners.onSession = next.onSession;
  listeners.onExpired = next.onExpired;
}

export const tokenStorage = createTokenStorage();

/** Whether the last request reached the server (drives the offline banner). */
export const useReachability = create<{ reachable: boolean }>()(() => ({ reachable: true }));

/** The app-wide API client. Feature modules call `api.request(...)`; UI code never calls fetch directly. */
export const api = createApiClient({
  baseUrl: API_BASE_URL,
  tokens: tokenStorage,
  onSession: (pair) => listeners.onSession?.(pair),
  onSessionExpired: () => listeners.onExpired?.(),
  onReachability: (reachable) => {
    if (useReachability.getState().reachable !== reachable) useReachability.setState({ reachable });
  },
});

/** Fetches every page of a cursor-paginated list (bounded, for small per-user collections). */
export async function fetchAllPages<T>(
  path: string,
  query: Record<string, string | number | boolean | undefined> = {},
  signal?: AbortSignal,
  maxPages = 20,
): Promise<T[]> {
  const items: T[] = [];
  let cursor: string | null = null;
  for (let page = 0; page < maxPages; page++) {
    const res: { items: T[]; next_cursor: string | null } = await api.request(path, {
      query: { ...query, limit: 100, cursor: cursor ?? undefined },
      signal,
    });
    items.push(...res.items);
    cursor = res.next_cursor;
    if (!cursor) break;
  }
  return items;
}

export interface DownloadedFile {
  bytes: ArrayBuffer;
  filename: string;
  mimeType: string;
}

/** `attachment; filename="INV-2026-0001.pdf"` → `INV-2026-0001.pdf`. */
export function filenameFromDisposition(header: string | null, fallback: string): string {
  const match = header ? /filename="?([^";]+)"?/i.exec(header) : null;
  return match?.[1]?.trim() || fallback;
}

/** Authenticated binary download (PDF, CSV) through the same client: token refresh and typed errors included. */
export async function downloadFile(
  path: string,
  query: Record<string, string | undefined>,
  fallbackName: string,
): Promise<DownloadedFile> {
  const res = await api.requestWithMeta<ArrayBuffer>(path, { query, binary: true, timeoutMs: 60_000 });
  return {
    bytes: res.data,
    filename: filenameFromDisposition(res.headers.get('content-disposition'), fallbackName),
    mimeType: res.headers.get('content-type')?.split(';')[0] ?? 'application/octet-stream',
  };
}
