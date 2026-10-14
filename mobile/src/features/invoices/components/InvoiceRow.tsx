import { useTranslation } from 'react-i18next';
import { StyleSheet, View } from 'react-native';

import { formatMoney } from '@/shared/lib/money';
import { formatCalendarDate } from '@/shared/lib/time';
import type { InvoiceSummary } from '@/shared/types/domain';
import { AppText, Badge, Card } from '@/shared/ui';
import { spacing } from '@/shared/theme';

import { displayStatus, statusTone } from '../status';

export function InvoiceStatusBadge({ invoice }: { invoice: Pick<InvoiceSummary, 'status' | 'isOverdue' | 'paymentStatus'> }) {
  const { t } = useTranslation();
  const status = displayStatus(invoice);
  return <Badge label={t(`invoices.status.${status}`)} tone={statusTone[status]} dot />;
}

export function InvoiceRow({ invoice, onPress }: { invoice: InvoiceSummary; onPress: () => void }) {
  const { t } = useTranslation();
  const status = displayStatus(invoice);
  const title = invoice.number ?? t('invoices.draftTitle');
  const due = status === 'open' || status === 'partial' || status === 'overdue';
  return (
    <Card
      padding="md"
      onPress={onPress}
      style={styles.card}
      accessibilityLabel={`${title}, ${invoice.client.name}, ${t(`invoices.status.${status}`)}, ${formatMoney(invoice.total, invoice.currency)}`}
      testID={`invoice-row-${invoice.id}`}
    >
      <View style={styles.top}>
        <View style={styles.flex}>
          <AppText variant="bodyMedium" numberOfLines={1}>
            {title}
          </AppText>
          <AppText variant="caption" color="textMuted" numberOfLines={1}>
            {invoice.client.name}
          </AppText>
        </View>
        <View style={styles.right}>
          <AppText variant="mono">{formatMoney(invoice.total, invoice.currency)}</AppText>
          <InvoiceStatusBadge invoice={invoice} />
        </View>
      </View>
      <View style={styles.bottom}>
        <AppText variant="caption" color="textMuted">
          {status === 'draft'
            ? t('invoices.createdOn', { date: formatCalendarDate(invoice.createdAt.slice(0, 10)) })
            : t('invoices.dueOn', { date: formatCalendarDate(invoice.dueDate) })}
        </AppText>
        {due ? (
          <AppText variant="monoSmall" color={status === 'overdue' ? 'danger' : 'textSecondary'}>
            {t('invoices.amountDueShort', { amount: formatMoney(invoice.amountDue, invoice.currency) })}
          </AppText>
        ) : null}
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  card: { gap: spacing.sm },
  top: { flexDirection: 'row', alignItems: 'flex-start', gap: spacing.md },
  flex: { flex: 1 },
  right: { alignItems: 'flex-end', gap: spacing.xs },
  bottom: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
});
