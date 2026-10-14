/**
 * Domain types mirroring the API contracts in docs/api.md (camelCase on the client).
 * Money is always a decimal string with 2 fraction digits ("127.50") plus an explicit currency.
 */
export const SUPPORTED_CURRENCIES = ['USD', 'EUR', 'GBP', 'CAD', 'AUD', 'CHF', 'PLN', 'UAH'] as const;
export type CurrencyCode = (typeof SUPPORTED_CURRENCIES)[number];

/** Decimal string with up to 2 fraction digits, e.g. "85.00". */
export type DecimalString = string;
/** ISO-8601 timestamp in UTC, e.g. "2026-10-11T08:00:00.000Z". */
export type IsoDateTime = string;
/** Calendar date, e.g. "2026-12-01". */
export type IsoDate = string;

/** An amount in one currency. Totals are never summed across currencies. */
export interface MoneyAmount {
  currency: CurrencyCode;
  amount: DecimalString;
}

export interface UserProfile {
  id: string;
  email: string;
  fullName: string;
  timezone: string;
  defaultCurrency: CurrencyCode;
  defaultHourlyRate: DecimalString | null;
  weekStart: 1 | 7;
}

export interface Client {
  id: string;
  name: string;
  email: string | null;
  company: string | null;
  notes: string | null;
  defaultHourlyRate: DecimalString | null;
  currency: CurrencyCode;
  archivedAt: IsoDateTime | null;
  createdAt: IsoDateTime;
  stats: ClientStats;
}

export interface ClientStats {
  activeProjects: number;
  /** Net seconds of stopped entries. */
  trackedSeconds: number;
  /** Billable value of stopped entries that is not on a sent or paid invoice, per currency. */
  unbilled: MoneyAmount[];
}

export type ProjectStatus = 'active' | 'on_hold' | 'completed';
export type BillingType = 'hourly' | 'fixed' | 'non_billable';

export interface ProjectStats {
  tasksTotal: number;
  tasksDone: number;
  trackedSeconds: number;
  unbilled: MoneyAmount[];
}

export interface Project {
  id: string;
  clientId: string;
  clientName: string;
  name: string;
  description: string | null;
  status: ProjectStatus;
  billingType: BillingType;
  hourlyRate: DecimalString | null;
  fixedFee: DecimalString | null;
  currency: CurrencyCode;
  budgetHours: DecimalString | null;
  deadline: IsoDate | null;
  color: string;
  archivedAt: IsoDateTime | null;
  stats: ProjectStats;
}

export type TaskStatus = 'todo' | 'in_progress' | 'done';
export type TaskPriority = 'low' | 'medium' | 'high';

export interface Task {
  id: string;
  projectId: string;
  title: string;
  status: TaskStatus;
  priority: TaskPriority;
  dueDate: IsoDate | null;
  estimateMinutes: number | null;
  position: number;
  completedAt: IsoDateTime | null;
}

export type TimeEntryStatus = 'running' | 'paused' | 'stopped';
export type TimeEntrySource = 'timer' | 'manual';
export type RateSource = 'project' | 'client' | 'user' | 'none';

export interface TimeEntryPause {
  pausedAt: IsoDateTime;
  resumedAt: IsoDateTime | null;
}

export interface TimeEntry {
  id: string;
  projectId: string;
  taskId: string | null;
  /** Denormalised references returned by the API, so lists render without extra lookups. */
  project: { id: string; name: string; color: string };
  task: { id: string; title: string } | null;
  description: string;
  source: TimeEntrySource;
  status: TimeEntryStatus;
  startedAt: IsoDateTime;
  endedAt: IsoDateTime | null;
  pauses: TimeEntryPause[];
  /** Net of pauses. Set only when stopped. */
  durationSeconds: number | null;
  billable: boolean;
  /** Rate snapshot taken when the entry was created. */
  hourlyRate: DecimalString | null;
  currency: CurrencyCode;
  rateSource: RateSource;
  /** Set only when stopped; null when not billable or no rate. */
  billableAmount: DecimalString | null;
  /** Set while the entry is on an invoice (draft included). Such entries are locked server-side. */
  invoiceId?: string | null;
  version: number;
}

export type ActiveTimeEntry = TimeEntry & { status: 'running' | 'paused' };

export function isActiveEntry(entry: TimeEntry): entry is ActiveTimeEntry {
  return entry.status === 'running' || entry.status === 'paused';
}

// ---------- invoices ----------

/** Stored lifecycle. "Overdue" and "partially paid" are derived by the server (see InvoiceSummary). */
export type InvoiceStatus = 'draft' | 'sent' | 'paid' | 'void';
export type PaymentStatus = 'unpaid' | 'partial' | 'paid';
export type PaymentMethod = 'bank_transfer' | 'card' | 'cash' | 'paypal' | 'other';
export const PAYMENT_METHODS: readonly PaymentMethod[] = ['bank_transfer', 'card', 'cash', 'paypal', 'other'];

export interface InvoiceSummary {
  id: string;
  /** Assigned on send (INV-YYYY-NNNN); null for drafts. */
  number: string | null;
  status: InvoiceStatus;
  /** null for drafts and void invoices. */
  paymentStatus: PaymentStatus | null;
  isOverdue: boolean;
  daysOverdue: number;
  client: { id: string; name: string };
  issueDate: IsoDate;
  dueDate: IsoDate;
  currency: CurrencyCode;
  subtotal: DecimalString;
  taxRate: DecimalString;
  taxAmount: DecimalString;
  total: DecimalString;
  amountPaid: DecimalString;
  amountDue: DecimalString;
  trackedSeconds: number;
  sentAt: IsoDateTime | null;
  paidAt: IsoDateTime | null;
  voidedAt: IsoDateTime | null;
  version: number;
  createdAt: IsoDateTime;
}

export interface InvoiceItem {
  id: string;
  kind: 'time' | 'custom';
  timeEntryId: string | null;
  description: string;
  serviceDate: IsoDate | null;
  durationSeconds: number | null;
  /** Hours for time lines (4 dp, display only), quantity for custom lines. */
  quantity: string;
  unitPrice: DecimalString;
  amount: DecimalString;
}

export interface Payment {
  id: string;
  amount: DecimalString;
  paidOn: IsoDate;
  method: PaymentMethod;
  note: string | null;
}

export interface Invoice extends InvoiceSummary {
  billTo: { name: string; company: string | null; email: string | null };
  fromName: string | null;
  notes: string | null;
  items: InvoiceItem[];
  payments: Payment[];
}

// ---------- dashboard & analytics ----------

export interface DateRange {
  from: IsoDate;
  to: IsoDate;
}

/** What happened inside a period, per currency. */
export interface MoneyFlow {
  currency: CurrencyCode;
  /** Value of billable time tracked in the period — not money received. */
  tracked: DecimalString;
  previousTracked: DecimalString;
  /** Totals of invoices issued in the period. */
  invoiced: DecimalString;
  /** Payments recorded in the period. */
  received: DecimalString;
  billableSeconds: number;
  effectiveHourlyRate: DecimalString | null;
}

/** Balances as of now, per currency. */
export interface Balance {
  currency: CurrencyCode;
  unbilled: DecimalString;
  outstanding: DecimalString;
  overdue: DecimalString;
}

export interface DashboardSummary {
  range: DateRange;
  previousRange: DateRange;
  trackedSeconds: number;
  billableSeconds: number;
  previousTrackedSeconds: number;
  entries: number;
  flows: MoneyFlow[];
  balances: Balance[];
  invoices: { draft: number; open: number; overdue: number };
  topProjects: { id: string; name: string; color: string; clientName: string; seconds: number; amounts: MoneyAmount[] }[];
}

export interface SeriesPoint {
  start: IsoDate;
  end: IsoDate;
  seconds: number;
  billableSeconds: number;
  tracked: MoneyAmount[];
  received: MoneyAmount[];
}

export interface Timeseries {
  range: DateRange;
  interval: 'day' | 'week' | 'month';
  points: SeriesPoint[];
}

export interface CurrencyRate {
  currency: CurrencyCode;
  rate: DecimalString;
}

export interface BreakdownRow {
  id: string;
  name: string;
  color: string | null;
  clientName: string | null;
  billingType: BillingType | null;
  seconds: number;
  billableSeconds: number;
  share: number;
  amounts: MoneyAmount[];
  effectiveHourlyRate: CurrencyRate[];
}

export interface Breakdown {
  range: DateRange;
  groupBy: 'project' | 'client';
  totalSeconds: number;
  rows: BreakdownRow[];
}

export interface ProjectSummary {
  projectId: string;
  billingType: BillingType;
  currency: CurrencyCode;
  trackedSeconds: number;
  billableSeconds: number;
  entries: number;
  lastEntryAt: IsoDateTime | null;
  budgetHours: DecimalString | null;
  /** tracked hours / budget hours (may exceed 1). Display only. */
  budgetUsed: number | null;
  fixedFee: DecimalString | null;
  currentRate: { rate: DecimalString | null; currency: CurrencyCode; source: RateSource };
  effectiveHourlyRate: CurrencyRate[];
  money: { currency: CurrencyCode; tracked: DecimalString; unbilled: DecimalString; invoiced: DecimalString }[];
  byTask: { taskId: string | null; title: string | null; seconds: number; amounts: MoneyAmount[] }[];
  last30DaysSeconds: number;
}
