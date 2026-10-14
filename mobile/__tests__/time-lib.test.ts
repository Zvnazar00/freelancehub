import { normalizeTimeZone } from '@/shared/lib/timezone';
import { addDays, formatClock, formatDuration, localDateKey, startOfWeek } from '@/shared/lib/time';

describe('time formatting', () => {
  it('formats clock values', () => {
    expect(formatClock(0)).toBe('00:00:00');
    expect(formatClock(3725)).toBe('01:02:05');
    expect(formatClock(100 * 3600)).toBe('100:00:00');
    expect(formatClock(-5)).toBe('00:00:00');
  });

  it('formats human durations', () => {
    expect(formatDuration(0)).toBe('0m');
    expect(formatDuration(45)).toBe('<1m');
    expect(formatDuration(300)).toBe('5m');
    expect(formatDuration(3600)).toBe('1h');
    expect(formatDuration(5400)).toBe('1h 30m');
  });
});

describe('startOfWeek', () => {
  const sunday = new Date(2026, 9, 11, 15, 30); // Sun Oct 11 2026
  const monday = new Date(2026, 9, 12, 8, 0);

  it('uses Monday as week start', () => {
    expect(localDateKey(startOfWeek(sunday, 1))).toBe('2026-10-05');
    expect(localDateKey(startOfWeek(monday, 1))).toBe('2026-10-12');
  });

  it('uses Sunday as week start', () => {
    expect(localDateKey(startOfWeek(sunday, 7))).toBe('2026-10-11');
    expect(localDateKey(startOfWeek(monday, 7))).toBe('2026-10-11');
  });

  it('adds calendar days across month boundaries', () => {
    expect(localDateKey(addDays(new Date(2026, 9, 31), 1))).toBe('2026-11-01');
  });
});

describe('normalizeTimeZone', () => {
  it('maps CLDR legacy ids to current IANA names', () => {
    expect(normalizeTimeZone('Europe/Kiev')).toBe('Europe/Kyiv');
    expect(normalizeTimeZone('Asia/Calcutta')).toBe('Asia/Kolkata');
    expect(normalizeTimeZone('Europe/Warsaw')).toBe('Europe/Warsaw');
    expect(normalizeTimeZone(undefined)).toBe('UTC');
  });
});
