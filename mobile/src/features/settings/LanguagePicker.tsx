import { useTranslation } from 'react-i18next';
import { Pressable, StyleSheet, View } from 'react-native';

import { deviceLanguage, SUPPORTED_LANGUAGES } from '@/shared/i18n';
import { useLanguagePreference, type LanguagePreference } from '@/shared/i18n/preferences';
import { AppText, Icon } from '@/shared/ui';
import { colors, spacing } from '@/shared/theme';

/** Radio list: "System" + every supported language, each shown in its own language. */
export function LanguagePicker() {
  const { t } = useTranslation();
  const preference = useLanguagePreference((s) => s.preference);
  const setPreference = useLanguagePreference((s) => s.setPreference);

  const options: { value: LanguagePreference; label: string; hint?: string }[] = [
    {
      value: 'system',
      label: t('settings.languageSystem'),
      hint: t('settings.languageSystemHint', { language: t(`languages.${deviceLanguage()}`) }),
    },
    ...SUPPORTED_LANGUAGES.map((lng) => ({ value: lng, label: t(`languages.${lng}`) })),
  ];

  return (
    <View accessibilityRole="radiogroup" accessibilityLabel={t('settings.language')}>
      {options.map((option, i) => {
        const selected = option.value === preference;
        return (
          <Pressable
            key={option.value}
            testID={`language-${option.value}`}
            accessibilityRole="radio"
            accessibilityState={{ checked: selected }}
            accessibilityLabel={option.hint ? `${option.label}, ${option.hint}` : option.label}
            onPress={() => void setPreference(option.value)}
            style={({ pressed }) => [styles.row, i < options.length - 1 && styles.divider, pressed && styles.pressed]}
          >
            <View style={styles.text}>
              <AppText variant="bodyMedium">{option.label}</AppText>
              {option.hint ? (
                <AppText variant="caption" color="textMuted">
                  {option.hint}
                </AppText>
              ) : null}
            </View>
            <View style={[styles.radio, selected && styles.radioSelected]}>
              {selected ? <Icon name="checkmark" size={14} color="textOnAccent" /> : null}
            </View>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    minHeight: 56,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
  },
  divider: { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  pressed: { backgroundColor: colors.surface2 },
  text: { flex: 1, gap: 2 },
  radio: {
    width: 22,
    height: 22,
    borderRadius: 11,
    borderWidth: 1.5,
    borderColor: colors.borderStrong,
    alignItems: 'center',
    justifyContent: 'center',
  },
  radioSelected: { backgroundColor: colors.accentStrong, borderColor: colors.accentStrong },
});
