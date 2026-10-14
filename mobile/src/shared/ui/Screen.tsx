import type { ReactNode } from 'react';
import { KeyboardAvoidingView, Platform, RefreshControl, ScrollView, StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';
import { SafeAreaView, type Edge } from 'react-native-safe-area-context';

import { colors, layout, spacing } from '@/shared/theme';

export interface ScreenProps {
  children: ReactNode;
  /** Scrollable content (default). Use false for screens that render their own FlatList. */
  scroll?: boolean;
  /** Safe-area edges. Tab screens without native header need 'top'. */
  edges?: Edge[];
  contentStyle?: StyleProp<ViewStyle>;
  testID?: string;
  /** Enables pull-to-refresh on scrollable screens. */
  onRefresh?: () => void;
  refreshing?: boolean;
  /** Form screens: keep the focused field above the iOS keyboard and let a drag dismiss it. */
  keyboard?: boolean;
}

export function Screen({
  children,
  scroll = true,
  edges = ['top'],
  contentStyle,
  testID,
  onRefresh,
  refreshing = false,
  keyboard = false,
}: ScreenProps) {
  const body = (
    <>
      {scroll ? (
        <ScrollView
          style={styles.flex}
          contentContainerStyle={[styles.content, contentStyle]}
          keyboardShouldPersistTaps="handled"
          keyboardDismissMode={keyboard ? 'interactive' : 'none'}
          showsVerticalScrollIndicator={false}
          refreshControl={
            onRefresh ? (
              <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.accent} colors={[colors.accent]} />
            ) : undefined
          }
        >
          {children}
        </ScrollView>
      ) : (
        <View style={[styles.flex, styles.content, contentStyle]}>{children}</View>
      )}
    </>
  );

  return (
    <SafeAreaView style={styles.safe} edges={edges} testID={testID}>
      {keyboard ? (
        <KeyboardAvoidingView style={styles.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
          {body}
        </KeyboardAvoidingView>
      ) : (
        body
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  flex: { flex: 1 },
  content: {
    width: '100%',
    maxWidth: layout.maxContentWidth,
    alignSelf: 'center',
    paddingHorizontal: layout.screenPadding,
    paddingTop: spacing.md,
    paddingBottom: spacing.huge,
    gap: spacing.xl,
  },
});
