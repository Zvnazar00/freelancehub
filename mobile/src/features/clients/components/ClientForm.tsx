import { zodResolver } from '@hookform/resolvers/zod';
import { Controller, useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { StyleSheet, View } from 'react-native';

import { applyServerFieldErrors } from '@/features/auth/formErrors';
import type { TxKey } from '@/shared/i18n';
import { SUPPORTED_CURRENCIES } from '@/shared/types/domain';
import { AppText, Button, Input, SegmentedControl } from '@/shared/ui';
import { spacing } from '@/shared/theme';

import { clientFormSchema, emptyClientForm, type ClientFormValues } from '../schema';

const currencyOptions = SUPPORTED_CURRENCIES.map((c) => ({ value: c, label: c }));

export interface ClientFormProps {
  submitLabel?: string;
  /** `applyServerErrors` maps API validation errors onto fields; returns true when it handled the error. */
  onSubmit: (values: ClientFormValues, applyServerErrors: (error: unknown) => boolean) => void | Promise<void>;
  defaultValues?: ClientFormValues;
}

export function ClientForm({ submitLabel, onSubmit, defaultValues = emptyClientForm }: ClientFormProps) {
  const { t } = useTranslation();
  /** Schema messages are i18n keys (see ../schema.ts). */
  const tr = (message: string | undefined) => (message ? t(message as TxKey) : undefined);
  const {
    control,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<ClientFormValues>({ resolver: zodResolver(clientFormSchema), defaultValues, mode: 'onTouched' });

  return (
    <View style={styles.form}>
      <Controller
        control={control}
        name="name"
        render={({ field }) => (
          <Input
            testID="client-name"
            label={t('clientForm.name')}
            placeholder={t('clientForm.namePlaceholder')}
            autoCapitalize="words"
            returnKeyType="next"
            value={field.value}
            onChangeText={field.onChange}
            onBlur={field.onBlur}
            error={tr(errors.name?.message)}
          />
        )}
      />
      <Controller
        control={control}
        name="company"
        render={({ field }) => (
          <Input
            label={t('clientForm.company')}
            placeholder={t('clientForm.companyPlaceholder')}
            value={field.value}
            onChangeText={field.onChange}
            onBlur={field.onBlur}
            error={tr(errors.company?.message)}
          />
        )}
      />
      <Controller
        control={control}
        name="email"
        render={({ field }) => (
          <Input
            testID="client-email"
            label={t('clientForm.email')}
            placeholder={t('clientForm.emailPlaceholder')}
            keyboardType="email-address"
            autoCapitalize="none"
            autoCorrect={false}
            leftIcon="mail-outline"
            value={field.value}
            onChangeText={field.onChange}
            onBlur={field.onBlur}
            error={tr(errors.email?.message)}
          />
        )}
      />
      <View style={styles.rateBlock}>
        <AppText variant="captionMedium" color="textSecondary">
          {t('clientForm.currency')}
        </AppText>
        <Controller
          control={control}
          name="currency"
          render={({ field }) => (
            <SegmentedControl
              accessibilityLabel={t('clientForm.currencyA11y')}
              layout="scroll"
              options={currencyOptions}
              value={field.value}
              onChange={field.onChange}
            />
          )}
        />
      </View>
      <Controller
        control={control}
        name="defaultHourlyRate"
        render={({ field }) => (
          <Input
            testID="client-rate"
            label={t('clientForm.rate')}
            placeholder="85.00"
            keyboardType="decimal-pad"
            mono
            value={field.value}
            onChangeText={field.onChange}
            onBlur={field.onBlur}
            error={tr(errors.defaultHourlyRate?.message)}
            helper={t('clientForm.rateHelper')}
          />
        )}
      />
      <Button testID="client-submit" label={submitLabel ?? t('clientForm.submit')} size="lg" fullWidth loading={isSubmitting} onPress={handleSubmit((values) =>
          onSubmit(values, (error) =>
            applyServerFieldErrors(
              error,
              setError,
              { name: 'name', email: 'email', company: 'company', default_hourly_rate: 'defaultHourlyRate' },
              { NAME_TAKEN: { field: 'name', message: 'errors.NAME_TAKEN' } },
            ),
          ),
        )} />
    </View>
  );
}

const styles = StyleSheet.create({
  form: { gap: spacing.lg },
  rateBlock: { gap: spacing.xs + 2 },
});
