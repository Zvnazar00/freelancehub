import { useTranslation } from 'react-i18next';
import { Pressable, StyleSheet, View } from 'react-native';

import { formatMoney } from '@/shared/lib/money';
import { formatDuration, formatShortDay } from '@/shared/lib/time';
import type { TimeEntry } from '@/shared/types/domain';
import { AppText, Icon } from '@/shared/ui';
import { colors, radii, spacing } from '@/shared/theme';

export interface EntryPickerProps {
  entries: TimeEntry[];
  selected: ReadonlySet<string>;
  onToggle: (id: string) => void;
}

/** Checkbox list of billable entries (oldest first, like the invoice lines). */
export function EntryPicker({ entries, selected, onToggle }: EntryPickerProps) {
  const { t } = useTranslation();
  return (
    <View>
      {entries.map((entry, i) => {
        const checked = selected.has(entry.id);
        const title = entry.description || entry.task?.title || entry.project.name;
        return (
          <Pressable
            key={entry.id}
            testID={`pick-entry-${entry.id}`}
            accessibilityRole="checkbox"
            accessibilityState={{ checked }}
            accessibilityLabel={`${title}, ${formatShortDay(new Date(entry.startedAt))}, ${formatDuration(entry.durationSeconds ?? 0)}`}
            onPress={() => onToggle(entry.id)}
            style={({ pressed }) => [styles.row, i > 0 && styles.divider, pressed && styles.pressed]}
          >
            <View style={[styles.box, checked && styles.boxChecked]}>{checked ? <Icon name="checkmark" size={14} color="textOnAccent" /> : null}</View>
            <View style={styles.main}>
              <AppText variant="bodyMedium" numberOfLines={1} color={checked ? 'textPrimary' : 'textMuted'}>
                {title}
              </AppText>
              <AppText variant="caption" color="textMuted" numberOfLines={1}>
                {formatShortDay(new Date(entry.startedAt))} · {entry.project.name}
                {entry.task && entry.description ? ` · ${entry.task.title}` : ''}
              </AppText>
            </View>
            <View style={styles.right}>
              <AppText variant="mono" color={checked ? 'textPrimary' : 'textMuted'}>
                {formatDuration(entry.durationSeconds ?? 0)}
              </AppText>
              {entry.billableAmount ? (
                <AppText variant="monoSmall" color="textMuted">
                  {formatMoney(entry.billableAmount, entry.currency)}
                </AppText>
              ) : (
                <AppText variant="caption" color="textMuted">
                  {t('invoiceForm.noRate')}
                </AppText>
              )}
            </View>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, paddingVertical: spacing.md, minHeight: 56 },
  divider: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  pressed: { backgroundColor: colors.surface2, borderRadius: radii.sm },
  box: {
    width: 22,
    height: 22,
    borderRadius: 6,
    borderWidth: 1.5,
    borderColor: colors.borderStrong,
    alignItems: 'center',
    justifyContent: 'center',
  },
  boxChecked: { backgroundColor: colors.accentStrong, borderColor: colors.accentStrong },
  main: { flex: 1, gap: 2 },
  right: { alignItems: 'flex-end', gap: 2 },
});
