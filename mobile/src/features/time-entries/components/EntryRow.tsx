import { useTranslation } from 'react-i18next';
import { Pressable, StyleSheet, View } from 'react-native';

import { formatMoney } from '@/shared/lib/money';
import { formatDuration, formatTimeOfDay } from '@/shared/lib/time';
import type { TimeEntry } from '@/shared/types/domain';
import { AppText, Icon } from '@/shared/ui';
import { colors, radii, spacing } from '@/shared/theme';

export interface EntryRowProps {
  entry: TimeEntry;
  onLongPress?: () => void;
}

export function EntryRow({ entry, onLongPress }: EntryRowProps) {
  const { t } = useTranslation();
  const start = new Date(entry.startedAt);
  const end = entry.endedAt ? new Date(entry.endedAt) : null;
  const seconds = entry.durationSeconds ?? 0;
  const meta = [entry.project.name || t('common.unknownProject'), entry.task?.title].filter(Boolean).join(' · ');
  const range = `${formatTimeOfDay(start)} – ${end ? formatTimeOfDay(end) : t('common.now')}`;
  const description = entry.description || t('common.noDescription');

  return (
    <Pressable
      onLongPress={onLongPress}
      accessibilityLabel={`${description}, ${meta}, ${range}, ${formatDuration(seconds)}`}
      style={({ pressed }) => [styles.row, pressed && onLongPress ? styles.pressed : null]}
    >
      <View style={[styles.stripe, { backgroundColor: entry.project.color || colors.borderStrong }]} />
      <View style={styles.main}>
        <AppText variant="bodyMedium" numberOfLines={1} color={entry.description ? 'textPrimary' : 'textMuted'}>
          {description}
        </AppText>
        <AppText variant="caption" color="textSecondary" numberOfLines={1}>
          {meta}
        </AppText>
        <View style={styles.metaRow}>
          <AppText variant="monoSmall" color="textMuted">
            {range}
          </AppText>
          {entry.pauses.length > 0 ? <Icon name="pause-circle-outline" size={13} color="textMuted" /> : null}
          {entry.source === 'manual' ? <Icon name="create-outline" size={13} color="textMuted" /> : null}
          {!entry.billable ? (
            <AppText variant="caption" color="textMuted">
              {t('entry.nonBillable')}
            </AppText>
          ) : null}
        </View>
      </View>
      <View style={styles.right}>
        <AppText variant="mono">{formatDuration(seconds)}</AppText>
        {entry.billableAmount ? (
          <AppText variant="monoSmall" color="textMuted">
            {formatMoney(entry.billableAmount, entry.currency)}
          </AppText>
        ) : null}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, paddingVertical: spacing.md, borderRadius: radii.sm },
  pressed: { backgroundColor: colors.surface2 },
  stripe: { width: 3, alignSelf: 'stretch', borderRadius: 2 },
  main: { flex: 1, gap: 2 },
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs + 2, marginTop: 2 },
  right: { alignItems: 'flex-end', gap: 2 },
});
