import { clientFormSchema, emptyClientForm, toClientPayload } from '@/features/clients/schema';

const valid = { ...emptyClientForm, name: 'Acme' };

describe('clientFormSchema', () => {
  it('accepts a minimal client', () => {
    expect(clientFormSchema.safeParse(valid).success).toBe(true);
  });

  it.each([
    [{ name: '   ' }, 'name'],
    [{ email: 'not-an-email' }, 'email'],
    [{ defaultHourlyRate: '12.345' }, 'defaultHourlyRate'],
    [{ defaultHourlyRate: '-5' }, 'defaultHourlyRate'],
    [{ defaultHourlyRate: '10000' }, 'defaultHourlyRate'],
  ])('rejects %p', (patch, field) => {
    const result = clientFormSchema.safeParse({ ...valid, ...patch });
    expect(result.success).toBe(false);
    expect(result.error?.issues.some((i) => i.path[0] === field)).toBe(true);
  });

  it('normalises the payload', () => {
    expect(toClientPayload({ ...valid, name: ' Acme ', email: ' Billing@ACME.io ', defaultHourlyRate: '85.5', company: '' })).toEqual({
      name: 'Acme',
      company: null,
      email: 'billing@acme.io',
      defaultHourlyRate: '85.50',
      currency: 'USD',
    });
  });
});
