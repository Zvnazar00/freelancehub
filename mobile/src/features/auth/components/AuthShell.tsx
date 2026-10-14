import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { KeyboardAvoidingView, Platform, StyleSheet, View } from 'react-native';

import { API_BASE_URL } from '@/shared/api/config';
import { AppText, Icon, Screen } from '@/shared/ui';
import { colors, radii, spacing } from '@/shared/theme';

export function AuthShell({ title, subtitle, children, footer, testID }: { title: string; subtitle: string; children: ReactNode; footer: ReactNode; testID?: string }) {
  const { t } = useTranslation();
  return (
    <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <Screen testID={testID} contentStyle={styles.content}>
        <View style={styles.brand}>
          <View style={styles.logo}>
            <Icon name="timer" size={26} color="textOnAccent" />
          </View>
          <AppText variant="subheading">FreelanceHub</AppText>
          <AppText variant="caption" color="textMuted" align="center">
            {t('auth.tagline')}
          </AppText>
        </View>
        <View style={styles.head}>
          <AppText variant="title">{title}</AppText>
          <AppText variant="body" color="textSecondary">
            {subtitle}
          </AppText>
        </View>
        {children}
        <View style={styles.footer}>{footer}</View>
        <View style={styles.meta}>
          <View style={styles.row}>
            <Icon name="lock-closed-outline" size={14} color="textMuted" />
            <AppText variant="caption" color="textMuted" style={styles.flex}>
              {t('auth.secureNote')}
            </AppText>
          </View>
          <AppText variant="monoSmall" color="textMuted" numberOfLines={1}>
            {t('auth.server', { url: API_BASE_URL })}
          </AppText>
        </View>
      </Screen>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.bg },
  content: { gap: spacing.xl, paddingTop: spacing.xxl },
  brand: { alignItems: 'center', gap: spacing.sm },
  logo: {
    width: 56,
    height: 56,
    borderRadius: radii.lg,
    backgroundColor: colors.accentStrong,
    alignItems: 'center',
    justifyContent: 'center',
  },
  head: { gap: spacing.xs },
  footer: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center', alignItems: 'center', gap: spacing.xs },
  meta: { gap: spacing.sm, marginTop: spacing.lg },
  row: { flexDirection: 'row', gap: spacing.sm, alignItems: 'flex-start' },
});
