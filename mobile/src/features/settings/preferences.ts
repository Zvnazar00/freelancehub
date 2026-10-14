import AsyncStorage from '@react-native-async-storage/async-storage';
import { create } from 'zustand';

/** Device-local UI preferences (not synced, not secret). */
interface AppPreferences {
  longRunningWarning: boolean;
  setLongRunningWarning: (value: boolean) => void;
}

const KEY = 'freelancehub.prefs.v1';

export const useAppPreferences = create<AppPreferences>()((set) => ({
  longRunningWarning: true,
  setLongRunningWarning: (value) => {
    set({ longRunningWarning: value });
    void AsyncStorage.setItem(KEY, JSON.stringify({ longRunningWarning: value })).catch(() => undefined);
  },
}));

export async function restoreAppPreferences(): Promise<void> {
  try {
    const raw = await AsyncStorage.getItem(KEY);
    if (!raw) return;
    const parsed = JSON.parse(raw) as { longRunningWarning?: unknown };
    if (typeof parsed.longRunningWarning === 'boolean') useAppPreferences.setState({ longRunningWarning: parsed.longRunningWarning });
  } catch {
    // defaults
  }
}
