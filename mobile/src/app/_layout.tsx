import {
  Inter_400Regular,
  Inter_500Medium,
  Inter_600SemiBold,
  Inter_700Bold,
  useFonts,
} from '@expo-google-fonts/inter';
import { JetBrainsMono_500Medium, JetBrainsMono_700Bold } from '@expo-google-fonts/jetbrains-mono';
import { QueryClientProvider } from '@tanstack/react-query';
import { useLocales } from 'expo-localization';
import { DarkTheme, Stack, ThemeProvider, type Theme } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { restoreSession } from '@/features/auth/session';
import { useAuth } from '@/features/auth/store';
import { restoreAppPreferences } from '@/features/settings/preferences';
import { queryClient } from '@/shared/api';
import { bindFocusToAppState } from '@/shared/api/queryClient';
import i18n from '@/shared/i18n'; // importing initialises i18next before any screen renders
import { languageFor, restoreLanguagePreference, useLanguagePreference } from '@/shared/i18n/preferences';
import { colors, fontFamilies } from '@/shared/theme';
import { ErrorState, Screen } from '@/shared/ui';

SplashScreen.preventAutoHideAsync().catch(() => {
  /* splash already hidden (e.g. fast refresh) */
});

const navigationTheme: Theme = {
  ...DarkTheme,
  colors: {
    ...DarkTheme.colors,
    primary: colors.accent,
    background: colors.bg,
    card: colors.surface1,
    text: colors.textPrimary,
    border: colors.border,
    notification: colors.accent,
  },
};

export default function RootLayout() {
  const [fontsLoaded, fontError] = useFonts({
    Inter_400Regular,
    Inter_500Medium,
    Inter_600SemiBold,
    Inter_700Bold,
    JetBrainsMono_500Medium,
    JetBrainsMono_700Bold,
  });
  const { t } = useTranslation();
  const [languageRestored, setLanguageRestored] = useState(false);
  const preference = useLanguagePreference((s) => s.preference);
  const deviceLocales = useLocales();
  const authStatus = useAuth((s) => s.status);
  const [retrying, setRetrying] = useState(false);

  // Restore the session (keystore refresh token → fresh access token) while the splash screen is up.
  useEffect(() => {
    void restoreAppPreferences();
    void restoreSession();
    return bindFocusToAppState();
  }, []);

  // Apply the saved language before the splash screen hides, so the UI never flashes in another language.
  useEffect(() => {
    void restoreLanguagePreference().finally(() => setLanguageRestored(true));
  }, []);

  // With "system" selected, follow device language changes made while the app is running.
  useEffect(() => {
    if (!languageRestored || preference !== 'system') return;
    const next = languageFor('system');
    if (i18n.language !== next) void i18n.changeLanguage(next);
  }, [deviceLocales, preference, languageRestored]);

  // If fonts fail to load we still render with system fonts rather than blocking the app.
  const ready = (fontsLoaded || fontError !== null) && languageRestored && authStatus !== 'restoring';

  useEffect(() => {
    if (ready) SplashScreen.hideAsync().catch(() => undefined);
  }, [ready]);

  if (!ready && !retrying) return null;

  const signedIn = authStatus === 'signedIn';

  return (
    <QueryClientProvider client={queryClient}>
    <SafeAreaProvider>
      <ThemeProvider value={navigationTheme}>
        <StatusBar style="light" />
        {authStatus === 'unreachable' || (retrying && authStatus === 'restoring') ? (
          <Screen testID="unreachable-screen">
            <ErrorState
              title={t('auth.unreachableTitle')}
              message={t('auth.unreachableHint')}
              retrying={retrying}
              onRetry={() => {
                setRetrying(true);
                void restoreSession().finally(() => setRetrying(false));
              }}
            />
          </Screen>
        ) : (
        <Stack
          screenOptions={{
            headerStyle: { backgroundColor: colors.bg },
            headerTintColor: colors.textPrimary,
            headerTitleStyle: { fontFamily: fontFamilies.semibold, fontSize: 17 },
            headerShadowVisible: false,
            headerBackButtonDisplayMode: 'minimal',
            contentStyle: { backgroundColor: colors.bg },
          }}
        >
          {/* Protected routes: unreachable without a session; the router redirects to the first allowed screen. */}
          <Stack.Protected guard={signedIn}>
            <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
            <Stack.Screen name="projects/[id]" options={{ title: t('screens.project') }} />
            <Stack.Screen name="projects/new" options={{ title: t('screens.newProject') }} />
            <Stack.Screen name="clients/[id]" options={{ title: t('screens.client') }} />
            <Stack.Screen name="clients/new" options={{ title: t('screens.newClient') }} />
            <Stack.Screen name="settings/components" options={{ title: t('screens.designSystem') }} />
            <Stack.Screen name="analytics" options={{ title: t('screens.analytics') }} />
            <Stack.Screen name="invoices/index" options={{ title: t('screens.invoices') }} />
            <Stack.Screen name="invoices/new" options={{ title: t('screens.newInvoice') }} />
            <Stack.Screen name="invoices/[id]" options={{ title: t('screens.invoice') }} />
            <Stack.Screen name="invoices/edit/[id]" options={{ title: t('screens.editInvoice') }} />
          </Stack.Protected>
          <Stack.Protected guard={!signedIn}>
            <Stack.Screen name="(auth)" options={{ headerShown: false }} />
          </Stack.Protected>
          <Stack.Screen name="+not-found" options={{ title: t('screens.notFound') }} />
        </Stack>
        )}
      </ThemeProvider>
    </SafeAreaProvider>
    </QueryClientProvider>
  );
}
