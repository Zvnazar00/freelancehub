import AsyncStorage from '@react-native-async-storage/async-storage';
import { fireEvent, render, screen } from '@testing-library/react-native';

import { LanguagePicker } from '@/features/settings/LanguagePicker';
import i18n from '@/shared/i18n';
import { resolveLanguage } from '@/shared/i18n/locale';
import { en } from '@/shared/i18n/locales/en';
import { ru } from '@/shared/i18n/locales/ru';
import { uk } from '@/shared/i18n/locales/uk';
import { restoreLanguagePreference, useLanguagePreference } from '@/shared/i18n/preferences';
import { formatMoney } from '@/shared/lib/money';
import { formatDuration, formatHours, formatLongDay } from '@/shared/lib/time';

type Tree = { [key: string]: string | Tree };

function flatten(tree: Tree, prefix = ''): Record<string, string> {
  return Object.entries(tree).reduce<Record<string, string>>((acc, [k, v]) => {
    const key = prefix ? `${prefix}.${k}` : k;
    return typeof v === 'string' ? { ...acc, [key]: v } : { ...acc, ...flatten(v, key) };
  }, {});
}

const placeholders = (s: string) => [...s.matchAll(/{{\s*(\w+)\s*}}/g)].map((m) => m[1]).sort();

const flat = { en: flatten(en as unknown as Tree), uk: flatten(uk as unknown as Tree), ru: flatten(ru as unknown as Tree) };

afterEach(async () => {
  await i18n.changeLanguage('en');
});

describe('locale files', () => {
  it.each(['uk', 'ru'] as const)('%s has exactly the same keys as en', (lng) => {
    expect(Object.keys(flat[lng]).sort()).toEqual(Object.keys(flat.en).sort());
  });

  it.each(['en', 'uk', 'ru'] as const)('%s has no empty strings', (lng) => {
    expect(Object.entries(flat[lng]).filter(([, v]) => v.trim() === '')).toEqual([]);
  });

  it.each(['uk', 'ru'] as const)('%s keeps every {{placeholder}} of en', (lng) => {
    const mismatches = Object.keys(flat.en).filter(
      (key) => placeholders(flat.en[key] ?? '').join() !== placeholders(flat[lng][key] ?? '').join(),
    );
    expect(mismatches).toEqual([]);
  });
});

describe('plurals', () => {
  it.each([
    ['uk', 1, '1 активний проєкт'],
    ['uk', 3, '3 активні проєкти'],
    ['uk', 5, '5 активних проєктів'],
    ['uk', 21, '21 активний проєкт'],
    ['ru', 1, '1 активный проект'],
    ['ru', 2, '2 активных проекта'],
    ['ru', 11, '11 активных проектов'],
    ['en', 1, '1 active project'],
    ['en', 2, '2 active projects'],
  ] as const)('%s, %i → %s', async (lng, count, expected) => {
    await i18n.changeLanguage(lng);
    expect(i18n.t('clients.activeProjects', { count })).toBe(expected);
  });
});

describe('device language resolution', () => {
  it('picks the first supported language and falls back to English', () => {
    expect(resolveLanguage(['de', 'uk', 'en'])).toBe('uk');
    expect(resolveLanguage(['ru-RU'])).toBe('ru');
    expect(resolveLanguage(['pl', null])).toBe('en');
    expect(resolveLanguage([])).toBe('en');
  });
});

describe('localized formatting follows the active language', () => {
  it('formats durations and hours', async () => {
    expect(formatDuration(5400)).toBe('1h 30m');
    await i18n.changeLanguage('uk');
    expect(formatDuration(5400)).toBe('1 год 30 хв');
    expect(formatHours(50760)).toBe('14,1 год');
    await i18n.changeLanguage('ru');
    expect(formatDuration(45)).toBe('<1 мин');
    expect(formatHours(5400)).toBe('1,5 ч');
  });

  it('formats the date heading with a nominative weekday', async () => {
    const wed = new Date(2026, 9, 14);
    expect(formatLongDay(wed)).toBe('Wednesday, October 14');
    await i18n.changeLanguage('uk');
    expect(formatLongDay(wed)).toBe('середа, 14 жовтня');
    await i18n.changeLanguage('ru');
    expect(formatLongDay(wed)).toBe('среда, 14 октября');
  });

  it('formats money with locale separators but the entry currency', async () => {
    await i18n.changeLanguage('uk');
    expect(formatMoney('1284.50', 'USD')).toMatch(/1\s284,50/);
    expect(formatMoney('1284.50', 'USD')).toContain('$');
  });
});

describe('LanguagePicker', () => {
  it('switches the UI language and persists the choice', async () => {
    await render(<LanguagePicker />);
    expect(screen.getByText('System')).toBeOnTheScreen();

    await fireEvent.press(screen.getByTestId('language-uk'));
    expect(i18n.language).toBe('uk');
    expect(useLanguagePreference.getState().preference).toBe('uk');
    expect(AsyncStorage.setItem).toHaveBeenCalledWith('freelancehub.languagePreference', 'uk');
    expect(screen.getByText('Як у системі')).toBeOnTheScreen();
    expect(screen.getByTestId('language-uk')).toBeChecked();

    await fireEvent.press(screen.getByTestId('language-ru'));
    expect(screen.getByText('Как в системе')).toBeOnTheScreen();
  });

  it('restores a saved preference on startup', async () => {
    await AsyncStorage.setItem('freelancehub.languagePreference', 'ru');
    await restoreLanguagePreference();
    expect(i18n.language).toBe('ru');
    expect(useLanguagePreference.getState().preference).toBe('ru');
  });

  it('ignores garbage in storage', async () => {
    await AsyncStorage.setItem('freelancehub.languagePreference', 'klingon');
    useLanguagePreference.setState({ preference: 'system' });
    await restoreLanguagePreference();
    expect(useLanguagePreference.getState().preference).toBe('system');
  });
});
