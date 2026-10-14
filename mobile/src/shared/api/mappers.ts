import {
  type Breakdown,
  type Client,
  type CurrencyCode,
  type CurrencyRate,
  type DashboardSummary,
  type Invoice,
  type InvoiceSummary,
  type MoneyAmount,
  type Project,
  type ProjectSummary,
  type Task,
  type TimeEntry,
  type Timeseries,
  type UserProfile,
} from '@/shared/types/domain';

import type {
  WireBreakdown,
  WireClient,
  WireCurrencyAmount,
  WireDashboard,
  WireInvoice,
  WireInvoiceSummary,
  WireProject,
  WireProjectSummary,
  WireTask,
  WireTimeEntry,
  WireTimeseries,
  WireUser,
} from './wire';

/**
 * The server only stores supported currencies (DB CHECK). An unknown code from a newer server is
 * passed through unchanged so the amount is still shown with its real code instead of a wrong one.
 */
function currency(code: string): CurrencyCode {
  return code as CurrencyCode;
}

const amounts = (list: WireCurrencyAmount[]): MoneyAmount[] =>
  list.map((a) => ({ currency: currency(a.currency), amount: a.amount }));

export function toUser(w: WireUser): UserProfile {
  return {
    id: w.id,
    email: w.email,
    fullName: w.full_name,
    timezone: w.timezone,
    defaultCurrency: currency(w.default_currency),
    defaultHourlyRate: w.default_hourly_rate,
    weekStart: w.week_start === 7 ? 7 : 1,
  };
}

export function toClient(w: WireClient): Client {
  return {
    id: w.id,
    name: w.name,
    email: w.email,
    company: w.company,
    notes: w.notes,
    defaultHourlyRate: w.default_hourly_rate,
    currency: currency(w.currency),
    archivedAt: w.archived_at,
    createdAt: w.created_at,
    stats: {
      activeProjects: w.stats.active_projects,
      trackedSeconds: w.stats.tracked_seconds,
      unbilled: amounts(w.stats.unbilled),
    },
  };
}

export function toProject(w: WireProject): Project {
  return {
    id: w.id,
    clientId: w.client.id,
    clientName: w.client.name,
    name: w.name,
    description: w.description,
    status: w.status,
    billingType: w.billing_type,
    hourlyRate: w.hourly_rate,
    fixedFee: w.fixed_fee,
    currency: currency(w.currency),
    budgetHours: w.budget_hours,
    deadline: w.deadline,
    color: w.color,
    archivedAt: w.archived_at,
    stats: {
      tasksTotal: w.stats.tasks_total,
      tasksDone: w.stats.tasks_done,
      trackedSeconds: w.stats.tracked_seconds,
      unbilled: amounts(w.stats.unbilled),
    },
  };
}

export function toTask(w: WireTask): Task {
  return {
    id: w.id,
    projectId: w.project_id,
    title: w.title,
    status: w.status,
    priority: w.priority,
    dueDate: w.due_date,
    estimateMinutes: w.estimate_minutes,
    position: w.position,
    completedAt: w.completed_at,
  };
}

export function toEntry(w: WireTimeEntry): TimeEntry {
  return {
    id: w.id,
    projectId: w.project.id,
    taskId: w.task?.id ?? null,
    project: w.project,
    task: w.task,
    description: w.description,
    source: w.source,
    status: w.status,
    startedAt: w.started_at,
    endedAt: w.ended_at,
    pauses: w.pauses.map((p) => ({ pausedAt: p.paused_at, resumedAt: p.resumed_at })),
    durationSeconds: w.duration_seconds,
    billable: w.billable,
    hourlyRate: w.hourly_rate,
    currency: currency(w.currency),
    rateSource: w.rate_source,
    billableAmount: w.billable_amount,
    invoiceId: w.invoice_id ?? null,
    version: w.version,
  };
}

const rates = (list: { currency: string; rate: string }[]): CurrencyRate[] =>
  list.map((r) => ({ currency: currency(r.currency), rate: r.rate }));

export function toInvoiceSummary(w: WireInvoiceSummary): InvoiceSummary {
  return {
    id: w.id,
    number: w.number,
    status: w.status,
    paymentStatus: w.payment_status,
    isOverdue: w.is_overdue,
    daysOverdue: w.days_overdue,
    client: w.client,
    issueDate: w.issue_date,
    dueDate: w.due_date,
    currency: currency(w.currency),
    subtotal: w.subtotal,
    taxRate: w.tax_rate,
    taxAmount: w.tax_amount,
    total: w.total,
    amountPaid: w.amount_paid,
    amountDue: w.amount_due,
    trackedSeconds: w.tracked_seconds,
    sentAt: w.sent_at,
    paidAt: w.paid_at,
    voidedAt: w.voided_at,
    version: w.version,
    createdAt: w.created_at,
  };
}

export function toInvoice(w: WireInvoice): Invoice {
  return {
    ...toInvoiceSummary(w),
    billTo: w.bill_to,
    fromName: w.from_name,
    notes: w.notes,
    items: w.items.map((i) => ({
      id: i.id,
      kind: i.kind,
      timeEntryId: i.time_entry_id,
      description: i.description,
      serviceDate: i.service_date,
      durationSeconds: i.duration_seconds,
      quantity: i.quantity,
      unitPrice: i.unit_price,
      amount: i.amount,
    })),
    payments: w.payments.map((p) => ({ id: p.id, amount: p.amount, paidOn: p.paid_on, method: p.method, note: p.note })),
  };
}

export function toDashboard(w: WireDashboard): DashboardSummary {
  return {
    range: w.range,
    previousRange: w.previous_range,
    trackedSeconds: w.tracked_seconds,
    billableSeconds: w.billable_seconds,
    previousTrackedSeconds: w.previous_tracked_seconds,
    entries: w.entries,
    flows: w.flows.map((f) => ({
      currency: currency(f.currency),
      tracked: f.tracked,
      previousTracked: f.previous_tracked,
      invoiced: f.invoiced,
      received: f.received,
      billableSeconds: f.billable_seconds,
      effectiveHourlyRate: f.effective_hourly_rate,
    })),
    balances: w.balances.map((b) => ({
      currency: currency(b.currency),
      unbilled: b.unbilled,
      outstanding: b.outstanding,
      overdue: b.overdue,
    })),
    invoices: w.invoices,
    topProjects: w.top_projects.map((p) => ({
      id: p.id,
      name: p.name,
      color: p.color,
      clientName: p.client_name,
      seconds: p.seconds,
      amounts: amounts(p.amounts),
    })),
  };
}

export function toTimeseries(w: WireTimeseries): Timeseries {
  return {
    range: w.range,
    interval: w.interval,
    points: w.points.map((p) => ({
      start: p.start,
      end: p.end,
      seconds: p.seconds,
      billableSeconds: p.billable_seconds,
      tracked: amounts(p.tracked),
      received: amounts(p.received),
    })),
  };
}

export function toBreakdown(w: WireBreakdown): Breakdown {
  return {
    range: w.range,
    groupBy: w.group_by,
    totalSeconds: w.total_seconds,
    rows: w.rows.map((r) => ({
      id: r.id,
      name: r.name,
      color: r.color,
      clientName: r.client_name,
      billingType: r.billing_type,
      seconds: r.seconds,
      billableSeconds: r.billable_seconds,
      share: r.share,
      amounts: amounts(r.amounts),
      effectiveHourlyRate: rates(r.effective_hourly_rate),
    })),
  };
}

export function toProjectSummary(w: WireProjectSummary): ProjectSummary {
  return {
    projectId: w.project_id,
    billingType: w.billing_type,
    currency: currency(w.currency),
    trackedSeconds: w.tracked_seconds,
    billableSeconds: w.billable_seconds,
    entries: w.entries,
    lastEntryAt: w.last_entry_at,
    budgetHours: w.budget_hours,
    budgetUsed: w.budget_used,
    fixedFee: w.fixed_fee,
    currentRate: { rate: w.current_rate.rate, currency: currency(w.current_rate.currency), source: w.current_rate.source },
    effectiveHourlyRate: rates(w.effective_hourly_rate),
    money: w.money.map((m) => ({
      currency: currency(m.currency),
      tracked: m.tracked,
      unbilled: m.unbilled,
      invoiced: m.invoiced,
    })),
    byTask: w.by_task.map((t) => ({ taskId: t.task_id, title: t.title, seconds: t.seconds, amounts: amounts(t.amounts) })),
    last30DaysSeconds: w.last_30_days_seconds,
  };
}
