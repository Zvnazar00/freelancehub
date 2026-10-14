import { QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, renderRouter, screen, waitFor, within } from 'expo-router/testing-library';

import DashboardScreen from '@/app/(tabs)/index';
import InvoiceDetailScreen from '@/app/invoices/[id]';
import EditInvoiceScreen from '@/app/invoices/edit/[id]';
import NewInvoiceScreen from '@/app/invoices/new';
import { useAuth } from '@/features/auth/store';
import { queryClient, tokenStorage } from '@/shared/api';
import { toUser } from '@/shared/api/mappers';
import type { WireInvoice } from '@/shared/api/wire';

import { createFakeApi, problem, wireEntry, wireUser } from '../test-utils/fakeApi';

const today = new Date();
const iso = (date: Date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;

function wireInvoice(overrides: Partial<WireInvoice> = {}): WireInvoice {
  return {
    id: 'inv-1',
    number: 'INV-2026-0001',
    status: 'sent',
    payment_status: 'unpaid',
    is_overdue: false,
    days_overdue: 0,
    client: { id: 'c-1', name: 'Acme' },
    issue_date: iso(today),
    due_date: iso(today),
    currency: 'USD',
    subtotal: '127.50',
    tax_rate: '0.00',
    tax_amount: '0.00',
    total: '127.50',
    amount_paid: '0.00',
    amount_due: '127.50',
    tracked_seconds: 5400,
    sent_at: '2026-10-12T10:00:00Z',
    paid_at: null,
    voided_at: null,
    version: 2,
    created_at: '2026-10-12T10:00:00Z',
    updated_at: '2026-10-12T10:00:00Z',
    bill_to: { name: 'Acme', company: null, email: null },
    from_name: 'Alex Morgan',
    from_email: 'alex@example.com',
    notes: null,
    items: [
      {
        id: 'l-1',
        kind: 'time',
        time_entry_id: 'e-1',
        description: 'App — Login',
        service_date: iso(today),
        duration_seconds: 5400,
        quantity: '1.5000',
        unit_price: '85.00',
        amount: '127.50',
      },
    ],
    payments: [],
    ...overrides,
  };
}

function wrap(Screen: () => React.JSX.Element) {
  return function Wrapped() {
    return (
      <QueryClientProvider client={queryClient}>
        <Screen />
      </QueryClientProvider>
    );
  };
}

let fake: ReturnType<typeof createFakeApi>;

beforeEach(() => {
  queryClient.clear();
  fake = createFakeApi('http://localhost:8000/api/v1');
  globalThis.fetch = fake.fetchImpl;
  tokenStorage.setAccessToken('access-1');
  useAuth.setState({ status: 'signedIn', user: toUser(wireUser()), offline: false });
});

// Mutations invalidate several money queries; let those refetches finish inside the test that caused them,
// otherwise they spill into the next test as overlapping act() calls.
afterEach(async () => {
  await waitFor(() => expect(queryClient.isFetching() + queryClient.isMutating()).toBe(0));
  queryClient.clear();
});

describe('Invoice detail', () => {
  it('records a partial payment with an idempotency key and shows the new balance', async () => {
    let invoice = wireInvoice();
    fake
      .on('GET /invoices/:id', () => [200, invoice])
      .on('POST /invoices/:id/payments', (call) => {
        const body = call.body as { amount: string; paid_on: string; method: string };
        invoice = {
          ...invoice,
          payment_status: 'partial',
          amount_paid: body.amount,
          amount_due: '27.50',
          version: 3,
          payments: [{ id: 'pay-1', amount: body.amount, paid_on: body.paid_on, method: 'card', note: null, created_at: '' }],
        };
        return [201, invoice];
      });

    await renderRouter({ 'invoices/[id]': wrap(InvoiceDetailScreen) }, { initialUrl: '/invoices/inv-1' });
    expect(await screen.findByTestId('invoice-number')).toHaveTextContent('INV-2026-0001');
    expect(screen.getByTestId('invoice-due')).toHaveTextContent('$127.50 due');
    expect(screen.queryByTestId('invoice-edit')).toBeNull(); // issued invoices cannot

    await act(async () => fireEvent.press(screen.getByTestId('invoice-record-payment')));
    const amount = screen.getByTestId('payment-amount');
    expect(amount.props.value).toBe('127.50'); // defaults to the amount due
    await act(async () => fireEvent.changeText(amount, '200'));
    await act(async () => fireEvent.press(screen.getByTestId('payment-submit')));
    expect(await screen.findByText('More than the amount due')).toBeOnTheScreen(); // validated before sending
    expect(fake.callsTo('POST /invoices/:id/payments')).toHaveLength(0);

    await act(async () => fireEvent.changeText(amount, '100'));
    await act(async () => fireEvent.press(screen.getByTestId('payment-submit')));
    await waitFor(() => expect(screen.queryByTestId('payment-form')).toBeNull());
    const [call] = fake.callsTo('POST /invoices/:id/payments');
    expect(call?.body).toMatchObject({ amount: '100.00', method: 'bank_transfer', paid_on: iso(today) });
    expect(call?.headers['Idempotency-Key']).toMatch(/^[0-9a-f-]{36}$/);
    expect(await screen.findByText('Part-paid')).toBeOnTheScreen();
    expect(screen.getByTestId('invoice-due')).toHaveTextContent('$27.50 due');
  });

  it('asks for a second tap before sending and shows invoice-specific errors', async () => {
    fake
      .on('GET /invoices/:id', () => [200, wireInvoice({ status: 'draft', number: null, payment_status: null, amount_due: '0.00', version: 1 })])
      .on('POST /invoices/:id/send', () => [422, problem(422, 'INVOICE_EMPTY')]);
    await renderRouter({ 'invoices/[id]': wrap(InvoiceDetailScreen) }, { initialUrl: '/invoices/inv-1' });

    const send = await screen.findByTestId('invoice-send');
    expect(screen.getByTestId('invoice-edit')).toBeOnTheScreen(); // drafts can be edited
    await act(async () => fireEvent.press(send));
    expect(fake.callsTo('POST /invoices/:id/send')).toHaveLength(0);
    expect(screen.getByText('Tap again to send · number is assigned')).toBeOnTheScreen();
    await act(async () => fireEvent.press(screen.getByTestId('invoice-send')));
    expect(await screen.findByText('Add at least one line with an amount before sending.')).toBeOnTheScreen();
    expect(fake.callsTo('POST /invoices/:id/send')[0]?.body).toEqual({ version: 1 });
  });
});

describe('New invoice', () => {
  it('previews the totals with the server rules and creates a draft from the selected entries', async () => {
    const stopped = (id: string, amount: string, seconds: number) =>
      wireEntry({ id, status: 'stopped', ended_at: '2026-10-05T10:30:00Z', duration_seconds: seconds, billable_amount: amount });
    fake
      .on('GET /clients', () => [
        200,
        {
          items: [
            {
              id: 'c-1', name: 'Acme', email: null, company: null, notes: null, default_hourly_rate: null, currency: 'USD',
              archived_at: null, created_at: '', updated_at: '',
              stats: { active_projects: 1, tracked_seconds: 6600, unbilled: [{ currency: 'USD', amount: '155.83' }] },
            },
          ],
          next_cursor: null,
        },
      ])
      .on('GET /invoices/billable-entries', () => [
        200,
        { items: [stopped('e-1', '127.50', 5400), stopped('e-2', '28.33', 1200)], totals: [], truncated: false },
      ])
      .on('POST /invoices', () => [201, wireInvoice({ id: 'inv-9', status: 'draft', number: null })]);

    await renderRouter({ 'invoices/new': wrap(NewInvoiceScreen), 'invoices/[id]': () => null }, { initialUrl: '/invoices/new?clientId=c-1' });
    const preview = await screen.findByTestId('invoice-preview');
    await waitFor(() => expect(within(preview).getByTestId('invoice-preview-total')).toHaveTextContent('$155.83'));

    await act(async () => fireEvent.changeText(screen.getByTestId('invoice-tax'), '7.5'));
    await waitFor(() => expect(screen.getByTestId('invoice-preview-total')).toHaveTextContent('$167.52')); // 155.83 + 11.69

    await act(async () => fireEvent.press(screen.getByTestId('pick-entry-e-2')));
    await waitFor(() => expect(screen.getByTestId('invoice-preview-total')).toHaveTextContent('$137.06')); // 127.50 + 9.56

    await act(async () => fireEvent.press(screen.getByTestId('invoice-create')));
    await waitFor(() => expect(fake.callsTo('POST /invoices')).toHaveLength(1));
    const [call] = fake.callsTo('POST /invoices');
    expect(call?.body).toMatchObject({ client_id: 'c-1', time_entry_ids: ['e-1'], tax_rate: '7.50', items: [], issue_date: iso(today) });
    expect(call?.headers['Idempotency-Key']).toBeTruthy();
  });
});

describe('Edit draft', () => {
  const stopped = (id: string, amount: string, seconds: number) =>
    wireEntry({ id, status: 'stopped', ended_at: '2026-10-05T10:30:00Z', duration_seconds: seconds, billable_amount: amount });
  const draft = () =>
    wireInvoice({
      status: 'draft',
      number: null,
      payment_status: null,
      amount_due: '0.00',
      version: 3,
      issue_date: '2026-10-10',
      due_date: '2026-11-09', // 30 days
      subtotal: '177.50',
      tax_rate: '10.00',
      tax_amount: '17.75',
      total: '195.25',
      notes: 'Thanks!',
      items: [
        { id: 'l-1', kind: 'time', time_entry_id: 'e-1', description: 'App', service_date: '2026-10-05', duration_seconds: 5400, quantity: '1.5000', unit_price: '85.00', amount: '127.50' },
        { id: 'l-2', kind: 'custom', time_entry_id: null, description: 'Setup', service_date: null, duration_seconds: null, quantity: '2.0000', unit_price: '25.00', amount: '50.00' },
      ],
    });

  it('loads the draft, lets lines change and PATCHes with the version', async () => {
    fake
      .on('GET /invoices/:id', () => [200, draft()])
      .on('GET /invoices/billable-entries', (call) => {
        expect(call.query.get('invoice_id')).toBe('inv-1'); // the draft's own entries are included
        return [200, { items: [stopped('e-1', '127.50', 5400), stopped('e-2', '28.33', 1200)], totals: [], truncated: false }];
      })
      .on('PATCH /invoices/:id', (call) => [200, { ...draft(), version: 4, ...(call.body as object) }]);

    await renderRouter({ 'invoices/edit/[id]': wrap(EditInvoiceScreen), 'invoices/[id]': () => null }, { initialUrl: '/invoices/edit/inv-1' });
    await screen.findByTestId('invoice-edit-screen');
    // Only the entry on the draft starts selected; custom line, tax, notes and the 30-day term are restored.
    await waitFor(() => expect(screen.getByTestId('invoice-preview-total')).toHaveTextContent('$195.25')); // (127.50 + 50) + 10 %
    expect(screen.getByTestId('invoice-tax').props.value).toBe('10');
    expect(screen.getByTestId('extra-amount-0').props.value).toBe('50.00');
    expect(screen.getByTestId('invoice-notes').props.value).toBe('Thanks!');

    await act(async () => fireEvent.press(screen.getByTestId('pick-entry-e-1')));
    await act(async () => fireEvent.press(screen.getByTestId('pick-entry-e-2')));
    await act(async () => fireEvent.press(screen.getByTestId('extra-remove-0')));
    await act(async () => fireEvent.changeText(screen.getByTestId('invoice-tax'), ''));
    await waitFor(() => expect(screen.getByTestId('invoice-preview-total')).toHaveTextContent('$28.33'));

    await act(async () => fireEvent.press(screen.getByTestId('invoice-save')));
    await waitFor(() => expect(fake.callsTo('PATCH /invoices/:id')).toHaveLength(1));
    expect(fake.callsTo('PATCH /invoices/:id')[0]?.body).toEqual({
      version: 3,
      time_entry_ids: ['e-2'],
      issue_date: '2026-10-10',
      due_date: '2026-11-09',
      tax_rate: '0.00',
      notes: 'Thanks!',
      items: [],
    });
  });

  it('on a version conflict offers to reload instead of overwriting', async () => {
    let version = 3;
    fake
      .on('GET /invoices/:id', () => [200, { ...draft(), version }])
      .on('GET /invoices/billable-entries', () => [200, { items: [stopped('e-1', '127.50', 5400)], totals: [], truncated: false }])
      .on('PATCH /invoices/:id', () => {
        version = 4; // someone else saved first
        return [409, problem(409, 'VERSION_CONFLICT')];
      });
    await renderRouter({ 'invoices/edit/[id]': wrap(EditInvoiceScreen) }, { initialUrl: '/invoices/edit/inv-1' });
    await waitFor(() => expect(screen.getByTestId('invoice-preview-total')).toHaveTextContent('$195.25'));
    await act(async () => fireEvent.press(screen.getByTestId('invoice-save')));
    expect(await screen.findByTestId('invoice-conflict')).toBeOnTheScreen();
    await act(async () => fireEvent.press(screen.getByTestId('invoice-reload')));
    await waitFor(() => expect(screen.queryByTestId('invoice-conflict')).toBeNull());
    await act(async () => fireEvent.press(screen.getByTestId('invoice-save')));
    await waitFor(() => expect(fake.callsTo('PATCH /invoices/:id')).toHaveLength(2));
    expect((fake.callsTo('PATCH /invoices/:id')[1]?.body as { version: number }).version).toBe(4);
  });

  it('refuses to edit an issued invoice', async () => {
    fake.on('GET /invoices/:id', () => [200, wireInvoice()]);
    await renderRouter({ 'invoices/edit/[id]': wrap(EditInvoiceScreen) }, { initialUrl: '/invoices/edit/inv-1' });
    expect(await screen.findByTestId('invoice-edit-locked')).toBeOnTheScreen();
    expect(screen.queryByTestId('invoice-save')).toBeNull();
  });
});

describe('Dashboard', () => {
  it('keeps tracked value, invoiced and received apart and never adds currencies', async () => {
    const range = { from: '2026-10-01', to: '2026-10-31' };
    fake
      .on('GET /timer/current', () => [200, { entry: null, server_time: new Date().toISOString() }])
      .on('GET /dashboard/summary', () => [
        200,
        {
          range,
          previous_range: range,
          tracked_seconds: 7200,
          billable_seconds: 5400,
          previous_tracked_seconds: 3600,
          entries: 3,
          flows: [
            { currency: 'USD', tracked: '155.83', previous_tracked: '100.00', invoiced: '127.50', received: '100.00', billable_seconds: 5400, effective_hourly_rate: '85.00' },
            { currency: 'EUR', tracked: '30.00', previous_tracked: '0.00', invoiced: '0.00', received: '0.00', billable_seconds: 1800, effective_hourly_rate: '60.00' },
          ],
          balances: [{ currency: 'USD', unbilled: '28.33', outstanding: '27.50', overdue: '27.50' }],
          invoices: { draft: 1, open: 1, overdue: 1 },
          top_projects: [],
          server_time: new Date().toISOString(),
        },
      ])
      .on('GET /analytics/timeseries', () => [200, { range, interval: 'day', points: [] }]);

    await renderRouter({ index: wrap(DashboardScreen) }, { initialUrl: '/' });
    expect(await screen.findByTestId('flow-USD-tracked')).toHaveTextContent('$155.83');
    expect(screen.getByTestId('flow-USD-invoiced')).toHaveTextContent('$127.50');
    expect(screen.getByTestId('flow-USD-received')).toHaveTextContent('$100.00');
    expect(screen.getByTestId('flow-EUR-tracked')).toHaveTextContent('€30.00');
    expect(screen.getByTestId('balance-USD-outstanding')).toHaveTextContent('$27.50');
    expect(screen.getByTestId('balance-USD-overdue')).toHaveTextContent('$27.50');
    expect(screen.queryByText(/185\.83/)).toBeNull(); // USD + EUR are never summed
    const summary = fake.callsTo('GET /dashboard/summary')[0];
    expect(summary?.query.get('from')).toMatch(/^\d{4}-\d{2}-01$/);
  });
});
