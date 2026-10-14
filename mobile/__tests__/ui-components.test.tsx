import { fireEvent, render, screen } from '@testing-library/react-native';

import { TimerControls } from '@/features/timer/components/TimerControls';
import { Button, EmptyState, ErrorState, Input } from '@/shared/ui';

describe('Button', () => {
  it('fires onPress and exposes an accessible role', async () => {
    const onPress = jest.fn();
    await render(<Button label="Save" onPress={onPress} />);
    await fireEvent.press(screen.getByRole('button', { name: 'Save' }));
    expect(onPress).toHaveBeenCalledTimes(1);
  });

  it('does not fire when disabled or loading', async () => {
    const onPress = jest.fn();
    await render(
      <>
        <Button label="Disabled" disabled onPress={onPress} />
        <Button label="Busy" loading onPress={onPress} />
      </>,
    );
    await fireEvent.press(screen.getByRole('button', { name: 'Disabled' }));
    await fireEvent.press(screen.getByRole('button', { name: 'Busy' }));
    expect(onPress).not.toHaveBeenCalled();
  });
});

describe('Input', () => {
  it('shows an error message instead of helper text', async () => {
    await render(<Input label="Email" helper="We never share it" error="Enter a valid email" value="x" onChangeText={() => undefined} />);
    expect(screen.getByText('Enter a valid email')).toBeOnTheScreen();
    expect(screen.queryByText('We never share it')).toBeNull();
  });
});

describe('state views', () => {
  it('EmptyState renders an action', async () => {
    const onAction = jest.fn();
    await render(<EmptyState icon="folder-open-outline" title="No projects" message="Nothing here" actionLabel="Create" onAction={onAction} />);
    await fireEvent.press(screen.getByRole('button', { name: 'Create' }));
    expect(onAction).toHaveBeenCalled();
  });

  it('ErrorState offers retry', async () => {
    const onRetry = jest.fn();
    await render(<ErrorState message="Network failed" onRetry={onRetry} />);
    expect(screen.getByText('Network failed')).toBeOnTheScreen();
    await fireEvent.press(screen.getByRole('button', { name: 'Try again' }));
    expect(onRetry).toHaveBeenCalled();
  });
});

describe('TimerControls', () => {
  const handlers = () => ({
    onStart: jest.fn(),
    onPause: jest.fn(),
    onResume: jest.fn(),
    onStop: jest.fn(),
    onDiscard: jest.fn(),
  });

  it('shows Start when idle and respects startDisabled', async () => {
    const h = handlers();
    await render(<TimerControls status="idle" startDisabled {...h} />);
    await fireEvent.press(screen.getByTestId('timer-start'));
    expect(h.onStart).not.toHaveBeenCalled();
  });

  it('switches between Pause and Resume', async () => {
    const h = handlers();
    const { rerender } = await render(<TimerControls status="running" {...h} />);
    await fireEvent.press(screen.getByTestId('timer-pause'));
    expect(h.onPause).toHaveBeenCalled();
    await rerender(<TimerControls status="paused" {...h} />);
    await fireEvent.press(screen.getByTestId('timer-resume'));
    expect(h.onResume).toHaveBeenCalled();
  });

  it('requires a second tap to discard', async () => {
    const h = handlers();
    await render(<TimerControls status="running" {...h} />);
    await fireEvent.press(screen.getByTestId('timer-discard'));
    expect(h.onDiscard).not.toHaveBeenCalled();
    expect(screen.getByText('Tap again to discard this entry')).toBeOnTheScreen();
    await fireEvent.press(screen.getByTestId('timer-discard'));
    expect(h.onDiscard).toHaveBeenCalledTimes(1);
  });
});
