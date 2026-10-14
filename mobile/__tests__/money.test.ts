import {
  amountForDuration,
  centsToDecimal,
  decimalToCents,
  formatMoney,
  isValidDecimal,
  MoneyParseError,
  sumDecimals,
} from '@/shared/lib/money';

describe('decimal parsing', () => {
  it.each([
    ['0', 0],
    ['85', 8500],
    ['85.5', 8550],
    ['85.50', 8550],
    ['0.01', 1],
    ['1234567.89', 123456789],
  ])('%s → %i cents', (input, cents) => {
    expect(decimalToCents(input)).toBe(cents);
  });

  it.each(['', '-1', '1.234', 'abc', '1,50', '.5', '1e3'])('rejects %p', (input) => {
    expect(() => decimalToCents(input)).toThrow(MoneyParseError);
    expect(isValidDecimal(input)).toBe(false);
  });

  it('round-trips cents to decimal strings', () => {
    expect(centsToDecimal(0)).toBe('0.00');
    expect(centsToDecimal(5)).toBe('0.05');
    expect(centsToDecimal(12750)).toBe('127.50');
    expect(() => centsToDecimal(-1)).toThrow(RangeError);
    expect(() => centsToDecimal(1.5)).toThrow(RangeError);
  });
});

describe('amountForDuration — reference vectors from docs/architecture.md §8', () => {
  it.each([
    [1, '100.00', '0.03'],
    [5400, '85.00', '127.50'],
    [3601, '50.00', '50.01'],
    [1200, '33.33', '11.11'],
    [1800, '0.01', '0.01'], // exactly 0.005 → half-up
    [0, '100.00', '0.00'],
  ])('%i s at %s/h = %s', (seconds, rate, expected) => {
    expect(amountForDuration(seconds, rate)).toBe(expected);
  });

  it('rounds half-up, not half-even', () => {
    // 2.5 cents → 3 cents (banker's rounding would give 2)
    expect(amountForDuration(9, '10.00')).toBe('0.03'); // 9 × 1000 / 3600 = 2.5 cents
  });

  it('rejects non-integer seconds', () => {
    expect(() => amountForDuration(1.5, '10.00')).toThrow(RangeError);
  });
});

describe('sumDecimals', () => {
  it('sums without floating point drift', () => {
    expect(sumDecimals(['0.10', '0.20'])).toBe('0.30');
    expect(sumDecimals(Array.from({ length: 1000 }, () => '0.01'))).toBe('10.00');
    expect(sumDecimals([])).toBe('0.00');
  });
});

describe('formatMoney', () => {
  it('formats with currency symbol and two decimals', () => {
    expect(formatMoney('1284.5', 'USD')).toBe('$1,284.50');
    expect(formatMoney('70.00', 'EUR')).toBe('€70.00');
  });

  it('compacts only large values', () => {
    expect(formatMoney('2400.00', 'USD', { compact: true })).toBe('$2,400');
    expect(formatMoney('99.99', 'USD', { compact: true })).toBe('$99.99');
  });
});
