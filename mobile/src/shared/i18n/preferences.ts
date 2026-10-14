import AsyncStorage from '@react-native-async-storage/async-storage';
import { create } from 'zustand';

import i18n, { deviceLanguage } from './index';
import { isAppLanguage, type AppLanguage } from './locale';

/** 'system' follows the device language; otherwise a fixed in-app choice. */
export type LanguagePreference = 'system' | AppLanguage;

const STORAGE_KEY = 'freelancehub.languagePreference';

function isPreference(value: unknown): value is LanguagePreference {
  return value === 'system' || isAppLanguage(value);
}

export function languageFor(preference: LanguagePreference): AppLanguage {
  return preference === 'system' ? deviceLanguage() : preference;
}

interface LanguagePreferenceState {
  preference: LanguagePreference;
  setPreference: (preference: LanguagePreference) => Promise<void>;
}

export const useLanguagePreference = create<LanguagePreferenceState>()((set) => ({
  preference: 'system',
  setPreference: async (preference) => {
    set({ preference });
    await i18n.changeLanguage(languageFor(preference));
    try {
      await AsyncStorage.setItem(STORAGE_KEY, preference);
    } catch {
      // Storage is a convenience: the choice still applies for this session.
    }
  },
}));

/** Reads the saved choice (if any) and applies it. Never throws. */
export async function restoreLanguagePreference(): Promise<void> {
  try {
    const saved = await AsyncStorage.getItem(STORAGE_KEY);
    if (isPreference(saved)) {
      useLanguagePreference.setState({ preference: saved });
      await i18n.changeLanguage(languageFor(saved));
    }
  } catch {
    // Fall back to the device language chosen at init.
  }
}
