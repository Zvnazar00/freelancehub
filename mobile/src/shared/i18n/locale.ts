/**
 * Framework-free source of truth for the active UI language.
 * Formatting helpers in shared/lib read it, so they stay pure and testable without i18next.
 */
export const SUPPORTED_LANGUAGES = ['en', 'uk', 'ru'] as const;
export type AppLanguage = (typeof SUPPORTED_LANGUAGES)[number];

const localeTags: Record<AppLanguage, string> = {
  en: 'en-US',
  uk: 'uk-UA',
  ru: 'ru-RU',
};

let active: AppLanguage = 'en';

export function setActiveLanguage(language: AppLanguage): void {
  active = language;
}

export function activeLanguage(): AppLanguage {
  return active;
}

/** BCP-47 tag used for Intl number/date formatting, e.g. "uk-UA". */
export function localeTagFor(language: AppLanguage = active): string {
  return localeTags[language];
}

export function isAppLanguage(value: unknown): value is AppLanguage {
  return typeof value === 'string' && (SUPPORTED_LANGUAGES as readonly string[]).includes(value);
}

/** First supported language among device language codes (most preferred first); English otherwise. */
export function resolveLanguage(codes: readonly (string | null | undefined)[]): AppLanguage {
  for (const code of codes) {
    const base = code?.toLowerCase().split(/[-_]/)[0];
    if (isAppLanguage(base)) return base;
  }
  return 'en';
}
