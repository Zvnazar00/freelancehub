import { zodResolver } from '@hookform/resolvers/zod';
import { Link } from 'expo-router';
import { useState } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { View } from 'react-native';

import { AuthShell } from '@/features/auth/components/AuthShell';
import { PasswordInput } from '@/features/auth/components/PasswordInput';
import { signInSchema, type SignInValues } from '@/features/auth/schema';
import { signIn } from '@/features/auth/session';
import type { TxKey } from '@/shared/i18n';
import { AppText, Button, InlineError, Input } from '@/shared/ui';
import { spacing } from '@/shared/theme';

export default function SignInScreen() {
  const { t } = useTranslation();
  const tr = (m?: string) => (m ? t(m as TxKey) : undefined);
  const [error, setError] = useState<unknown>(null);
  const {
    control,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<SignInValues>({ resolver: zodResolver(signInSchema), defaultValues: { email: '', password: '' }, mode: 'onTouched' });

  const submit = handleSubmit(async (values) => {
    setError(null);
    try {
      await signIn(values); // on success the protected stack takes over (Stack.Protected)
    } catch (e) {
      setError(e);
    }
  });

  return (
    <AuthShell
      testID="sign-in-screen"
      title={t('auth.signInTitle')}
      subtitle={t('auth.signInSubtitle')}
      footer={
        <>
          <AppText variant="caption" color="textMuted">
            {t('auth.noAccount')}
          </AppText>
          <Link href="/sign-up" replace>
            <AppText variant="captionMedium" color="accentText">
              {t('auth.toSignUp')}
            </AppText>
          </Link>
        </>
      }
    >
      <View style={{ gap: spacing.lg }}>
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
              returnKeyType="next"
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
              autoComplete="current-password"
              textContentType="password"
              returnKeyType="go"
              onSubmitEditing={() => void submit()}
              value={field.value}
              onChangeText={field.onChange}
              onBlur={field.onBlur}
              error={tr(errors.password?.message)}
            />
          )}
        />
        <InlineError error={error} testID="auth-error" />
        <Button testID="auth-submit" label={t('auth.signIn')} size="lg" fullWidth loading={isSubmitting} onPress={() => void submit()} />
      </View>
    </AuthShell>
  );
}
