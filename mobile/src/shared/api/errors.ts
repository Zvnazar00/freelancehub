import type { TxKey } from '@/shared/i18n';

import type { WireProblem } from './wire';

/** Client-side codes for failures that never reached (or never came back from) the server. */
export type ClientErrorCode = 'NETWORK_ERROR' | 'TIMEOUT' | 'BAD_RESPONSE' | 'SESSION_EXPIRED';

export interface FieldError {
  field: string;
  message: string;
  code: string;
}

/**
 * Every failed request becomes an ApiError: RFC 9457 problem+json from the server,
 * or a client-side code (status 0) for network failures and timeouts.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly detail: string | null;
  readonly fieldErrors: FieldError[];
  readonly requestId: string | null;
  readonly context: Record<string, unknown> | null;

  constructor(init: {
    status: number;
    code: string;
    detail?: string | null;
    fieldErrors?: FieldError[];
    requestId?: string | null;
    context?: Record<string, unknown> | null;
  }) {
    super(init.detail ?? init.code);
    this.name = 'ApiError';
    this.status = init.status;
    this.code = init.code;
    this.detail = init.detail ?? null;
    this.fieldErrors = init.fieldErrors ?? [];
    this.requestId = init.requestId ?? null;
    this.context = init.context ?? null;
  }

  /** True when the request may not have reached the server — safe to retry with the same Idempotency-Key. */
  get isTransient(): boolean {
    return this.status === 0 || this.status === 502 || this.status === 503 || this.status === 504;
  }

  static fromProblem(status: number, body: WireProblem | null, requestId: string | null): ApiError {
    const fieldErrors: FieldError[] = (body?.errors ?? []).flatMap((e) =>
      e.field ? [{ field: e.field, message: e.message ?? e.msg ?? '', code: e.code ?? e.type ?? 'invalid' }] : [],
    );
    return new ApiError({
      status,
      code: body?.code ?? (status >= 500 ? 'INTERNAL_ERROR' : 'HTTP_ERROR'),
      detail: body?.detail ?? body?.title ?? null,
      fieldErrors,
      requestId: body?.request_id ?? requestId,
      context: body?.context ?? null,
    });
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

/** Codes with a dedicated, translated message. Anything else falls back to a generic message. */
const KNOWN_CODES = [
  'NETWORK_ERROR',
  'TIMEOUT',
  'SESSION_EXPIRED',
  'INVALID_CREDENTIALS',
  'EMAIL_TAKEN',
  'RATE_LIMITED',
  'NAME_TAKEN',
  'NOT_FOUND',
  'VALIDATION_ERROR',
  'ACTIVE_TIMER_EXISTS',
  'INVALID_TRANSITION',
  'TIMESTAMP_OUT_OF_ORDER',
  'TIMESTAMP_IN_FUTURE',
  'TIME_OVERLAP',
  'PROJECT_ARCHIVED',
  'CLIENT_ARCHIVED',
  'RESOURCE_IN_USE',
  'VERSION_CONFLICT',
  'INTERNAL_ERROR',
  'ENTRY_LOCKED',
  'ENTRY_ALREADY_INVOICED',
  'INVALID_INVOICE_ENTRIES',
  'CURRENCY_MISMATCH',
  'INVOICE_EMPTY',
  'INVOICE_HAS_PAYMENTS',
  'INVOICE_ALREADY_PAID',
  'OVERPAYMENT',
] as const;
type KnownCode = (typeof KNOWN_CODES)[number];

function isKnown(code: string): code is KnownCode {
  return (KNOWN_CODES as readonly string[]).includes(code);
}

/** Where an error happened, for codes whose meaning depends on the resource (e.g. INVALID_TRANSITION). */
export type ErrorScope = 'timer' | 'invoice';

/** i18n key of a human message for any thrown value. Never exposes raw server text to the user. */
export function errorMessageKey(error: unknown, scope: ErrorScope = 'timer'): TxKey {
  if (isApiError(error)) {
    if (scope === 'invoice' && error.code === 'INVALID_TRANSITION') return 'errors.INVOICE_INVALID_TRANSITION';
    if (isKnown(error.code)) return `errors.${error.code}`;
    if (error.status >= 500) return 'errors.INTERNAL_ERROR';
  }
  return 'errors.UNKNOWN';
}
