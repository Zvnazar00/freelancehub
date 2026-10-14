import { useTranslation } from 'react-i18next';
import { StyleSheet, View } from 'react-native';

import { diffCents, formatMoney, centsToDecimal } from '@/shared/lib/money';
import { formatDuration } from '@/shared/lib/time';
import type { Balance, MoneyFlow } from '@/shared/types/domain';
import { AppText, Card, Icon } from '@/shared/ui';
import { colors, spacing } from '@/shared/theme';

function Row({ label, value, hint, tone = 'textPrimary', testID }: { label: string; value: string; hint?: string; tone?: 'textPrimary' | 'success' | 'info' | 'danger' | 'warning' | 'textMuted'; testID?: string }) {
  return (
    <View style={styles.row} accessible accessibilityLabel={`${label}: ${value}${hint ? `, ${hint}` : ''}`}>
      <View style={styles.flex}>
        <AppText variant="captionMedium" color="textSecondary">
          {label}
        </AppText>
        {hint ? (
          <AppText variant="caption" color="textMuted">
            {hint}
          </AppText>
        ) : null}
      </View>
      <AppText variant="mono" color={tone} testID={testID}>
        {value}
      </AppText>
    </View>
  );
}

/**
 * One card per currency. Three distinct numbers, never merged: tracked value (work done), invoiced (bills
 * issued) and received (payments). Labels say what each one is so tracked value never reads as income.
 */
export function MoneyFlowCard({ flow }: { flow: MoneyFlow }) {
  const { t } = useTranslation();
  const delta = diffCents(flow.tracked, flow.previousTracked);
  const deltaText =
    delta === 0
      ? t('money.sameAsBefore')
      : t(delta > 0 ? 'money.moreThanBefore' : 'money.lessThanBefore', {
          amount: formatMoney(centsToDecimal(Math.abs(delta)), flow.currency),
        });

  return (
    <Card variant="raised" padding="lg" style={styles.card} testID={`flow-${flow.currency}`}>
      <View style={styles.head}>
        <AppText variant="overline" color="textMuted">
          {t('money.trackedValue')} · {flow.currency}
        </AppText>
        {flow.effectiveHourlyRate ? (
          <AppText variant="monoSmall" color="textMuted">
            {t('money.perHour', { rate: formatMoney(flow.effectiveHourlyRate, flow.currency) })}
          </AppText>
        ) : null}
      </View>
      <AppText variant="monoLarge" numberOfLines={1} adjustsFontSizeToFit testID={`flow-${flow.currency}-tracked`}>
        {formatMoney(flow.tracked, flow.currency)}
      </AppText>
      <View style={styles.deltaRow}>
        {delta !== 0 ? <Icon name={delta > 0 ? 'trending-up' : 'trending-down'} size={14} color={delta > 0 ? 'success' : 'textMuted'} /> : null}
        <AppText variant="caption" color="textMuted">
          {deltaText} · {t('money.billableTime', { duration: formatDuration(flow.billableSeconds) })}
        </AppText>
      </View>
      <View style={styles.divider} />
      <Row label={t('money.invoiced')} hint={t('money.invoicedHint')} value={formatMoney(flow.invoiced, flow.currency)} tone="info" testID={`flow-${flow.currency}-invoiced`} />
      <Row label={t('money.received')} hint={t('money.receivedHint')} value={formatMoney(flow.received, flow.currency)} tone="success" testID={`flow-${flow.currency}-received`} />
    </Card>
  );
}

/** Balances as of today: what still has to be billed, what clients still owe, and what is late. */
export function BalanceCard({ balance, onPressOutstanding }: { balance: Balance; onPressOutstanding?: () => void }) {
  const { t } = useTranslation();
  const overdue = balance.overdue !== '0.00';
  return (
    <Card padding="lg" style={styles.card} onPress={onPressOutstanding} accessibilityHint={onPressOutstanding ? t('money.openInvoicesHint') : undefined} testID={`balance-${balance.currency}`}>
      <AppText variant="overline" color="textMuted">
        {t('money.balancesNow')} · {balance.currency}
      </AppText>
      <Row label={t('money.unbilled')} hint={t('money.unbilledHint')} value={formatMoney(balance.unbilled, balance.currency)} testID={`balance-${balance.currency}-unbilled`} />
      <Row label={t('money.outstanding')} hint={t('money.outstandingHint')} value={formatMoney(balance.outstanding, balance.currency)} tone="warning" testID={`balance-${balance.currency}-outstanding`} />
      {overdue ? (
        <Row label={t('money.overdue')} value={formatMoney(balance.overdue, balance.currency)} tone="danger" testID={`balance-${balance.currency}-overdue`} />
      ) : null}
    </Card>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  card: { gap: spacing.sm },
  head: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  deltaRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
  divider: { height: StyleSheet.hairlineWidth, backgroundColor: colors.border, marginVertical: spacing.xs },
  row: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, minHeight: 36 },
});
