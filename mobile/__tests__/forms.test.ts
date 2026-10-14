import { signInSchema, signUpSchema } from '@/features/auth/schema';
import { emptyProjectForm, projectFormSchema, toProjectPayload } from '@/features/projects/schema';

const messages = (r: { success: boolean; error?: { issues: { path: PropertyKey[]; message: string }[] } }) =>
  Object.fromEntries((r.error?.issues ?? []).map((i) => [i.path.join('.'), i.message]));

describe('auth forms', () => {
  it('validates sign-in', () => {
    expect(signInSchema.safeParse({ email: 'a@b.co', password: 'x' }).success).toBe(true);
    expect(messages(signInSchema.safeParse({ email: 'nope', password: '' }))).toEqual({
      email: 'auth.errors.emailInvalid',
      password: 'auth.errors.passwordRequired',
    });
  });

  it('mirrors the server password rules on sign-up', () => {
    expect(messages(signUpSchema.safeParse({ fullName: ' ', email: 'a@b.co', password: 'short' }))).toEqual({
      fullName: 'auth.errors.nameRequired',
      password: 'auth.errors.passwordShort',
    });
    expect(messages(signUpSchema.safeParse({ fullName: 'A', email: 'long.email@b.co', password: 'LONG.EMAIL@B.CO' }))).toEqual({
      password: 'auth.errors.passwordIsEmail',
    });
  });
});

describe('project form', () => {
  const base = { ...emptyProjectForm('c-1'), name: '  Redesign ' };

  it('requires a fee for fixed-price projects and validates amounts', () => {
    expect(messages(projectFormSchema.safeParse({ ...base, billingType: 'fixed' }))).toEqual({ fixedFee: 'projectForm.errors.feeRequired' });
    expect(messages(projectFormSchema.safeParse({ ...base, hourlyRate: '12.345' }))).toEqual({ hourlyRate: 'projectForm.errors.amountFormat' });
    expect(messages(projectFormSchema.safeParse({ ...base, clientId: '' }))).toEqual({ clientId: 'projectForm.errors.clientRequired' });
  });

  it('builds a payload with only the values that apply to the billing type', () => {
    expect(toProjectPayload({ ...base, hourlyRate: '85.5', fixedFee: '999', budgetHours: '40' })).toEqual({
      clientId: 'c-1',
      name: 'Redesign',
      billingType: 'hourly',
      hourlyRate: '85.50',
      fixedFee: null,
      budgetHours: '40.00',
      color: '#8B7CFF',
    });
    expect(toProjectPayload({ ...base, billingType: 'fixed', hourlyRate: '85', fixedFee: '2500' })).toMatchObject({ hourlyRate: null, fixedFee: '2500.00' });
  });
});
