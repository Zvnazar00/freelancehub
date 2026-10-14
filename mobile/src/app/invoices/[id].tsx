import { router, Stack, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { StyleSheet, View } from 'react-native';

import { useDeletePayment, useInvoice, useInvoiceCommand, useSharePdf } from '@/features/invoices/api';
import { InvoiceStatusBadge } from '@/features/invoices/components/InvoiceRow';
import { PaymentForm } from '@/features/invoices/components/PaymentForm';
import { allowedActions, displayStatus } from '@/features/invoices/status';
import { errorMessageKey, isApiError } from '@/shared/api';
import { formatMoney } from '@/shared/lib/money';
import { formatCalendarDate, formatDuration } from '@/shared/lib/time';
import type { Invoice } from '@/shared/types/domain';
import { AppText, Button, Card, EmptyState, ErrorState, IconButton, InlineError, LoadingState, Screen, SectionHeader } from '@/shared/ui';
import { colors, spacing } from '@/shared/theme';

type Confirm = 'send' | 'void' | 'delete' | `payment:${string}` | null;

export default function InvoiceDetailScreen() {
  const { t } = useTranslation();
  const { id } = useLocalSearchParams<{ id: string }>();
  const query = useInvoice(id);
  const command = useInvoiceCommand();
  const deletePayment = useDeletePayment(id ?? '');
  const pdf = useSharePdf();
  const [paying, setPaying] = useState(false);
  // Destructive or irreversible actions need a second tap (works the same on iOS, Android and web).
  const [confirm, setConfirm] = useState<Confirm>(null);
  const [refreshing, setRefreshing] = useState(false);
  const invoice = query.data;

  if (!invoice) {
    const notFound = isApiError(query.error) && query.error.status === 404;
    return (
      <Screen edges={['bottom']}>
        <Stack.Screen options={{ title: t('screens.invoice') }} />
        {query.isPending ? (
          <LoadingState rows={5} />
        ) : notFound ? (
          <EmptyState icon="document-outline" title={t('invoices.notFound')} message={t('invoices.notFoundHint')} actionLabel={t('invoices.back')} onAction={() => router.replace('/invoices')} />
        ) : (
          <ErrorState message={t(errorMessageKey(query.error))} onRetry={() => void query.refetch()} retrying={query.isFetching} />
        )}
      </Screen>
    );
  }

  const actions = allowedActions(invoice);
  const status = displayStatus(invoice);
  const title = invoice.number ?? t('invoices.draftTitle');

  const run = (kind: 'send' | 'void' | 'delete') => {
    if (confirm !== kind) {
      setConfirm(kind);
      return;
    }
    setConfirm(null);
    command.mutate(
      { kind, invoice },
      { onSuccess: () => (kind === 'delete' ? router.replace('/invoices') : undefined) },
    );
  };

  const refresh = () => {
    setRefreshing(true);
    void query.refetch().finally(() => setRefreshing(false));
  };

  return (
    <Screen edges={['bottom']} testID="invoice-detail-screen" onRefresh={refresh} refreshing={refreshing} keyboard={paying}>
      <Stack.Screen options={{ title }} />

      <Card style={styles.gap}>
        <View style={styles.head}>
          <View style={styles.flex}>
            <AppText variant="heading" testID="invoice-number">
              {title}
            </AppText>
            <AppText
              variant="captionMedium"
              color="accentText"
              accessibilityRole="link"
              onPress={() => router.push({ pathname: '/clients/[id]', params: { id: invoice.client.id } })}
            >
              {invoice.client.name}
            </AppText>
          </View>
          <InvoiceStatusBadge invoice={invoice} />
        </View>
        <AppText variant="monoLarge" testID="invoice-total">
          {formatMoney(invoice.total, invoice.currency)}
        </AppText>
        {status === 'open' || status === 'partial' || status === 'overdue' ? (
          <AppText variant="captionMedium" color={status === 'overdue' ? 'danger' : 'textSecondary'} testID="invoice-due">
            {status === 'overdue'
              ? t('invoices.overdueBy', { count: invoice.daysOverdue, amount: formatMoney(invoice.amountDue, invoice.currency) })
              : t('invoices.amountDue', { amount: formatMoney(invoice.amountDue, invoice.currency) })}
          </AppText>
        ) : null}
        <View style={styles.dates}>
          <Meta label={t('invoices.issued')} value={formatCalendarDate(invoice.issueDate)} />
          <Meta label={t('invoices.due')} value={formatCalendarDate(invoice.dueDate)} />
          <Meta label={t('invoices.time')} value={formatDuration(invoice.trackedSeconds)} />
        </View>
        {status === 'draft' ? (
          <AppText variant="caption" color="textMuted">
            {t('invoices.draftHint')}
          </AppText>
        ) : null}
      </Card>

      <View style={styles.actions}>
        {actions.send ? (
          <Button
            testID="invoice-send"
            label={confirm === 'send' ? t('invoices.confirmSend') : t('invoices.send')}
            icon="paper-plane-outline"
            fullWidth
            loading={command.isPending && command.variables?.kind === 'send'}
            onPress={() => run('send')}
          />
        ) : null}
        {actions.edit ? (
          <Button
            testID="invoice-edit"
            label={t('invoices.edit')}
            icon="create-outline"
            variant="secondary"
            fullWidth
            onPress={() => router.push({ pathname: '/invoices/edit/[id]', params: { id: invoice.id } })}
          />
        ) : null}
        {actions.recordPayment && !paying ? (
          <Button testID="invoice-record-payment" label={t('invoices.recordPayment')} icon="cash-outline" fullWidth onPress={() => setPaying(true)} />
        ) : null}
        <Button
          testID="invoice-pdf"
          label={t('invoices.sharePdf')}
          icon="share-outline"
          variant="secondary"
          fullWidth
          loading={pdf.isPending}
          onPress={() => pdf.mutate(invoice)}
        />
        {pdf.isSuccess && pdf.data === 'saved' ? (
          <AppText variant="caption" color="success" align="center">
            {t('exports.saved')}
          </AppText>
        ) : null}
        <InlineError error={pdf.error} />
        <InlineError error={command.error} scope="invoice" />
      </View>

      {paying ? <PaymentForm invoice={invoice} onDone={() => setPaying(false)} /> : null}

      <View style={styles.section}>
        <SectionHeader title={t('invoices.lines')} meta={String(invoice.items.length)} />
        <Card padding="md" style={styles.listCard}>
          {invoice.items.length === 0 ? (
            <EmptyState compact icon="list-outline" title={t('invoices.noLines')} />
          ) : (
            invoice.items.map((item, i) => (
              <View key={item.id} style={[styles.line, i > 0 && styles.divider]}>
                <View style={styles.flex}>
                  <AppText variant="body" numberOfLines={3}>
                    {item.description}
                  </AppText>
                  <AppText variant="monoSmall" color="textMuted">
                    {item.kind === 'time'
                      ? `${item.serviceDate ? `${formatCalendarDate(item.serviceDate)} · ` : ''}${formatDuration(item.durationSeconds ?? 0)} × ${formatMoney(item.unitPrice, invoice.currency)}`
                      : `${Number(item.quantity)} × ${formatMoney(item.unitPrice, invoice.currency)}`}
                  </AppText>
                </View>
                <AppText variant="mono">{formatMoney(item.amount, invoice.currency)}</AppText>
              </View>
            ))
          )}
        </Card>
        <Totals invoice={invoice} />
      </View>

      {invoice.status !== 'draft' ? (
        <View style={styles.section}>
          <SectionHeader title={t('invoices.payments')} meta={formatMoney(invoice.amountPaid, invoice.currency)} />
          <Card padding="md" style={styles.listCard}>
            {invoice.payments.length === 0 ? (
              <EmptyState compact icon="wallet-outline" title={t('invoices.noPayments')} message={t('invoices.noPaymentsHint')} />
            ) : (
              invoice.payments.map((p, i) => {
                const confirming = confirm === `payment:${p.id}`;
                return (
                  <View key={p.id} style={[styles.line, i > 0 && styles.divider]} testID={`payment-${p.id}`}>
                    <View style={styles.flex}>
                      <AppText variant="bodyMedium">{formatMoney(p.amount, invoice.currency)}</AppText>
                      <AppText variant="caption" color="textMuted">
                        {formatCalendarDate(p.paidOn)} · {t(`paymentForm.methods.${p.method}`)}
                        {p.note ? ` · ${p.note}` : ''}
                      </AppText>
                    </View>
                    {actions.deletePayment ? (
                      confirming ? (
                        <Button
                          label={t('invoices.confirmDeletePayment')}
                          size="sm"
                          variant="danger"
                          loading={deletePayment.isPending}
                          onPress={() => {
                            setConfirm(null);
                            deletePayment.mutate(p.id);
                          }}
                        />
                      ) : (
                        <IconButton icon="trash-outline" variant="plain" color="textMuted" accessibilityLabel={t('invoices.deletePayment')} onPress={() => setConfirm(`payment:${p.id}`)} />
                      )
                    ) : null}
                  </View>
                );
              })
            )}
          </Card>
          <InlineError error={deletePayment.error} scope="invoice" />
        </View>
      ) : null}

      {invoice.notes ? (
        <View style={styles.section}>
          <SectionHeader title={t('invoices.notes')} />
          <Card padding="md">
            <AppText variant="body" color="textSecondary">
              {invoice.notes}
            </AppText>
          </Card>
        </View>
      ) : null}

      {actions.void || actions.delete ? (
        <View style={styles.section}>
          <SectionHeader title={t('invoices.dangerZone')} />
          {actions.void ? (
            <Button
              testID="invoice-void"
              label={confirm === 'void' ? t('invoices.confirmVoid') : t('invoices.void')}
              icon="close-circle-outline"
              variant="danger"
              fullWidth
              loading={command.isPending && command.variables?.kind === 'void'}
              onPress={() => run('void')}
            />
          ) : null}
          {actions.delete ? (
            <Button
              testID="invoice-delete"
              label={confirm === 'delete' ? t('invoices.confirmDelete') : t('invoices.delete')}
              icon="trash-outline"
              variant="danger"
              fullWidth
              loading={command.isPending && command.variables?.kind === 'delete'}
              onPress={() => run('delete')}
            />
          ) : null}
          <AppText variant="caption" color="textMuted">
            {actions.void ? t('invoices.voidHint') : t('invoices.deleteHint')}
          </AppText>
        </View>
      ) : null}
      {invoice.status === 'sent' && !actions.void ? (
        <AppText variant="caption" color="textMuted">
          {t('invoices.voidBlockedHint')}
        </AppText>
      ) : null}
    </Screen>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.meta}>
      <AppText variant="caption" color="textMuted">
        {label}
      </AppText>
      <AppText variant="captionMedium">{value}</AppText>
    </View>
  );
}

function Totals({ invoice }: { invoice: Invoice }) {
  const { t } = useTranslation();
  const rows: [string, string, boolean][] = [[t('invoices.subtotal'), formatMoney(invoice.subtotal, invoice.currency), false]];
  if (invoice.taxRate !== '0.00') rows.push([t('invoices.tax', { rate: Number(invoice.taxRate) }), formatMoney(invoice.taxAmount, invoice.currency), false]);
  rows.push([t('invoices.total'), formatMoney(invoice.total, invoice.currency), true]);
  if (invoice.amountPaid !== '0.00') rows.push([t('invoices.paid'), formatMoney(invoice.amountPaid, invoice.currency), false]);
  if (invoice.status === 'sent' || invoice.status === 'paid') rows.push([t('invoices.balanceDue'), formatMoney(invoice.amountDue, invoice.currency), true]);
  return (
    <Card variant="raised" padding="md" style={styles.gapSm}>
      {rows.map(([label, value, strong]) => (
        <View key={label} style={styles.totalRow}>
          <AppText variant={strong ? 'bodyMedium' : 'caption'} color={strong ? 'textPrimary' : 'textSecondary'}>
            {label}
          </AppText>
          <AppText variant={strong ? 'mono' : 'monoSmall'}>{value}</AppText>
        </View>
      ))}
    </Card>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  gap: { gap: spacing.md },
  gapSm: { gap: spacing.sm },
  head: { flexDirection: 'row', alignItems: 'flex-start', gap: spacing.md },
  dates: { flexDirection: 'row', gap: spacing.lg, flexWrap: 'wrap' },
  meta: { gap: 2 },
  actions: { gap: spacing.sm },
  section: { gap: spacing.md },
  listCard: { paddingVertical: spacing.xs },
  line: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, paddingVertical: spacing.md },
  divider: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  totalRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
});
