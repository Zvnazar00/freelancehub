import { canGoForward, chartInterval, containsDay, periodContaining, periodLabel, shiftPeriod } from '@/features/analytics/range';

const d = (y: number, m: number, day: number) => new Date(y, m - 1, day);
const quarter = (q: number, y: number) => `Q${q} ${y}`;

describe('analytics periods', () => {
  it('builds calendar periods around a day', () => {
    expect(periodContaining('week', d(2026, 10, 14), 1)).toEqual({ kind: 'week', from: '2026-10-12', to: '2026-10-18' });
    expect(periodContaining('week', d(2026, 10, 14), 7)).toEqual({ kind: 'week', from: '2026-10-11', to: '2026-10-17' });
    expect(periodContaining('month', d(2026, 2, 10), 1)).toEqual({ kind: 'month', from: '2026-02-01', to: '2026-02-28' });
    expect(periodContaining('month', d(2028, 2, 10), 1).to).toBe('2028-02-29');
    expect(periodContaining('quarter', d(2026, 11, 3), 1)).toEqual({ kind: 'quarter', from: '2026-10-01', to: '2026-12-31' });
    expect(periodContaining('year', d(2026, 6, 6), 1)).toEqual({ kind: 'year', from: '2026-01-01', to: '2026-12-31' });
  });

  it('navigates without drifting across month lengths and years', () => {
    const jan = periodContaining('month', d(2026, 1, 31), 1);
    expect(shiftPeriod(jan, 1, 1)).toEqual({ kind: 'month', from: '2026-02-01', to: '2026-02-28' });
    expect(shiftPeriod(jan, -1, 1)).toEqual({ kind: 'month', from: '2025-12-01', to: '2025-12-31' });
    const q1 = periodContaining('quarter', d(2026, 2, 1), 1);
    expect(shiftPeriod(q1, -1, 1)).toEqual({ kind: 'quarter', from: '2025-10-01', to: '2025-12-31' });
    const week = periodContaining('week', d(2026, 12, 30), 1);
    expect(shiftPeriod(week, 1, 1)).toEqual({ kind: 'week', from: '2027-01-04', to: '2027-01-10' });
    expect(shiftPeriod(periodContaining('year', d(2026, 1, 1), 1), -2, 1).from).toBe('2024-01-01');
  });

  it('stops at the current period and knows which day it contains', () => {
    const today = d(2026, 10, 12);
    const current = periodContaining('month', today, 1);
    expect(canGoForward(current, today)).toBe(false);
    expect(canGoForward(shiftPeriod(current, -1, 1), today)).toBe(true);
    expect(containsDay(current, today)).toBe(true);
    expect(containsDay(shiftPeriod(current, -1, 1), today)).toBe(false);
  });

  it('picks a readable chart interval and labels', () => {
    expect(chartInterval('week')).toBe('day');
    expect(chartInterval('month')).toBe('day');
    expect(chartInterval('quarter')).toBe('week');
    expect(chartInterval('year')).toBe('month');
    expect(periodLabel(periodContaining('quarter', d(2026, 11, 3), 1), quarter, 'en')).toBe('Q4 2026');
    expect(periodLabel(periodContaining('year', d(2026, 11, 3), 1), quarter, 'en')).toBe('2026');
    expect(periodLabel(periodContaining('month', d(2026, 10, 3), 1), quarter, 'en')).toBe('October 2026');
    expect(periodLabel(periodContaining('week', d(2026, 10, 14), 1), quarter, 'en')).toBe('Oct 12 – Oct 18 2026');
  });
});
