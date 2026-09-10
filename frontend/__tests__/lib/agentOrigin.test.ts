/**
 * #1916 / notice 39 rung 3 — our own agents stop counting as an audience.
 *
 * WHAT THIS GUARDS, AND WHY IT IS SHAPED THIS WAY.
 *
 * The ship has two halves that must agree and are written in two languages: a
 * TypeScript predicate (`isAgentOriginValue`) used by the consent gate, and an
 * inline JS string (`speedInsightsAgentDropSnippet`) that runs during HTML
 * parse, before hydration, to register a Speed Insights `beforeSend`. Two
 * copies of one definition is exactly the drift this file exists to prevent, so
 * the central test EXECUTES the snippet in a `vm` sandbox and asserts it agrees
 * with the predicate value-for-value. A source scan would only prove the two
 * strings look alike.
 *
 * The suite is `testEnvironment: 'node'` with no jsdom, which is why the
 * sandbox supplies its own `document`/`window` rather than rendering anything.
 *
 * 🔴 THE EMPTY VALUE IS THE CASE THAT ALREADY BIT US, so it is asserted rather
 * than assumed. Rung 1 shipped a carrier that put `x-bainluck-origin:` on the
 * wire with no value: the backend's `if not raw` read it as a PERSON, the call
 * voted exactly as before, and nothing errored — the author believed it was
 * tagged. An empty `bl_agent` must therefore mean "a person" here too, matching
 * `routes/events.py:_request_is_automation` exactly, and any future carrier is
 * asserting a NON-EMPTY value, never merely a present one.
 */

import vm from 'vm';
import fs from 'fs';
import path from 'path';

import {
  AGENT_COOKIE,
  AGENT_ORIGIN_USER,
  isAgentOriginValue,
  readAgentCookie,
  isAgentClient,
  subscribeAgentOrigin,
  speedInsightsAgentDropSnippet,
} from '@/lib/analytics/agentOrigin';

const FRONTEND = path.join(__dirname, '..', '..');
const LAYOUT = path.join(FRONTEND, 'app', 'layout.tsx');
const GATE = path.join(FRONTEND, 'components', 'Analytics', 'TelemetryGate.tsx');

function read(file: string): string {
  if (!fs.existsSync(file)) {
    throw new Error(
      `agentOrigin: ${file} does not exist. This guard reads call sites by ` +
        `path; a move renames the claim and must be made deliberately.`,
    );
  }
  return fs.readFileSync(file, 'utf8');
}

/** Same conservative strip the D30 guard uses: an absence check must not be
 *  satisfiable by prose, and a presence check must not be broken by it. */
function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/^\s*\/\/.*$/gm, '');
}

interface SnippetRun {
  /** Everything pushed onto the Speed Insights pre-load queue. */
  queue: unknown[][];
  /** The `beforeSend` callbacks the snippet registered, if any. */
  registered: Array<(e: unknown) => unknown>;
  sandbox: Record<string, any>;
}

/**
 * Run the inline snippet against a given `document.cookie`, in a sandbox that
 * mimics a browser only as far as the snippet can observe.
 *
 * `preexistingSi` models the case where something else already installed the
 * queue stub — the package's own `initQueue` does exactly this — because a
 * snippet that clobbered it would silently discard whatever was queued first.
 */
function runSnippet(cookie: string, preexistingSi?: (...a: unknown[]) => void): SnippetRun {
  const registered: Array<(e: unknown) => unknown> = [];
  const sandbox: Record<string, any> = {
    document: { cookie },
  };
  sandbox.window = sandbox;
  if (preexistingSi) sandbox.si = preexistingSi;

  vm.createContext(sandbox);
  vm.runInContext(speedInsightsAgentDropSnippet(), sandbox);

  const queue: unknown[][] = (sandbox.siq as unknown[][]) || [];
  for (const entry of queue) {
    if (entry[0] === 'beforeSend' && typeof entry[1] === 'function') {
      registered.push(entry[1] as (e: unknown) => unknown);
    }
  }
  return { queue, registered, sandbox };
}

/**
 * The shared table. Every case is a real shape the cookie can take, and the
 * expectation is the BACKEND's answer for the same string — that parity is the
 * property under test, not this file's opinion.
 */
const CASES: Array<{ value: string; agent: boolean; why: string }> = [
  { value: 'look.sh', agent: true, why: 'the default every shot carries' },
  { value: 'latency', agent: true, why: 'a named lane' },
  { value: 'bus-hourly', agent: true, why: 'a named mission' },
  { value: AGENT_ORIGIN_USER, agent: false, why: 'the deliberate escape hatch' },
  { value: 'USER', agent: false, why: 'the escape hatch is case-insensitive' },
  { value: '  user  ', agent: false, why: 'the escape hatch survives padding' },
  { value: '', agent: false, why: 'THE EMPTY VALUE IS A PERSON — the rung-1 bug' },
  { value: '   ', agent: true, why: 'whitespace is a value, and it is not "user"' },
];

describe('the agent predicate mirrors the backend, including the empty case', () => {
  it.each(CASES)('$value -> agent=$agent ($why)', ({ value, agent }) => {
    expect(isAgentOriginValue(value)).toBe(agent);
  });

  it('treats a missing cookie as a person, never as an agent', () => {
    expect(isAgentOriginValue(null)).toBe(false);
    expect(isAgentOriginValue(undefined)).toBe(false);
  });

  it('fails toward MEASURING when there is no document at all', () => {
    // Server render. A predicate that guessed "agent" here would delete every
    // real visitor from the numbers, which is the unrecoverable direction:
    // over-suppression leaves nothing behind to notice, under-suppression
    // leaves a row we can see and count.
    expect(typeof document).toBe('undefined');
    expect(isAgentClient()).toBe(false);
  });
});

describe('the cookie parse reads a cookie, not a substring', () => {
  it('finds the value among siblings', () => {
    expect(readAgentCookie(`a=1; ${AGENT_COOKIE}=latency; z=9`)).toBe('latency');
  });

  it('does NOT answer for a cookie whose name merely ends in ours', () => {
    // `not_bl_agent=lane` contains `bl_agent=lane`. A substring match would
    // report an agent for a visitor carrying an unrelated cookie, and silently
    // drop that visitor from every rail.
    expect(readAgentCookie('not_bl_agent=lane')).toBeNull();
    expect(isAgentOriginValue(readAgentCookie('not_bl_agent=lane'))).toBe(false);
  });

  it('decodes a percent-escaped value and survives a malformed one', () => {
    expect(readAgentCookie(`${AGENT_COOKIE}=look%2Esh`)).toBe('look.sh');
    // A lone `%` is not a valid escape; the parse must not throw inside a
    // telemetry path, and the raw value is still judged by the predicate.
    expect(readAgentCookie(`${AGENT_COOKIE}=100%`)).toBe('100%');
  });

  it('returns null for an empty or absent cookie string', () => {
    expect(readAgentCookie('')).toBeNull();
    expect(readAgentCookie(null)).toBeNull();
    expect(readAgentCookie('other=1')).toBeNull();
  });
});

describe('the inline snippet agrees with the predicate, value for value', () => {
  it.each(CASES)(
    'cookie=$value registers a drop iff the predicate says agent ($agent)',
    ({ value, agent }) => {
      const { registered } = runSnippet(`${AGENT_COOKIE}=${encodeURIComponent(value)}`);
      expect(registered.length > 0).toBe(agent);
      expect(registered.length > 0).toBe(isAgentOriginValue(value));
    },
  );

  it('registers nothing when the cookie is absent — a visitor is untouched', () => {
    const { queue, sandbox } = runSnippet('a=1; b=2');
    expect(queue).toHaveLength(0);
    // Pass-through means genuinely nothing installed, not an installed no-op:
    // a stub left behind would swallow the package's own later registration.
    expect(sandbox.si).toBeUndefined();
  });

  it('the registered callback CANCELS the beacon', () => {
    const { registered } = runSnippet(`${AGENT_COOKIE}=look.sh`);
    expect(registered).toHaveLength(1);
    // The package cancels on null/undefined/false and sends on anything else,
    // so "returns falsy" is too weak a claim to assert — null is the contract.
    expect(registered[0]({ type: 'vital', url: 'https://bainluck.com/' })).toBeNull();
  });

  it('queues in the shape the real script drains', () => {
    // `initQueue` pushes a real ARRAY of the arguments. The loaded script reads
    // `siq[i][0]`/`[1]`; pushing a bare `arguments` object here would look fine
    // in this test and is a different type on the wire, so assert the type.
    const { queue } = runSnippet(`${AGENT_COOKIE}=look.sh`);
    expect(queue).toHaveLength(1);
    expect(Array.isArray(queue[0])).toBe(true);
    expect(queue[0][0]).toBe('beforeSend');
    expect(typeof queue[0][1]).toBe('function');
  });

  it('does not clobber a queue stub that is already installed', () => {
    // The package's `initQueue` bails when `window.si` exists, so whoever gets
    // there first owns the stub. If that is not us we must USE it, or the
    // registration lands somewhere the real script never drains.
    const seen: unknown[][] = [];
    const existing = (...args: unknown[]) => { seen.push(args); };
    const { sandbox } = runSnippet(`${AGENT_COOKIE}=look.sh`, existing);

    expect(sandbox.si).toBe(existing);
    expect(seen).toHaveLength(1);
    expect(seen[0][0]).toBe('beforeSend');
  });

  it('never throws, whatever the cookie header looks like', () => {
    for (const cookie of ['', ';;;', '=', `${AGENT_COOKIE}`, `${AGENT_COOKIE}=`, '%%%']) {
      expect(() => runSnippet(cookie)).not.toThrow();
    }
  });
});

describe('the drop is wired where it can actually win the race', () => {
  it('runs BEFORE the Speed Insights mount in the root layout', () => {
    const code = stripComments(read(LAYOUT));

    const snippetAt = code.indexOf('speedInsightsAgentDropSnippet()');
    const mountAt = code.indexOf('<SpeedInsights');
    if (snippetAt === -1 || mountAt === -1) {
      throw new Error(
        'agentOrigin: the layout no longer contains both the snippet call and ' +
          'the <SpeedInsights mount. This guard raises rather than going green ' +
          'on a file it did not understand.',
      );
    }
    // Ordering is the entire argument for an inline script over a useEffect:
    // registered after the beacon, the callback is decoration.
    expect(snippetAt).toBeLessThan(mountAt);
  });

  it('is unconditional — a cookie-less visitor must still parse it', () => {
    const code = stripComments(read(LAYOUT));
    const at = code.indexOf('speedInsightsAgentDropSnippet()');
    const lineStart = code.lastIndexOf('\n', at) + 1;
    const lineEnd = code.indexOf('\n', at);
    const line = code.slice(lineStart, lineEnd === -1 ? undefined : lineEnd);

    // The decision belongs to the snippet, which reads the cookie at runtime.
    // A React-level condition here could only read it by making the root layout
    // dynamic — paying for this filter with every real visitor's TTFB.
    expect(line).not.toContain('&&');
    expect(line).not.toContain('?');
    expect(line).toContain('speedInsightsAgentDropSnippet()');
  });

  it('the consent gate refuses agents, and the check is CODE not prose', () => {
    const code = stripComments(read(GATE));

    // Presence controls first: if the gate no longer mounts what it gates, the
    // assertion below would be guarding an empty component.
    expect(code).toContain('<Analytics');
    expect(code).toContain('decision.googleAnalytics');

    expect(code).toContain('isAgentClient');
    expect(code).toContain('if (isAgent) return null;');
  });

  it('the agent store subscribe is inert and unsubscribes cleanly', () => {
    // It exists only to satisfy `useSyncExternalStore`; the cookie cannot change
    // during the document's life. The contract that matters is that it hands
    // back a callable teardown, or React throws on unmount.
    const unsubscribe = subscribeAgentOrigin();
    expect(typeof unsubscribe).toBe('function');
    expect(() => unsubscribe()).not.toThrow();
  });
});
