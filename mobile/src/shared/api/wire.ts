/**
 * Wire types: the exact JSON shapes of the FastAPI backend (snake_case, docs/api.md).
 * They never leak into UI code — `mappers.ts` converts them to the camelCase domain types.
 */

export interface WireCurrencyAmount {
  currency: string;
  amount: string;
}

export interface WireUser {
  id: string;
  email: string;
  full_name: string;
  timezone: string;
  default_currency: string;
  default_hourly_rate: string | null;
  week_start: number;
  created_at: string;
  updated_at: string;
}

export interface WireTokenPair {
  access_token: string;
  token_type: string;
  expires_in: number;
  refresh_token: string;
  user: WireUser;
}

export interface WirePage<T> {
  items: T[];
  next_cursor: string | null;
}

export interface WireClient {
  id: string;
  name: string;
  email: string | null;
  company: string | null;
  notes: string | null;
  default_hourly_rate: string | null;
  currency: string;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
  stats: { active_projects: number; tracked_seconds: number; unbilled: WireCurrencyAmount[] };
}

export interface WireProject {
  id: string;
  client: { id: string; name: string };
  name: string;
  description: string | null;
  status: 'active' | 'on_hold' | 'completed';
  billing_type: 'hourly' | 'fixed' | 'non_billable';
  hourly_rate: string | null;
  fixed_fee: string | null;
  currency: string;
  budget_hours: string | null;
  deadline: string | null;
  color: string;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
  stats: { tasks_total: number; tasks_done: number; tracked_seconds: number; unbilled: WireCurrencyAmount[] };
}

export interface WireTask {
  id: string;
  project_id: string;
  title: string;
  description: string | null;
  status: 'todo' | 'in_progress' | 'done';
  priority: 'low' | 'medium' | 'high';
  due_date: string | null;
  estimate_minutes: number | null;
  position: number;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface WireTimeEntry {
  id: string;
  project: { id: string; name: string; color: string };
  task: { id: string; title: string } | null;
  description: string;
  source: 'timer' | 'manual';
  status: 'running' | 'paused' | 'stopped';
  started_at: string;
  ended_at: string | null;
  pauses: { paused_at: string; resumed_at: string | null }[];
  duration_seconds: number | null;
  elapsed_seconds: number;
  billable: boolean;
  hourly_rate: string | null;
  currency: string;
  rate_source: 'project' | 'client' | 'user' | 'none';
  rate_corrected_at: string | null;
  billable_amount: string | null;
  invoice_id?: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface WireTimerState {
  entry: WireTimeEntry | null;
  server_time: string;
}

export interface WireEntryPage extends WirePage<WireTimeEntry> {
  summary: { currency: string; seconds: number; billable_seconds: number; amount: string }[];
  days: { date: string; seconds: number; entries: number }[];
  server_time: string;
}

export interface WireProblem {
  type?: string;
  title?: string;
  status?: number;
  code?: string;
  detail?: string | null;
  errors?: { field?: string; loc?: (string | number)[]; msg?: string; message?: string; code?: string; type?: string }[] | null;
  context?: Record<string, unknown> | null;
  request_id?: string | null;
}

// ---------- invoices (docs/api.md §4.10) ----------

export type WireInvoiceStatus = 'draft' | 'sent' | 'paid' | 'void';
export type WirePaymentMethod = 'bank_transfer' | 'card' | 'cash' | 'paypal' | 'other';

export interface WireInvoiceSummary {
  id: string;
  number: string | null;
  status: WireInvoiceStatus;
  payment_status: 'unpaid' | 'partial' | 'paid' | null;
  is_overdue: boolean;
  days_overdue: number;
  client: { id: string; name: string };
  issue_date: string;
  due_date: string;
  currency: string;
  subtotal: string;
  tax_rate: string;
  tax_amount: string;
  total: string;
  amount_paid: string;
  amount_due: string;
  tracked_seconds: number;
  sent_at: string | null;
  paid_at: string | null;
  voided_at: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface WireInvoiceItem {
  id: string;
  kind: 'time' | 'custom';
  time_entry_id: string | null;
  description: string;
  service_date: string | null;
  duration_seconds: number | null;
  quantity: string;
  unit_price: string;
  amount: string;
}

export interface WirePayment {
  id: string;
  amount: string;
  paid_on: string;
  method: WirePaymentMethod;
  note: string | null;
  created_at: string;
}

export interface WireInvoice extends WireInvoiceSummary {
  bill_to: { name: string; company: string | null; email: string | null };
  from_name: string | null;
  from_email: string | null;
  notes: string | null;
  items: WireInvoiceItem[];
  payments: WirePayment[];
}

export interface WireBillableEntries {
  items: WireTimeEntry[];
  totals: { currency: string; entries: number; seconds: number; amount: string }[];
  truncated: boolean;
}

// ---------- dashboard & analytics (docs/api.md §4.8) ----------

export interface WireDateRange {
  from: string;
  to: string;
}

export interface WireDashboard {
  range: WireDateRange;
  previous_range: WireDateRange;
  tracked_seconds: number;
  billable_seconds: number;
  previous_tracked_seconds: number;
  entries: number;
  flows: {
    currency: string;
    tracked: string;
    previous_tracked: string;
    invoiced: string;
    received: string;
    billable_seconds: number;
    effective_hourly_rate: string | null;
  }[];
  balances: { currency: string; unbilled: string; outstanding: string; overdue: string }[];
  invoices: { draft: number; open: number; overdue: number };
  top_projects: {
    id: string;
    name: string;
    color: string;
    client_name: string;
    seconds: number;
    amounts: WireCurrencyAmount[];
  }[];
  server_time: string;
}

export interface WireTimeseries {
  range: WireDateRange;
  interval: 'day' | 'week' | 'month';
  points: {
    start: string;
    end: string;
    seconds: number;
    billable_seconds: number;
    tracked: WireCurrencyAmount[];
    received: WireCurrencyAmount[];
  }[];
}

export interface WireBreakdown {
  range: WireDateRange;
  group_by: 'project' | 'client';
  total_seconds: number;
  rows: {
    id: string;
    name: string;
    color: string | null;
    client_name: string | null;
    billing_type: 'hourly' | 'fixed' | 'non_billable' | null;
    seconds: number;
    billable_seconds: number;
    share: number;
    amounts: WireCurrencyAmount[];
    effective_hourly_rate: { currency: string; rate: string }[];
  }[];
}

export interface WireProjectSummary {
  project_id: string;
  billing_type: 'hourly' | 'fixed' | 'non_billable';
  currency: string;
  tracked_seconds: number;
  billable_seconds: number;
  entries: number;
  first_entry_at: string | null;
  last_entry_at: string | null;
  budget_hours: string | null;
  budget_used: number | null;
  fixed_fee: string | null;
  current_rate: { rate: string | null; currency: string; source: 'project' | 'client' | 'user' | 'none' };
  effective_hourly_rate: { currency: string; rate: string }[];
  money: { currency: string; tracked: string; unbilled: string; invoiced: string }[];
  by_task: { task_id: string | null; title: string | null; seconds: number; amounts: WireCurrencyAmount[] }[];
  last_30_days_seconds: number;
}
