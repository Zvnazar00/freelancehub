import { useTranslation } from 'react-i18next';
import { StyleSheet, View } from 'react-native';

import { useReachability } from '@/shared/api';
import { colors, radii, spacing } from '@/shared/theme';

import { AppText } from './AppText';
import { Icon } from './Icon';

/** Shown while the last request failed to reach the server; hides itself after the next successful response. */
export function OfflineBanner() {
  const { t } = useTranslation();
  const reachable = useReachability((s) => s.reachable);
  if (reachable) return null;
  return (
    <View style={styles.box} accessibilityRole="alert" accessibilityLabel={`${t('common.offline')}. ${t('common.offlineHint')}`} testID="offline-banner">
      <Icon name="cloud-offline-outline" size={16} color="warning" />
      <View style={styles.text}>
        <AppText variant="captionMedium" color="warning">
          {t('common.offline')}
        </AppText>
        <AppText variant="caption" color="textSecondary">
          {t('common.offlineHint')}
        </AppText>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  box: {
    flexDirection: 'row',
    gap: spacing.sm,
    padding: spacing.md,
    borderRadius: radii.md,
    backgroundColor: colors.warningSoft,
  },
  text: { flex: 1, gap: 2 },
});
