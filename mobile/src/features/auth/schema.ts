import { z } from 'zod';

/** Mirrors the backend rules (app/schemas/auth.py). Messages are i18n keys. */
const email = z.string().trim().min(1, 'auth.errors.emailRequired').max(254).pipe(z.email('auth.errors.emailInvalid'));

export const signInSchema = z.object({
  email,
  password: z.string().min(1, 'auth.errors.passwordRequired').max(128),
});
export type SignInValues = z.infer<typeof signInSchema>;

export const signUpSchema = z
  .object({
    fullName: z.string().trim().min(1, 'auth.errors.nameRequired').max(120, 'auth.errors.nameTooLong'),
    email,
    password: z.string().min(10, 'auth.errors.passwordShort').max(128, 'auth.errors.passwordLong'),
  })
  .refine((v) => v.password.trim().toLowerCase() !== v.email.trim().toLowerCase(), {
    path: ['password'],
    message: 'auth.errors.passwordIsEmail',
  });
export type SignUpValues = z.infer<typeof signUpSchema>;
