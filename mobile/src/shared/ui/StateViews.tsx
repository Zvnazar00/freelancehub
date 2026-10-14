import { useTranslation } from 'react-i18next';
import { StyleSheet, View } from 'react-native';

import { colors, radii, spacing } from '@/shared/theme';

import { AppText } from './AppText';
import { Button } from './Button';
import { Icon, type IconName } from './Icon';
import { Skeleton } from './Skeleton';

export interface LoadingStateProps {
  /** Number of placeholder rows. */
  rows?: number;
  label?: string;
}

export function LoadingState({ rows = 3, label }: LoadingStateProps) {
  const { t } = useTranslation();
  label ??= t('common.loading');
  return (
    <View style={styles.loading} accessibilityRole="progressbar" accessibilityLabel={label} accessibilityLiveRegion="polite">
      {Array.from({ length: rows }, (_, i) => (
        <View key={i} style={styles.skeletonRow}>
          <Skeleton width={40} height={40} radius={radii.md} />
          <View style={styles.skeletonText}>
            <Skeleton width="62%" height={14} />
            <Skeleton width="38%" height={12} />
          </View>
        </View>
      ))}
    </View>
  );
}

export interface EmptyStateProps {
  icon: IconName;
  title: string;
  message?: string;
  actionLabel?: string;
  onAction?: () => void;
  compact?: boolean;
}

export function EmptyState({ icon, title, message, actionLabel, onAction, compact = false }: EmptyStateProps) {
  return (
    <View style={[styles.center, compact ? styles.compact : styles.spacious]} accessibilityRole="summary">
      <View style={styles.iconWrap}>
        <Icon name={icon} size={26} color="accentText" />
      </View>
      <AppText variant="subheading" align="center">
        {title}
      </AppText>
      {message ? (
        <AppText variant="caption" color="textSecondary" align="center" style={styles.message}>
          {message}
        </AppText>
      ) : null}
      {actionLabel && onAction ? (
        <Button label={actionLabel} variant="secondary" size="sm" onPress={onAction} style={styles.action} />
      ) : null}
    </View>
  );
}

export interface ErrorStateProps {
  title?: string;
  message: string;
  onRetry?: () => void;
  retrying?: boolean;
}

export function ErrorState({ title, message, onRetry, retrying = false }: ErrorStateProps) {
  const { t } = useTranslation();
  title ??= t('common.errorTitle');
  return (
    <View style={[styles.center, styles.spacious, styles.errorBox]} accessibilityRole="alert">
      <View style={[styles.iconWrap, styles.errorIcon]}>
        <Icon name="cloud-offline-outline" size={26} color="danger" />
      </View>
      <AppText variant="subheading" align="center">
        {title}
      </AppText>
      <AppText variant="caption" color="textSecondary" align="center" style={styles.message}>
        {message}
      </AppText>
      {onRetry ? (
        <Button label={t('common.tryAgain')} icon="refresh" variant="secondary" size="sm" loading={retrying} onPress={onRetry} style={styles.action} />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  loading: { gap: spacing.lg, paddingVertical: spacing.sm },
  skeletonRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  skeletonText: { flex: 1, gap: spacing.sm },
  center: { alignItems: 'center', justifyContent: 'center', gap: spacing.sm },
  spacious: { paddingVertical: spacing.huge, paddingHorizontal: spacing.xl },
  compact: { paddingVertical: spacing.xxl, paddingHorizontal: spacing.lg },
  iconWrap: {
    width: 56,
    height: 56,
    borderRadius: radii.lg,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.accentSoft,
    marginBottom: spacing.xs,
  },
  errorIcon: { backgroundColor: colors.dangerSoft },
  errorBox: {
    borderRadius: radii.lg,
    borderWidth: 1,
    borderColor: 'rgba(255, 107, 107, 0.25)',
    backgroundColor: colors.surface1,
  },
  message: { maxWidth: 300 },
  action: { marginTop: spacing.sm },
});
