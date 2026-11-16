/**
 * #11937 (147-A follow-up): while a rate-limited save waits, the grade pages say
 * so in a neutral line that counts down, not in the "Not saved" style.
 */
import '../../helpers/minimalDom';
import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { retryNoticeText } from '@/lib/ranking/gradeSession';
import { useRetryNotice } from '@/lib/ranking/useRetryNotice';

describe('retryNoticeText', () => {
  it('names the seconds left, rounded up, never below one', () => {
    expect(retryNoticeText(41)).toBe('Busy for a moment. Saving again in 41 s…');
    expect(retryNoticeText(0.2)).toBe('Busy for a moment. Saving again in 1 s…');
    expect(retryNoticeText(-3)).toBe('Busy for a moment. Saving again in 1 s…');
  });
  it('never reads as a failure', () => {
    expect(retryNoticeText(5)).not.toMatch(/not saved|error|failed/i);
  });
});

describe('useRetryNotice', () => {
  let root: Root | undefined;
  beforeEach(() => jest.useFakeTimers());
  afterEach(() => { if (root) act(() => root!.unmount()); root = undefined; jest.useRealTimers(); });

  function mount() {
    const result = { current: undefined as unknown as ReturnType<typeof useRetryNotice> };
    const container = document.createElement('div'); document.body.appendChild(container);
    root = createRoot(container);
    function Harness() { result.current = useRetryNotice(); return <>{result.current.notice ?? ''}</>; }
    act(() => { root!.render(<Harness />); });
    return result;
  }

  it('counts down once a second, then clears', () => {
    const result = mount();
    expect(result.current.notice).toBeNull();
    act(() => result.current.startWait(3000));
    expect(result.current.notice).toBe('Busy for a moment. Saving again in 3 s…');
    act(() => { jest.advanceTimersByTime(1000); });
    expect(result.current.notice).toBe('Busy for a moment. Saving again in 2 s…');
    act(() => { jest.advanceTimersByTime(1000); });
    expect(result.current.notice).toBe('Busy for a moment. Saving again in 1 s…');
    act(() => result.current.clearNotice());
    expect(result.current.notice).toBeNull();
  });
});
