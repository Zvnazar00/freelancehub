import { zodResolver } from '@hookform/resolvers/zod';
import { Link } from 'expo-router';
import { useState } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { View } from 'react-native';

import { AuthShell } from '@/features/auth/components/AuthShell';
import { PasswordInput } from '@/features/auth/components/PasswordInput';
import { applyServerFieldErrors } from '@/features/auth/formErrors';
import { signUpSchema, type SignUpValues } from '@/features/auth/schema';
import { signUp } from '@/features/auth/session';
import type { TxKey } from '@/shared/i18n';
import { AppText, Button, InlineError, Input } from '@/shared/ui';
import { spacing } from '@/shared/theme';

export default function SignUpScreen() {
  const { t } = useTranslation();
  const tr = (m?: string) => (m ? t(m as TxKey) : undefined);
  const [error, setError] = useState<unknown>(null);
  const {
    control,
    handleSubmit,
    setError: setFieldError,
    formState: { errors, isSubmitting },
  } = useForm<SignUpValues>({
    resolver: zodResolver(signUpSchema),
    defaultValues: { fullName: '', email: '', password: '' },
    mode: 'onTouched',
  });

  const submit = handleSubmit(async (values) => {
    setError(null);
    try {
      await signUp(values);
    } catch (e) {
      const handled = applyServerFieldErrors(e, setFieldError, { full_name: 'fullName', email: 'email', password: 'password' }, {
        EMAIL_TAKEN: { field: 'email', message: 'errors.EMAIL_TAKEN' },
      });
      if (!handled) setError(e);
    }
  });

  return (
    <AuthShell
      testID="sign-up-screen"
      title={t('auth.signUpTitle')}
      subtitle={t('auth.signUpSubtitle')}
      footer={
        <>
          <AppText variant="caption" color="textMuted">
            {t('auth.haveAccount')}
          </AppText>
          <Link href="/sign-in" replace>
            <AppText variant="captionMedium" color="accentText">
              {t('auth.toSignIn')}
            </AppText>
          </Link>
        </>
      }
    >
      <View style={{ gap: spacing.lg }}>
        <Controller
          control={control}
          name="fullName"
          render={({ field }) => (
            <Input
              testID="auth-name"
              label={t('auth.fullName')}
              placeholder={t('auth.fullNamePlaceholder')}
              leftIcon="person-outline"
              autoCapitalize="words"
              autoComplete="name"
              textContentType="name"
              value={field.value}
              onChangeText={field.onChange}
              onBlur={field.onBlur}
              error={tr(errors.fullName?.message)}
            />
          )}
        />
        <Controller
          control={control}
          name="email"
          render={({ field }) => (
            <Input
              testID="auth-email"
              label={t('auth.email')}
              placeholder={t('auth.emailPlaceholder')}
              leftIcon="mail-outline"
              keyboardType="email-address"
              autoCapitalize="none"
              autoCorrect={false}
              autoComplete="email"
              textContentType="username"
              value={field.value}
              onChangeText={field.onChange}
              onBlur={field.onBlur}
              error={tr(errors.email?.message)}
            />
          )}
        />
        <Controller
          control={control}
          name="password"
          render={({ field }) => (
            <PasswordInput
              testID="auth-password"
              label={t('auth.password')}
              placeholder={t('auth.passwordPlaceholder')}
              helper={t('auth.passwordHint')}
              autoComplete="new-password"
              textContentType="newPassword"
              value={field.value}
              onChangeText={field.onChange}
              onBlur={field.onBlur}
              error={tr(errors.password?.message)}
            />
          )}
        />
        <InlineError error={error} testID="auth-error" />
        <Button testID="auth-submit" label={t('auth.signUp')} size="lg" fullWidth loading={isSubmitting} onPress={() => void submit()} />
      </View>
    </AuthShell>
  );
}
