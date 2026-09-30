import { useEffect, useRef, type MouseEvent } from 'react';

const HISTORY_KEY = '__blSearchReturn';
const MAX_AGE_MS = 30 * 60 * 1000;
interface ReturnMark {
  key: string;
  href: string;
  top: number;
  y: number;
  savedAt: number;
}

/** #9731: the mark belongs to one history entry, not to every search with the
 * same text. Keep Next's router state intact. Results still refetch normally;
 * the landing waits for the matching response to be committed to the DOM. */
export function useSearchResultRestoration(key: string, resultsReady: boolean) {
  const pending = useRef<ReturnMark | null>(null);

  useEffect(() => {
    pending.current = null;
    try {
      const mark = window.history.state?.[HISTORY_KEY] as ReturnMark | undefined;
      const age = Date.now() - (mark?.savedAt ?? NaN);
      if (mark?.key === key && typeof mark.href === 'string' &&
          Number.isFinite(mark.y) && mark.y >= 0 && Number.isFinite(mark.top) &&
          age >= 0 && age <= MAX_AGE_MS) {
        pending.current = mark;
      }
    } catch { /* Unavailable history state must not break Search. */ }

    // A reader who starts scrolling while the request is pending has chosen a
    // new position. Do not yank them back when the response finally arrives.
    const cancel = () => {
      if (!pending.current) return;
      pending.current = null;
      // Retire an abandoned landing on this entry, so a later return cannot
      // resurrect the position the reader explicitly declined.
      try {
        if (window.history.state?.[HISTORY_KEY]?.key === key) {
          const state = { ...window.history.state };
          delete state[HISTORY_KEY];
          window.history.replaceState(state, '');
        }
      } catch { /* Navigation remains usable without history writes. */ }
    };
    const onKey = (event: KeyboardEvent) => {
      if (['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' '].includes(event.key)) cancel();
    };
    window.addEventListener('wheel', cancel, { passive: true });
    window.addEventListener('touchstart', cancel, { passive: true });
    window.addEventListener('keydown', onKey);
    return () => {
      pending.current = null;
      window.removeEventListener('wheel', cancel);
      window.removeEventListener('touchstart', cancel);
      window.removeEventListener('keydown', onKey);
    };
  }, [key]);

  useEffect(() => {
    if (!resultsReady || !pending.current) return;
    const frame = requestAnimationFrame(() => {
      const mark = pending.current;
      if (!mark || mark.key !== key || new URL(window.location.href).pathname !== '/search') return;
      // A same-text re-search can reuse this mounted component while replacing
      // the history entry. Its older request must not carry a landing into it.
      const current = window.history.state?.[HISTORY_KEY] as ReturnMark | undefined;
      if (current?.key !== mark.key || current.savedAt !== mark.savedAt || current.href !== mark.href) return;
      const anchor = Array.from(document.querySelectorAll<HTMLAnchorElement>('a[href]'))
        .find(link => link.href === mark.href);
      // Prefer the same result in the same viewport slot if a fresh result
      // above it changed height. If it disappeared, use the prior offset.
      const target = anchor ? window.scrollY + anchor.getBoundingClientRect().top - mark.top : mark.y;
      const maximum = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
      pending.current = null;
      window.scrollTo(0, Math.max(0, Math.min(target, maximum)));
    });
    return () => cancelAnimationFrame(frame);
  }, [key, resultsReady]);

  // After a successful return, scrolling then using browser Forward (or the
  // persistent navigation) must save the NEW place, not replay the old click.
  // Ignore loading/restore clamps. Bound History API writes during long scrolls;
  // scrollend flushes the final offset without waiting for the trailing timer.
  useEffect(() => {
    if (!resultsReady) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const save = () => {
      timer = undefined;
      if (pending.current || new URL(window.location.href).pathname !== '/search') return;
      try {
        const mark = window.history.state?.[HISTORY_KEY] as ReturnMark | undefined;
        if (mark?.key !== key) return;
        const anchor = Array.from(document.querySelectorAll<HTMLAnchorElement>('a[href]'))
          .find(link => link.href === mark.href);
        window.history.replaceState({ ...window.history.state, [HISTORY_KEY]: {
          ...mark, y: window.scrollY, top: anchor?.getBoundingClientRect().top ?? mark.top,
          savedAt: Date.now(),
        } }, '');
      } catch { /* History persistence is best effort. */ }
    };
    const onScroll = () => {
      if (!pending.current && timer === undefined) timer = setTimeout(save, 500);
    };
    const onScrollEnd = () => {
      if (timer === undefined) return;
      clearTimeout(timer);
      save();
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('scrollend', onScrollEnd);
    return () => {
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('scrollend', onScrollEnd);
      if (timer !== undefined) clearTimeout(timer);
    };
  }, [key, resultsReady]);

  return (event: MouseEvent<HTMLElement>) => {
    if (!resultsReady || event.defaultPrevented || event.button !== 0 ||
        event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const anchor = (event.target as Element).closest<HTMLAnchorElement>('a[href]');
    if (!anchor || (anchor.target && anchor.target !== '_self') || anchor.hasAttribute('download')) return;
    const destination = new URL(anchor.href, window.location.href);
    if (destination.origin !== window.location.origin || destination.pathname === '/search') return;
    const mark: ReturnMark = {
      key, href: destination.href, top: anchor.getBoundingClientRect().top,
      y: window.scrollY, savedAt: Date.now(),
    };
    try {
      window.history.replaceState({ ...window.history.state, [HISTORY_KEY]: mark }, '');
    } catch { /* A history quota/security failure must not block the card link. */ }
  };
}
