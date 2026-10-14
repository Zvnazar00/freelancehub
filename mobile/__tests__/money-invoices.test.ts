import { draftEntryIds, draftPreview, entryCurrencies, extraLinesFrom, isExtraLineValid } from '@/features/invoices/draft';
import { daysBetween, duePresetsWith, dueDateFor, invoiceFormSchema, isIsoDate, normalizeTaxRate, paymentFormSchema, taxRateInput } from '@/features/invoices/schema';
import { allowedActions, displayStatus } from '@/features/invoices/status';
import { toEntry } from '@/shared/api/mappers';
import { diffCents, taxCents } from '@/shared/lib/money';

import { wireEntry } from '../test-utils/fakeApi';

describe('tax preview uses the server rule (half-up once on the subtotal)', () => {
  it.each([
    [10, '5', 1], // 0.10 × 5 % = 0.005 → 0.01 (banker's rounding would give 0.00)
    [12750, '7.5', 956], // 127.50 × 7.5 % = 9.5625 → 9.56
    [100000, '20', 20000],
    [3333, '0', 0],
    [1, '50', 1], // 0.005 → 0.01
    [99999, '100', 99999],
    [15593, '7.5', 1169], // 155.93 → 11.69475 → 11.69 (backend test vector)
  ])('%i cents at %s%% → %i cents', (subtotal, rate, expected) => {
    expect(taxCents(subtotal, rate)).toBe(expected);
  });

  it('rejects rates above 100 % and negative subtotals', () => {
    expect(() => taxCents(100, '100.01')).toThrow(RangeError);
    expect(() => taxCents(-1, '5')).toThrow(RangeError);
  });

  it('diffCents compares decimal strings exactly', () => {
    expect(diffCents('100.10', '99.99')).toBe(11);
    expect(diffCents('0.00', '0.01')).toBe(-1);
  });
});

const entry = (id: string, amount: string | null, seconds: number, currency = 'USD') =>
  toEntry(wireEntry({ id, status: 'stopped', ended_at: '2026-10-12T10:00:00Z', duration_seconds: seconds, billable_amount: amount, currency }));

describe('invoice draft preview', () => {
  const entries = [entry('a', '127.50', 5400), entry('b', '28.33', 1200), entry('c', '0.03', 1)];

  it('sums per-entry rounded amounts, then applies tax once', () => {
    const preview = draftPreview(entries, new Set(['a', 'b']), [], '7.5');
    expect(preview).toEqual({ count: 2, seconds: 6600, subtotal: '155.83', tax: '11.69', total: '167.52' });
  });

  it('adds valid extra lines and ignores invalid tax input', () => {
    const extras = [
      { key: '1', description: 'Fee', amount: '100' },
      { key: '2', description: 'Broken', amount: 'abc' },
    ];
    const preview = draftPreview(entries, new Set(['c']), extras, '1.234');
    expect(preview.subtotal).toBe('100.03');
    expect(preview.tax).toBe('0.00');
    expect(isExtraLineValid(extras[0]!)).toBe(true);
    expect(isExtraLineValid(extras[1]!)).toBe(false);
    expect(isExtraLineValid({ key: '3', description: ' ', amount: '5' })).toBe(false);
  });

  it("lists currencies with the client's currency first", () => {
    expect(entryCurrencies([entry('x', '1.00', 1, 'EUR'), entry('y', '1.00', 1, 'USD')], 'USD')).toEqual(['USD', 'EUR']);
    expect(entryCurrencies([entry('x', '1.00', 1, 'EUR')], 'USD')).toEqual(['EUR']);
  });
});

describe('invoice status and actions', () => {
  const base = { status: 'sent' as const, isOverdue: false, paymentStatus: 'unpaid' as const, amountPaid: '0.00' };

  it('derives one display status', () => {
    expect(displayStatus({ ...base, status: 'draft', paymentStatus: null })).toBe('draft');
    expect(displayStatus(base)).toBe('open');
    expect(displayStatus({ ...base, paymentStatus: 'partial' })).toBe('partial');
    expect(displayStatus({ ...base, paymentStatus: 'partial', isOverdue: true })).toBe('overdue');
    expect(displayStatus({ ...base, status: 'paid', paymentStatus: 'paid' })).toBe('paid');
    expect(displayStatus({ ...base, status: 'void', paymentStatus: null })).toBe('void');
  });

  it('mirrors the server lifecycle rules', () => {
    expect(allowedActions({ status: 'draft', amountPaid: '0.00' })).toMatchObject({ send: true, delete: true, recordPayment: false, void: false });
    expect(allowedActions({ status: 'sent', amountPaid: '0.00' })).toMatchObject({ send: false, recordPayment: true, void: true });
    expect(allowedActions({ status: 'sent', amountPaid: '10.00' })).toMatchObject({ void: false, deletePayment: true });
    expect(allowedActions({ status: 'paid', amountPaid: '10.00' })).toMatchObject({ recordPayment: false, void: false, deletePayment: true });
    expect(allowedActions({ status: 'void', amountPaid: '0.00' })).toMatchObject({ send: false, delete: false, recordPayment: false, void: false });
  });
});

describe('invoice and payment forms', () => {
  const today = new Date(2026, 9, 12);

  it('validates payments against the amount due and the date', () => {
    const schema = paymentFormSchema(2750, today);
    const ok = { amount: '27.50', paidOn: '2026-10-12', method: 'card', note: '' };
    expect(schema.safeParse(ok).success).toBe(true);
    const issues = (v: object) => schema.safeParse({ ...ok, ...v }).error?.issues.map((i) => i.message);
    expect(issues({ amount: '27.51' })).toEqual(['paymentForm.errors.amountTooHigh']);
    expect(issues({ amount: '0' })).toEqual(['paymentForm.errors.amountPositive']);
    expect(issues({ amount: '1.234' })).toEqual(['paymentForm.errors.amountFormat']);
    expect(issues({ paidOn: '2026-10-13' })).toEqual(['paymentForm.errors.dateFuture']);
    expect(issues({ paidOn: '2026-02-30' })).toEqual(['paymentForm.errors.dateFormat']);
  });

  it('validates the invoice details', () => {
    const ok = { issueDate: '2026-10-12', dueDays: 14, taxRate: '', notes: '' };
    expect(invoiceFormSchema.safeParse(ok).success).toBe(true);
    expect(invoiceFormSchema.safeParse({ ...ok, taxRate: '100.01' }).error?.issues[0]?.message).toBe('invoiceForm.errors.taxMax');
    expect(invoiceFormSchema.safeParse({ ...ok, taxRate: '7,5' }).error?.issues[0]?.message).toBe('invoiceForm.errors.taxFormat');
    expect(invoiceFormSchema.safeParse({ ...ok, issueDate: '12.10.2026' }).success).toBe(false);
  });

  it('computes due dates on the calendar and normalises tax rates', () => {
    expect(dueDateFor('2026-10-12', 14)).toBe('2026-10-26');
    expect(dueDateFor('2026-12-25', 7)).toBe('2027-01-01');
    expect(dueDateFor('2028-02-22', 7)).toBe('2028-02-29');
    expect(normalizeTaxRate('')).toBe('0.00');
    expect(normalizeTaxRate('7.5')).toBe('7.50');
    expect(normalizeTaxRate('20')).toBe('20.00');
    expect(isIsoDate('2026-02-29')).toBe(false);
    expect(isIsoDate('2028-02-29')).toBe(true);
  });
});

describe('draft editing helpers', () => {
  const item = (kind: 'time' | 'custom', extra: Record<string, unknown>) => ({
    id: String(Math.random()), kind, timeEntryId: null, description: 'x', serviceDate: null, durationSeconds: null,
    quantity: '1.0000', unitPrice: '1.00', amount: '1.00', ...extra,
  });

  it('restores the term in days, across DST and month ends', () => {
    expect(daysBetween('2026-10-10', '2026-11-09')).toBe(30); // spans the EU DST change on 25 Oct
    expect(daysBetween('2026-03-01', '2026-03-31')).toBe(30);
    expect(daysBetween('2026-10-12', '2026-10-12')).toBe(0);
    expect(duePresetsWith(14)).toEqual([7, 14, 30]);
    expect(duePresetsWith(21)).toEqual([7, 14, 21, 30]);
  });

  it('shows stored tax rates the way people type them', () => {
    expect(taxRateInput('7.50')).toBe('7.5');
    expect(taxRateInput('10.00')).toBe('10');
    expect(taxRateInput('100.00')).toBe('100');
    expect(taxRateInput('0.00')).toBe('');
    expect(normalizeTaxRate(taxRateInput('7.25'))).toBe('7.25'); // round trip
  });

  it('turns custom lines into editor lines without changing the total', () => {
    let n = 0;
    const items = [
      item('time', { timeEntryId: 'e-1', amount: '127.50' }),
      item('custom', { description: 'Setup', quantity: '2.0000', unitPrice: '25.00', amount: '50.00' }),
    ] as Parameters<typeof extraLinesFrom>[0];
    expect(extraLinesFrom(items, () => `k${++n}`)).toEqual([{ key: 'k1', description: 'Setup', amount: '50.00' }]);
    expect([...draftEntryIds(items)]).toEqual(['e-1']);
  });
});
