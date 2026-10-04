/**
 * #10200 (child of #9655) — the chart status button and its tap details.
 *
 * MOUNTED on `helpers/minimalDom` (no jsdom in this repo). That DOM does not
 * dispatch events, so the test drives the real component the two ways a
 * browser would reach it: React's own props on the rendered button (a native
 * `<button>` is what turns Enter and Space into that same click), and the
 * document listeners the component registers for Escape and an outside tap,
 * captured and called. Static markup covers the closed state and the copy.
 */

import '../helpers/minimalDom';
import React, { act } from 'react';
import { readFileSync } from 'fs';
import { join } from 'path';
import { renderToStaticMarkup } from 'react-dom/server';
import { createRoot, type Root } from 'react-dom/client';

import LiveConnectionStatus from '@/components/event/LiveConnectionStatus';
import type { ConnectionPresentation } from '@/lib/event/liveConnectionStatus';

const NOW = Date.UTC(2026, 9, 2, 20, 0, 0);
const PRICE_AT = new Date(NOW - 8_000).toISOString();
const SCORE_AT = new Date(NOW - 7 * 60_000).toISOString();

const CONNECTED: ConnectionPresentation = {
  label: 'Connected · waiting',
  tone: 'live',
  breathes: true,
  announcement: '',
};

type Props = React.ComponentProps<typeof LiveConnectionStatus>;

function props(over: Partial<Props> = {}): Props {
  return {
    presentation: CONNECTED,
    priceObservedAt: PRICE_AT,
    scoreShown: true,
    scoreConfirmedAt: SCORE_AT,
    oldestFact: 'score',
    now: NOW,
    ...over,
  };
}

// ── a tiny walker over the minimal DOM ─────────────────────────────────────
type N = { tagName?: string; childNodes: N[]; textContent: string; [k: string]: unknown };
function find(node: N, pred: (n: N) => boolean): N | null {
  if (pred(node)) return node;
  for (const c of node.childNodes ?? []) {
    const hit = find(c, pred);
    if (hit) return hit;
  }
  return null;
}
const reactProps = (node: N) =>
  node[Object.keys(node).find((k) => k.startsWith('__reactProps'))!] as Record<string, (...a: unknown[]) => void>;

// ── document listeners, captured so Escape and an outside tap can be sent ───
const listeners = new Map<string, Set<(e: unknown) => void>>();
const doc = document as unknown as Record<string, unknown>;
doc.addEventListener = (type: string, fn: (e: unknown) => void) => {
  if (!listeners.has(type)) listeners.set(type, new Set());
  listeners.get(type)!.add(fn);
};
doc.removeEventListener = (type: string, fn: (e: unknown) => void) => {
  listeners.get(type)?.delete(fn);
};
const send = (type: string, e: unknown) => {
  for (const fn of [...(listeners.get(type) ?? [])]) fn(e);
};

function mount(p: Props) {
  const host = (document as unknown as { createElement: (t: string) => N }).createElement('div');
  (document as unknown as { body: { appendChild: (n: N) => void } }).body.appendChild(host);
  const root: Root = createRoot(host as unknown as Element);
  act(() => root.render(<LiveConnectionStatus {...p} />));
  const wrapper = find(host, (n) => n['data-testid'] === 'live-connection-status')!;
  const button = find(host, (n) => n.tagName === 'BUTTON')!;
  const details = () => find(host, (n) => n.tagName === 'DIV' && typeof n.id === 'string' && n.id === button['aria-controls'])!;
  // The minimal DOM has no focus or containment; give the two nodes the
  // component touches the browser's behaviour for them.
  let focused = false;
  button.focus = () => { focused = true; };
  wrapper.contains = (t: unknown) => find(wrapper, (n) => n === t) !== null;
  return {
    host, wrapper, button, details, root,
    focused: () => focused,
    click: () => act(() => reactProps(button).onClick({})),
    unmount: () => act(() => root.unmount()),
  };
}

describe('#10200 the status button', () => {
  it('closed: a semantic label, aria-expanded false, controlling hidden details', () => {
    const html = renderToStaticMarkup(<LiveConnectionStatus {...props()} />);
    expect(html).toContain('<span class="min-w-0 leading-4">Connected · waiting</span>');
    expect(html).toMatch(/aria-expanded="false" aria-controls="([^"]+)"/);
    const id = html.match(/aria-controls="([^"]+)"/)![1];
    // A plain substring: the id is React's `useId` value, so no pattern is needed.
    expect(html).toContain(`<div id="${id}" hidden=""`);
    // The label is a state, never a seconds counter.
    const visible = html.match(/min-w-0 leading-4">([^<]+)</)![1];
    expect(visible).not.toMatch(/\d+s\b|ago/);
  });

  it('a tap opens the exact facts; a second tap closes them', () => {
    const m = mount(props());
    try {
      expect(m.button['aria-expanded']).toBe('false');
      // The minimal DOM records attributes as fields: `hidden=""` while closed,
      // removed once open.
      expect(m.details().hidden).toBe('');
      m.click();
      expect(m.button['aria-expanded']).toBe('true');
      expect(m.details().hidden).toBeUndefined();
      const text = m.details().textContent;
      expect(text).toContain('Probability observed');
      expect(text).toContain('Oct 2, 7:59:52 PM UTC · 8s ago');
      expect(text).toContain('Score confirmed');
      expect(text).toContain('Oct 2, 7:53:00 PM UTC · 7m ago');
      expect(text).toContain('Oldest on screenThe score');
      m.click();
      expect(m.button['aria-expanded']).toBe('false');
    } finally {
      m.unmount();
    }
  });

  it('Escape closes and returns focus to the button', () => {
    const m = mount(props());
    try {
      m.click();
      act(() => send('keydown', { key: 'Enter' }));
      expect(m.button['aria-expanded']).toBe('true');
      act(() => send('keydown', { key: 'Escape' }));
      expect(m.button['aria-expanded']).toBe('false');
      expect(m.focused()).toBe(true);
    } finally {
      m.unmount();
    }
  });

  it('a tap outside closes; a tap inside the details does not', () => {
    const m = mount(props());
    try {
      m.click();
      act(() => send('pointerdown', { target: m.details() }));
      expect(m.button['aria-expanded']).toBe('true');
      act(() => send('pointerdown', { target: { nodeType: 1, childNodes: [] } }));
      expect(m.button['aria-expanded']).toBe('false');
    } finally {
      m.unmount();
    }
  });

  it('listens to the document only while open — a closed status costs nothing', () => {
    const m = mount(props());
    try {
      expect(listeners.get('keydown')?.size ?? 0).toBe(0);
      m.click();
      expect(listeners.get('keydown')?.size).toBe(1);
      expect(listeners.get('pointerdown')?.size).toBe(1);
      m.click();
      expect(listeners.get('keydown')?.size).toBe(0);
    } finally {
      m.unmount();
    }
  });
});

describe('#10200 the tap facts', () => {
  it('absent or unreadable clocks say "Time unavailable", never a guess', () => {
    const html = renderToStaticMarkup(
      <LiveConnectionStatus {...props({ priceObservedAt: null, scoreConfirmedAt: 'garbage' })} />,
    );
    expect(html.split('Time unavailable').length - 1).toBe(2);
  });

  it('a page with no score on screen gives only the probability clock', () => {
    const html = renderToStaticMarkup(
      <LiveConnectionStatus {...props({ scoreShown: false, oldestFact: 'price' })} />,
    );
    expect(html).toContain('Probability observed');
    expect(html).not.toContain('Score confirmed');
    expect(html).not.toContain('Oldest on screen');
  });

  it('the clock carries its machine-readable instant', () => {
    const html = renderToStaticMarkup(<LiveConnectionStatus {...props()} />);
    expect(html).toContain(`<time dateTime="${PRICE_AT}">`);
  });
});

describe('#10200 motion, colour and announcements', () => {
  it('a healthy connection breathes only where motion is allowed; Reduce Motion gets a still dot', () => {
    const html = renderToStaticMarkup(<LiveConnectionStatus {...props()} />);
    expect(html).toContain('motion-safe:animate-pulse');
    // A bare `animate-pulse` would ignore prefers-reduced-motion.
    expect(html).not.toMatch(/[" ]animate-pulse/);
  });

  it('nothing but a healthy connection moves', () => {
    for (const presentation of [
      { label: 'Price may be old', tone: 'neutral', breathes: false, announcement: '' },
      { label: 'Updates interrupted · reconnecting', tone: 'attention', breathes: false, announcement: 'Updates interrupted · reconnecting' },
      { label: 'Finished', tone: 'neutral', breathes: false, announcement: 'Finished' },
    ] as ConnectionPresentation[]) {
      expect(renderToStaticMarkup(<LiveConnectionStatus {...props({ presentation })} />)).not.toContain('animate-');
    }
  });

  it('colour is supplementary to the words, and comes from design tokens', () => {
    // Executable source only: the comments cite issues as `#8336`, which is not a colour.
    const src = readFileSync(join(process.cwd(), 'components/event/LiveConnectionStatus.tsx'), 'utf8')
      .replace(/\/\*[\s\S]*?\*\//g, ' ')
      .replace(/(^|\s)\/\/.*$/gm, '$1');
    expect(src).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
    expect(src).not.toMatch(/\bdark:/);
    const attention = renderToStaticMarkup(
      <LiveConnectionStatus
        {...props({ presentation: { label: 'Updates interrupted · reconnecting', tone: 'attention', breathes: false, announcement: 'x' } })}
      />,
    );
    expect(attention).toContain('bg-accent-warning');
    expect(attention).toContain('Updates interrupted · reconnecting');
  });

  it('announces politely, and only from the copy that is asked to', () => {
    const p = { label: 'Updates resumed', tone: 'steady', breathes: false, announcement: 'Updates resumed' } as ConnectionPresentation;
    expect(renderToStaticMarkup(<LiveConnectionStatus {...props({ presentation: p })} />)).toContain(
      '<span class="sr-only" role="status" aria-live="polite">Updates resumed</span>',
    );
    expect(renderToStaticMarkup(<LiveConnectionStatus {...props({ presentation: p, announces: false })} />)).not.toContain(
      'aria-live',
    );
  });

  it('a quiet receipt is not announced', () => {
    const p = { label: 'Updated', tone: 'steady', breathes: false, announcement: '' } as ConnectionPresentation;
    expect(renderToStaticMarkup(<LiveConnectionStatus {...props({ presentation: p })} />)).toContain(
      'aria-live="polite"></span>',
    );
  });
});

describe('#9655 the whole state is readable at 390px', () => {
  const RETRYING: ConnectionPresentation = {
    label: 'Updates interrupted · reconnecting',
    tone: 'attention',
    breathes: false,
    announcement: 'Updates interrupted · reconnecting',
  };
  // Every class on the path from the button down to the words: anything here
  // that forbids a line break or clips the overflow puts "reconn…" back.
  const CLIPS = /\b(truncate|whitespace-nowrap|text-ellipsis|text-clip|overflow-hidden|overflow-x-hidden|line-clamp-\d+)\b/;

  it('the retrying label is printed whole, with nothing on its path that clips or forbids a wrap', () => {
    const html = renderToStaticMarkup(<LiveConnectionStatus {...props({ presentation: RETRYING })} />);
    const button = html.match(/<button[^>]*class="([^"]+)"[^>]*>([\s\S]*?)<\/button>/)!;
    expect(button[1]).not.toMatch(CLIPS);
    const words = button[2].match(/<span class="([^"]*)">(Updates interrupted · reconnecting)<\/span>/);
    expect(words).not.toBeNull();
    expect(words![1]).not.toMatch(CLIPS);
    // Whole words: no utility that breaks inside "reconnecting".
    expect(words![1]).not.toMatch(/\bbreak-(all|words)\b/);
    expect(html.match(/<div[^>]*data-testid="live-connection-status"[^>]*class="([^"]+)"|<div[^>]*class="([^"]+)"[^>]*data-testid="live-connection-status"/)!.slice(1).join(' ')).not.toMatch(CLIPS);
  });

  it('a wrapped label keeps its dot on the first line and the dot never shrinks away', () => {
    const html = renderToStaticMarkup(<LiveConnectionStatus {...props({ presentation: RETRYING })} />);
    const dot = html.match(/<span aria-hidden="true" class="([^"]+)"><\/span>/)![1];
    expect(dot).toContain('shrink-0');
    expect(dot).toContain('bg-accent-warning');
    // 8px dot centred on the first 16px line, not on the middle of two lines.
    expect(dot).toContain('mt-1');
    expect(html).toMatch(/<button[^>]*class="[^"]*\bitems-start\b/);
    expect(html).toContain('<span class="min-w-0 leading-4">Updates interrupted · reconnecting</span>');
  });

  it('wrapping changes nothing a screen reader or a tap reaches', () => {
    const html = renderToStaticMarkup(<LiveConnectionStatus {...props({ presentation: RETRYING })} />);
    expect(html).toContain('<span class="sr-only">, show update times</span>');
    expect(html).toContain('<span class="sr-only" role="status" aria-live="polite">Updates interrupted · reconnecting</span>');
    expect(html).toMatch(/<button type="button" aria-expanded="false" aria-controls="[^"]+"/);
  });
});
