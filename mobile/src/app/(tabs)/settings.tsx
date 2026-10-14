import Constants from 'expo-constants';
import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Platform, StyleSheet, Switch, View } from 'react-native';

import { deviceTimeZone, signOut, signOutEverywhere, updateProfile } from '@/features/auth/session';
import { useCurrentUser } from '@/features/auth/store';
import { LanguagePicker } from '@/features/settings/LanguagePicker';
import { useAppPreferences } from '@/features/settings/preferences';
import { useReachability } from '@/shared/api';
import { API_BASE_URL } from '@/shared/api/config';
import {
  AppText,
  Avatar,
  Button,
  Card,
  InlineError,
  ListRow,
  OfflineBanner,
  Screen,
  ScreenHeader,
  SectionHeader,
  SegmentedControl,
} from '@/shared/ui';
import { colors, spacing } from '@/shared/theme';

export default function SettingsScreen() {
  const { t } = useTranslation();
  const user = useCurrentUser();
  const reachable = useReachability((s) => s.reachable);
  const longRunningWarning = useAppPreferences((s) => s.longRunningWarning);
  const setLongRunningWarning = useAppPreferences((s) => s.setLongRunningWarning);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState<'signOut' | 'signOutAll' | 'profile' | null>(null);
  const [confirmAll, setConfirmAll] = useState(false);
  const deviceTz = deviceTimeZone();

  useEffect(() => {
    if (!confirmAll) return;
    const id = setTimeout(() => setConfirmAll(false), 4000);
    return () => clearTimeout(id);
  }, [confirmAll]);

  const run = async (kind: NonNullable<typeof busy>, action: () => Promise<unknown>) => {
    setError(null);
    setBusy(kind);
    try {
      await action();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  };

  return (
    <Screen testID="settings-screen">
      <ScreenHeader title={t('settings.title')} />
      <OfflineBanner />

      <Card>
        <View style={styles.profile}>
          <Avatar name={user.fullName} size={56} />
          <View style={styles.profileText}>
            <AppText variant="heading" numberOfLines={1}>
              {user.fullName}
            </AppText>
            <AppText variant="caption" color="textSecondary" numberOfLines={1} testID="settings-email">
              {user.email}
            </AppText>
          </View>
        </View>
      </Card>

      <InlineError error={error} testID="settings-error" />

      <View style={styles.section}>
        <SectionHeader title={t('settings.billing')} />
        <Card padding="none">
          <ListRow icon="document-text-outline" label={t('screens.invoices')} description={t('settings.invoicesHint')} onPress={() => router.push('/invoices')} />
          <ListRow
            icon="analytics-outline"
            label={t('screens.analytics')}
            description={t('settings.analyticsHint')}
            onPress={() => router.push('/analytics')}
            showDivider={false}
          />
        </Card>
      </View>

      <View style={styles.section}>
        <SectionHeader title={t('settings.language')} />
        <Card padding="none">
          <LanguagePicker />
        </Card>
      </View>

      <View style={styles.section}>
        <SectionHeader title={t('settings.preferences')} />
        <Card padding="none">
          <View style={styles.block}>
            <AppText variant="bodyMedium">{t('settings.weekStartsOn')}</AppText>
            <SegmentedControl<'1' | '7'>
              accessibilityLabel={t('settings.weekStartsOn')}
              value={String(user.weekStart) as '1' | '7'}
              onChange={(v) => void run('profile', () => updateProfile({ week_start: v === '7' ? 7 : 1 }))}
              options={[
                { value: '1', label: t('settings.monday') },
                { value: '7', label: t('settings.sunday') },
              ]}
            />
          </View>
          <ListRow
            icon="hourglass-outline"
            label={t('settings.longRunning')}
            description={t('settings.longRunningHint')}
            right={
              <Switch
                accessibilityLabel={t('settings.longRunning')}
                value={longRunningWarning}
                onValueChange={setLongRunningWarning}
                trackColor={{ false: colors.surface3, true: colors.accent }}
                thumbColor={colors.textPrimary}
                ios_backgroundColor={colors.surface3}
              />
            }
          />
          <ListRow icon="cash-outline" label={t('settings.defaultCurrency')} value={user.defaultCurrency} />
          <ListRow
            icon="globe-outline"
            label={t('settings.timeZone')}
            value={user.timezone}
            description={user.timezone !== deviceTz ? t('settings.deviceTimeZone', { tz: deviceTz }) : undefined}
            showDivider={user.timezone !== deviceTz}
          />
          {user.timezone !== deviceTz ? (
            <View style={styles.block}>
              <Button
                label={t('settings.useDeviceTimeZone')}
                icon="locate-outline"
                variant="secondary"
                size="sm"
                loading={busy === 'profile'}
                onPress={() => void run('profile', () => updateProfile({ timezone: deviceTz }))}
              />
            </View>
          ) : null}
        </Card>
      </View>

      <View style={styles.section}>
        <SectionHeader title={t('settings.connection')} />
        <Card padding="none">
          <ListRow icon="server-outline" label={t('settings.server')} value={API_BASE_URL.replace(/^https?:\/\//, '')} />
          <ListRow
            icon={reachable ? 'cloud-done-outline' : 'cloud-offline-outline'}
            label={t('settings.connection')}
            value={t(reachable ? 'settings.online' : 'settings.offline')}
          />
          <ListRow
            icon="key-outline"
            label={t('settings.session')}
            value={t(Platform.OS === 'web' ? 'settings.memoryOnly' : 'settings.secureStore')}
            showDivider={false}
          />
        </Card>
      </View>

      <View style={styles.section}>
        <SectionHeader title={t('settings.account')} />
        <Button
          testID="sign-out"
          label={t('settings.signOut')}
          icon="log-out-outline"
          variant="secondary"
          fullWidth
          loading={busy === 'signOut'}
          onPress={() => void run('signOut', signOut)}
        />
        <Button
          testID="sign-out-all"
          label={t(confirmAll ? 'settings.signOutAllConfirm' : 'settings.signOutAll')}
          icon="shield-outline"
          variant={confirmAll ? 'danger' : 'ghost'}
          fullWidth
          loading={busy === 'signOutAll'}
          onPress={() => {
            if (!confirmAll) {
              setConfirmAll(true);
              return;
            }
            setConfirmAll(false);
            void run('signOutAll', signOutEverywhere);
          }}
        />
        <AppText variant="caption" color="textMuted" align="center">
          {t('settings.signOutAllHint')}
        </AppText>
      </View>

      <View style={styles.section}>
        <SectionHeader title={t('settings.developer')} />
        <Card padding="none">
          <ListRow
            icon="color-palette-outline"
            label={t('settings.designSystem')}
            description={t('settings.designSystemHint')}
            onPress={() => router.push('/settings/components')}
            showDivider={false}
          />
        </Card>
      </View>

      <View style={styles.section}>
        <SectionHeader title={t('settings.about')} />
        <Card padding="none">
          <ListRow icon="information-circle-outline" label={t('settings.version')} value={Constants.expoConfig?.version ?? '—'} />
          <ListRow icon="construct-outline" label={t('settings.buildStage')} value={t('settings.buildStageValue')} showDivider={false} />
        </Card>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  profileText: { flex: 1, gap: spacing.xs },
  profile: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  section: { gap: spacing.md },
  block: {
    gap: spacing.md,
    padding: spacing.lg,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
});
