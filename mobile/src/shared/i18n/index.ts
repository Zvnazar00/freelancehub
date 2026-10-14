// Hermes lacks a complete Intl.PluralRules; the polyfill only installs itself when needed.
import 'intl-pluralrules';

import { getLocales } from 'expo-localization';
import { createInstance, type ParseKeys } from 'i18next';
import { initReactI18next } from 'react-i18next';

import { en } from './locales/en';
import { ru } from './locales/ru';
import { uk } from './locales/uk';
import { isAppLanguage, resolveLanguage, setActiveLanguage, SUPPORTED_LANGUAGES, type AppLanguage } from './locale';

export { activeLanguage, isAppLanguage, localeTagFor, SUPPORTED_LANGUAGES, type AppLanguage } from './locale';

/** Any valid translation key (type-checked against locales/en.ts). */
export type TxKey = ParseKeys;

/** Best supported language from the device settings. */
export function deviceLanguage(): AppLanguage {
  try {
    return resolveLanguage(getLocales().map((l) => l.languageCode));
  } catch {
    return 'en';
  }
}

const i18n = createInstance();
const initial = deviceLanguage();
setActiveLanguage(initial);

i18n.on('languageChanged', (lng) => {
  if (isAppLanguage(lng)) setActiveLanguage(lng);
});

void i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    uk: { translation: uk },
    ru: { translation: ru },
  },
  lng: initial,
  fallbackLng: 'en',
  supportedLngs: [...SUPPORTED_LANGUAGES],
  interpolation: { escapeValue: false }, // React already escapes
  returnNull: false,
  initAsync: false, // resources are bundled, so init synchronously
});

export default i18n;
