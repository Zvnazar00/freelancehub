import { zodResolver } from '@hookform/resolvers/zod';
import { useMemo, useState } from 'react';
import { Controller, useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { StyleSheet, View } from 'react-native';

import { applyServerFieldErrors } from '@/features/auth/formErrors';
import type { TxKey } from '@/shared/i18n';
import { centsToDecimal, decimalToCents } from '@/shared/lib/money';
import { addDays, localDateKey } from '@/shared/lib/time';
import { PAYMENT_METHODS, type Invoice } from '@/shared/types/domain';
import { AppText, Button, Card, InlineError, Input, SegmentedControl } from '@/shared/ui';
import { spacing } from '@/shared/theme';

import { newIdempotencyKey, useRecordPayment } from '../api';
import { paymentFormSchema, type PaymentFormValues } from '../schema';

export interface PaymentFormProps {
  invoice: Invoice;
  onDone: () => void;
}

/** Records a payment. The amount defaults to what is still due; the server rejects overpayments too. */
export function PaymentForm({ invoice, onDone }: PaymentFormProps) {
  const { t } = useTranslation();
  const tr = (m?: string) => (m ? t(m as TxKey) : undefined);
  const today = useMemo(() => new Date(), []);
  const dueCents = decimalToCents(invoice.amountDue);
  const record = useRecordPayment(invoice.id);
  // The key lives as long as this form: a retry after a dropped response replays instead of paying twice.
  const [key] = useState(newIdempotencyKey);
  const [bannerError, setBannerError] = useState<unknown>(null);
  const { control, handleSubmit, setValue, setError, formState: { errors } } = useForm<PaymentFormValues>({
    resolver: zodResolver(paymentFormSchema(dueCents, today)),
    defaultValues: { amount: centsToDecimal(dueCents), paidOn: localDateKey(today), method: 'bank_transfer', note: '' },
    mode: 'onTouched',
  });

  const submit = handleSubmit(async (values) => {
    setBannerError(null);
    try {
      await record.mutateAsync({ ...values, amount: centsToDecimal(decimalToCents(values.amount)), idempotencyKey: key });
      onDone();
    } catch (error) {
      const handled = applyServerFieldErrors(error, setError, { paid_on: 'paidOn' }, {
        OVERPAYMENT: { field: 'amount', message: 'errors.OVERPAYMENT' },
      });
      if (!handled) setBannerError(error);
    }
  });

  return (
    <Card variant="raised" style={styles.card} testID="payment-form">
      <AppText variant="subheading">{t('paymentForm.title')}</AppText>
      <Controller
        control={control}
        name="amount"
        render={({ field }) => (
          <Input
            testID="payment-amount"
            label={t('paymentForm.amount', { currency: invoice.currency })}
            keyboardType="decimal-pad"
            mono
            value={field.value}
            onChangeText={field.onChange}
            onBlur={field.onBlur}
            error={tr(errors.amount?.message)}
            helper={t('paymentForm.amountHelper')}
          />
        )}
      />
      <Controller
        control={control}
        name="paidOn"
        render={({ field }) => (
          <View style={styles.gap}>
            <Input
              testID="payment-date"
              label={t('paymentForm.date')}
              placeholder="YYYY-MM-DD"
              mono
              autoCapitalize="none"
              value={field.value}
              onChangeText={field.onChange}
              onBlur={field.onBlur}
              error={tr(errors.paidOn?.message)}
            />
            <View style={styles.chips}>
              <Button label={t('common.today')} size="sm" variant="secondary" onPress={() => setValue('paidOn', localDateKey(today), { shouldValidate: true })} />
              <Button
                label={t('common.yesterday')}
                size="sm"
                variant="secondary"
                onPress={() => setValue('paidOn', localDateKey(addDays(today, -1)), { shouldValidate: true })}
              />
            </View>
          </View>
        )}
      />
      <View style={styles.gap}>
        <AppText variant="captionMedium" color="textSecondary">
          {t('paymentForm.method')}
        </AppText>
        <Controller
          control={control}
          name="method"
          render={({ field }) => (
            <SegmentedControl
              layout="scroll"
              accessibilityLabel={t('paymentForm.method')}
              value={field.value}
              onChange={field.onChange}
              options={PAYMENT_METHODS.map((m) => ({ value: m, label: t(`paymentForm.methods.${m}`) }))}
            />
          )}
        />
      </View>
      <Controller
        control={control}
        name="note"
        render={({ field }) => (
          <Input
            label={t('paymentForm.note')}
            placeholder={t('paymentForm.notePlaceholder')}
            value={field.value}
            onChangeText={field.onChange}
            onBlur={field.onBlur}
            error={tr(errors.note?.message)}
            maxLength={500}
          />
        )}
      />
      <InlineError error={bannerError} scope="invoice" />
      <View style={styles.actions}>
        <Button label={t('common.cancel')} variant="ghost" onPress={onDone} />
        <Button testID="payment-submit" label={t('paymentForm.submit')} icon="checkmark" loading={record.isPending} onPress={() => void submit()} />
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  card: { gap: spacing.lg },
  gap: { gap: spacing.sm },
  chips: { flexDirection: 'row', gap: spacing.sm },
  actions: { flexDirection: 'row', justifyContent: 'flex-end', gap: spacing.sm },
});
