import { useState, type ReactNode, type Ref } from 'react';
import { StyleSheet, TextInput, View, type TextInputProps } from 'react-native';

import { colors, fontFamilies, radii, spacing } from '@/shared/theme';

import { AppText } from './AppText';
import { Icon, type IconName } from './Icon';

export interface InputProps extends Omit<TextInputProps, 'style' | 'placeholderTextColor'> {
  label?: string;
  helper?: string;
  error?: string;
  leftIcon?: IconName;
  right?: ReactNode;
  /** Use a monospaced, tabular font (amounts, rates, times). */
  mono?: boolean;
  ref?: Ref<TextInput>;
}

export function Input({
  label,
  helper,
  error,
  leftIcon,
  right,
  mono = false,
  editable = true,
  onFocus,
  onBlur,
  accessibilityLabel,
  ref,
  ...rest
}: InputProps) {
  const [focused, setFocused] = useState(false);
  const borderColor = error ? colors.danger : focused ? colors.accent : colors.border;

  return (
    <View style={styles.wrapper}>
      {label ? (
        <AppText variant="captionMedium" color="textSecondary">
          {label}
        </AppText>
      ) : null}
      {/*
        The focus ring only animates values (shadowOpacity, borderColor); the props that decide the native view
        hierarchy stay constant. On Fabric (iOS) adding/removing shadowColor flips "forms stacking context", which
        re-parents the native TextInput — UIKit then resigns first responder and the keyboard closes on focus or on
        the first keystroke. collapsable={false} pins the view regardless of future style tweaks.
      */}
      <View
        collapsable={false}
        style={[
          styles.field,
          { borderColor, backgroundColor: editable ? colors.surface2 : colors.surface1 },
          { shadowOpacity: focused && !error ? 0.35 : 0 },
        ]}
      >
        {leftIcon ? <Icon name={leftIcon} size={18} color={focused ? 'accentText' : 'textMuted'} /> : null}
        <TextInput
          ref={ref}
          editable={editable}
          accessibilityLabel={accessibilityLabel ?? label}
          accessibilityHint={error ?? helper}
          placeholderTextColor={colors.textMuted}
          selectionColor={colors.accent}
          cursorColor={colors.accent}
          onFocus={(e) => {
            setFocused(true);
            onFocus?.(e);
          }}
          onBlur={(e) => {
            setFocused(false);
            onBlur?.(e);
          }}
          style={[styles.input, { fontFamily: mono ? fontFamilies.mono : fontFamilies.regular }, !editable && styles.disabledText]}
          {...rest}
        />
        {right}
      </View>
      {error ? (
        <View style={styles.messageRow} accessibilityLiveRegion="polite">
          <Icon name="alert-circle" size={14} color="danger" />
          <AppText variant="caption" color="danger">
            {error}
          </AppText>
        </View>
      ) : helper ? (
        <AppText variant="caption" color="textMuted">
          {helper}
        </AppText>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: { gap: spacing.xs + 2 },
  field: {
    minHeight: 48,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.md,
    borderRadius: radii.md,
    borderWidth: 1,
    // Shadow geometry is always present (see the comment in the render); focus only changes shadowOpacity.
    shadowColor: colors.accent,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 0 },
  },
  input: {
    flex: 1,
    color: colors.textPrimary,
    fontSize: 15,
    paddingVertical: spacing.md,
  },
  disabledText: { color: colors.textMuted },
  messageRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
});
