import { useEffect, useState } from 'react';
import { AppState } from 'react-native';

/**
 * Returns the current time (ms) and re-renders every `intervalMs` while `enabled`.
 * The interval only triggers re-renders — elapsed time is always derived from timestamps.
 * Also refreshes immediately when the app returns to the foreground.
 */
export function useNow(enabled: boolean, intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!enabled) return;
    const tick = () => setNow(Date.now());
    const immediate = setTimeout(tick, 0); // refresh right away when (re)enabled
    const id = setInterval(tick, intervalMs);
    const sub = AppState.addEventListener('change', (state) => {
      if (state === 'active') setNow(Date.now());
    });
    return () => {
      clearTimeout(immediate);
      clearInterval(id);
      sub.remove();
    };
  }, [enabled, intervalMs]);

  return now;
}
