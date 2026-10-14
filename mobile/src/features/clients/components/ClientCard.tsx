import { useTranslation } from 'react-i18next';
import { StyleSheet, View } from 'react-native';

import { formatAmounts } from '@/features/projects/components/ProjectCard';
import { formatMoney } from '@/shared/lib/money';
import type { Client } from '@/shared/types/domain';
import { AppText, Avatar, Card, Icon } from '@/shared/ui';
import { spacing } from '@/shared/theme';

export interface ClientCardProps {
  client: Client;
  onPress: () => void;
}

export function ClientCard({ client, onPress }: ClientCardProps) {
  const activeProjects = client.stats.activeProjects;
  const { t } = useTranslation();
  const rate = client.defaultHourlyRate
    ? t('projects.perHour', { rate: formatMoney(client.defaultHourlyRate, client.currency) })
    : client.currency;
  return (
    <Card onPress={onPress} padding="md" accessibilityLabel={`${client.name}, ${t('clients.activeProjects', { count: activeProjects })}`} accessibilityHint={t('clients.openDetailsHint')}>
      <View style={styles.row}>
        <Avatar name={client.name} />
        <View style={styles.text}>
          <AppText variant="subheading" numberOfLines={1}>
            {client.name}
          </AppText>
          <AppText variant="caption" color="textMuted" numberOfLines={1}>
            {client.company ?? client.email ?? t('clients.noCompany')}
          </AppText>
          <AppText variant="caption" color="textSecondary" numberOfLines={1}>
            {t('clients.activeShort', { count: activeProjects })} · {rate}
          </AppText>
        </View>
        <View style={styles.right}>
          <AppText variant="caption" color="textMuted">
            {t('clients.unbilled')}
          </AppText>
          <AppText variant="mono" numberOfLines={1}>
            {formatAmounts(client.stats.unbilled, { compact: true })}
          </AppText>
        </View>
        <Icon name="chevron-forward" size={18} color="textMuted" />
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  text: { flex: 1, gap: 2 },
  right: { alignItems: 'flex-end', gap: 2 },
});
