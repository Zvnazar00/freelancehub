import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { StyleSheet, View } from 'react-native';

import {
  AppText,
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  IconButton,
  Input,
  LoadingState,
  ProgressBar,
  Screen,
  SectionHeader,
  SegmentedControl,
  Skeleton,
} from '@/shared/ui';
import { colors, palette, spacing, typography, type TypographyVariant } from '@/shared/theme';

/** Living style guide for the Dark Developer design system. No data, no backend. */
export default function DesignSystemScreen() {
  const { t } = useTranslation();
  const [segment, setSegment] = useState<'a' | 'b' | 'c'>('a');
  const [retrying, setRetrying] = useState(false);
  const [text, setText] = useState('');

  const swatches = [
    ['bg', colors.bg],
    ['surface1', colors.surface1],
    ['surface2', colors.surface2],
    ['surface3', colors.surface3],
    ['accent', colors.accent],
    ['info', colors.info],
    ['success', colors.success],
    ['warning', colors.warning],
    ['danger', colors.danger],
    ['text', palette.gray300],
  ] as const;

  return (
    <Screen edges={['bottom']} testID="design-system-screen">
      <View style={styles.section}>
        <SectionHeader title={t('gallery.colors')} />
        <View style={styles.swatches}>
          {swatches.map(([name, value]) => (
            <View key={name} style={styles.swatchItem}>
              <View style={[styles.swatch, { backgroundColor: value }]} />
              <AppText variant="caption" color="textSecondary">
                {name}
              </AppText>
              <AppText variant="monoSmall" color="textMuted" style={styles.hex}>
                {value}
              </AppText>
            </View>
          ))}
        </View>
      </View>

      <View style={styles.section}>
        <SectionHeader title={t('gallery.typography')} />
        <Card style={styles.stack}>
          {(Object.keys(typography) as TypographyVariant[])
            .filter((v) => v !== 'timer')
            .map((variant) => (
              <AppText key={variant} variant={variant} numberOfLines={1}>
                {variant} · {variant.startsWith('mono') ? '01:42:07 $1,284.50' : t('gallery.sample')}
              </AppText>
            ))}
        </Card>
      </View>

      <View style={styles.section}>
        <SectionHeader title={t('gallery.buttons')} />
        <Card style={styles.stack}>
          <Button label={t('gallery.primary')} icon="play" fullWidth onPress={() => undefined} />
          <View style={styles.row}>
            <Button label={t('gallery.secondary')} variant="secondary" style={styles.flex} onPress={() => undefined} />
            <Button label={t('gallery.danger')} variant="danger" style={styles.flex} onPress={() => undefined} />
          </View>
          <View style={styles.row}>
            <Button label={t('gallery.ghost')} variant="ghost" size="sm" onPress={() => undefined} />
            <Button label={t('gallery.loading')} size="sm" loading onPress={() => undefined} />
            <Button label={t('gallery.disabled')} size="sm" disabled onPress={() => undefined} />
            <IconButton icon="add" variant="accent" accessibilityLabel={t('gallery.add')} onPress={() => undefined} />
          </View>
        </Card>
      </View>

      <View style={styles.section}>
        <SectionHeader title={t('gallery.inputs')} />
        <Card style={styles.stack}>
          <Input label={t('gallery.inputDefault')} placeholder={t('gallery.inputDefaultPlaceholder')} value={text} onChangeText={setText} />
          <Input label={t('gallery.inputIcon')} placeholder={t('gallery.inputSearch')} leftIcon="search" />
          <Input label={t('gallery.inputAmount')} placeholder="85.00" mono keyboardType="decimal-pad" helper={t('gallery.inputAmountHelper')} />
          <Input label={t('gallery.inputError')} value="not-an-email" error={t('clientForm.errors.emailInvalid')} onChangeText={() => undefined} />
          <Input label={t('gallery.inputDisabled')} value={t('gallery.readOnly')} editable={false} />
        </Card>
      </View>

      <View style={styles.section}>
        <SectionHeader title={t('gallery.badges')} />
        <Card style={styles.stack}>
          <View style={styles.wrap}>
            <Badge label={t('gallery.neutral')} />
            <Badge label={t('gallery.accent')} tone="accent" />
            <Badge label={t('gallery.info')} tone="info" />
            <Badge label={t('gallery.active')} tone="success" dot />
            <Badge label={t('gallery.onHold')} tone="warning" />
            <Badge label={t('gallery.overdue')} tone="danger" />
          </View>
          <SegmentedControl
            accessibilityLabel={t('gallery.exampleSegments')}
            value={segment}
            onChange={setSegment}
            options={[
              { value: 'a', label: t('gallery.week'), count: 7 },
              { value: 'b', label: t('gallery.month') },
              { value: 'c', label: t('gallery.year') },
            ]}
          />
          <ProgressBar value={0.42} accessibilityLabel={t('gallery.percent', { percent: 42 })} />
          <ProgressBar value={0.9} color={colors.warning} accessibilityLabel={t('gallery.percent', { percent: 90 })} />
          <ProgressBar value={1.2} accessibilityLabel={t('gallery.overBudget', { percent: 120 })} />
        </Card>
      </View>

      <View style={styles.section}>
        <SectionHeader title={t('gallery.cards')} />
        <Card>
          <AppText variant="subheading">{t('gallery.surface')}</AppText>
        </Card>
        <Card variant="raised">
          <AppText variant="subheading">{t('gallery.raised')}</AppText>
        </Card>
        <Card variant="accent">
          <AppText variant="subheading">{t('gallery.accent')}</AppText>
        </Card>
        <Card variant="outline">
          <AppText variant="subheading" color="textSecondary">
            {t('gallery.outline')}
          </AppText>
        </Card>
      </View>

      <View style={styles.section}>
        <SectionHeader title={t('gallery.loadingState')} />
        <Card>
          <LoadingState rows={3} />
          <View style={styles.skeletons}>
            <Skeleton width="40%" height={24} />
            <Skeleton height={60} />
          </View>
        </Card>
      </View>

      <View style={styles.section}>
        <SectionHeader title={t('gallery.emptyState')} />
        <Card>
          <EmptyState icon="folder-open-outline" title={t('gallery.emptyTitle')} message={t('gallery.emptyHint')} actionLabel={t('gallery.emptyAction')} onAction={() => undefined} />
        </Card>
      </View>

      <View style={styles.section}>
        <SectionHeader title={t('gallery.errorState')} />
        <ErrorState
          title={t('gallery.errorTitle')}
          message={t('gallery.errorHint')}
          retrying={retrying}
          onRetry={() => {
            setRetrying(true);
            setTimeout(() => setRetrying(false), 1200);
          }}
        />
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  section: { gap: spacing.md },
  stack: { gap: spacing.md },
  row: { flexDirection: 'row', gap: spacing.sm, alignItems: 'center', flexWrap: 'wrap' },
  wrap: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  flex: { flex: 1 },
  swatches: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.md },
  swatchItem: { width: '30%', gap: 4 },
  swatch: { height: 48, borderRadius: 10, borderWidth: 1, borderColor: colors.border },
  hex: { fontSize: 11 },
  skeletons: { gap: spacing.sm, marginTop: spacing.lg },
});
