import { useTranslation } from 'react-i18next';
import { StyleSheet, View } from 'react-native';

import { errorMessageKey, isApiError, type ErrorScope } from '@/shared/api/errors';
import { colors, radii, spacing } from '@/shared/theme';

import { AppText } from './AppText';
import { Icon } from './Icon';

export interface InlineErrorProps {
  error: unknown;
  testID?: string;
  scope?: ErrorScope;
}

/** Translated error banner for any thrown value; shows the request ID for server errors (support reference). */
export function InlineError({ error, testID, scope }: InlineErrorProps) {
  const { t } = useTranslation();
  if (!error) return null;
  const reference = isApiError(error) && error.status >= 500 ? error.requestId : null;
  return (
    <View style={styles.box} accessibilityRole="alert" accessibilityLiveRegion="polite" testID={testID}>
      <Icon name="alert-circle" size={16} color="danger" />
      <View style={styles.text}>
        <AppText variant="caption" color="danger">
          {t(errorMessageKey(error, scope))}
        </AppText>
        {reference ? (
          <AppText variant="monoSmall" color="textMuted">
            {t('errors.reference', { id: reference })}
          </AppText>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  box: { flexDirection: 'row', gap: spacing.sm, padding: spacing.md, borderRadius: radii.md, backgroundColor: colors.dangerSoft },
  text: { flex: 1, gap: 2 },
});
