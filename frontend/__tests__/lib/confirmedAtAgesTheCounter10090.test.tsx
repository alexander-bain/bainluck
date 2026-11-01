/**
 * #10090 decision J = A (Alex: "On decision J: I choose \"A\"") — WEB HALF.
 *
 * The event stream's named heartbeat carries `confirmed_at`: the newest venue
 * input that AGREED with what was published (the server never advances it while
 * a different price is held). The reader's "seconds ago" counts from the later
 * of the adopted price clock and that confirmation, so a steady price the
 * markets keep confirming stays a few seconds old instead of reading as a
 * 25-second delay.
 *
 * Pinned here:
 *   * the heartbeat parse: an old server's `{"t": ...}` is no confirmation;
 *   * the controller reports it and treats it as transport only (no frame, no
 *     delivery change);
 *   * `priceAgeClock`: the max, never a clock for nothing on screen, and an old
 *     server's page is exactly today's;
 *   * an open socket with a confirmed value on screen reads "Connected", not
 *     "Connected · waiting"; every warning still outranks it;
 *   * the tap details' "Latest source update" reads the newer confirmation
 *     (Alex 2026-10-31: one price row) and leave `data-observation-at` (the
 *     A6 recorder's read) on the observation.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import LiveConnectionStatus from "@/components/event/LiveConnectionStatus";
import {
  EMPTY_CONNECTION_TRACKER,
  presentConnectionStatus,
  priceAgeClock,
} from "@/lib/event/liveConnectionStatus";
import {
  createLiveStreamController,
  heartbeatConfirmedAt,
  type StreamHandle,
} from "@/lib/liveStreamController";

/** Fixed anchor — never `Date.now()` (gotcha #44). */
const NOW = Date.UTC(2026, 9, 29, 23, 0, 30);
const OBSERVED = "2026-10-29T23:00:05.000Z"; // 25 s before NOW
const CONFIRMED = "2026-10-29T23:00:28.000Z"; // 2 s before NOW

class FakeSource implements StreamHandle {
  readyState = 1;
  private listeners = new Map<string, ((event: unknown) => void)[]>();
  addEventListener(type: string, listener: (event: unknown) => void) {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
  }
  close() {
    this.readyState = 2;
  }
  emit(type: string, data?: unknown) {
    for (const listener of this.listeners.get(type) ?? []) listener(data === undefined ? {} : { data });
  }
}

describe("#10090 J=A heartbeatConfirmedAt", () => {
  it("reads confirmed_at from the heartbeat body", () => {
    expect(heartbeatConfirmedAt(JSON.stringify({ t: 1, confirmed_at: CONFIRMED }))).toBe(CONFIRMED);
    expect(heartbeatConfirmedAt({ t: 1, confirmed_at: CONFIRMED })).toBe(CONFIRMED);
  });

  it("an old server's heartbeat, a null, junk or an unparseable time is no confirmation", () => {
    expect(heartbeatConfirmedAt(JSON.stringify({ t: 1 }))).toBeNull();
    expect(heartbeatConfirmedAt(JSON.stringify({ t: 1, confirmed_at: null }))).toBeNull();
    expect(heartbeatConfirmedAt(JSON.stringify({ confirmed_at: "not a time" }))).toBeNull();
    expect(heartbeatConfirmedAt(JSON.stringify({ confirmed_at: 1761778828 }))).toBeNull();
    expect(heartbeatConfirmedAt("{not json")).toBeNull();
    expect(heartbeatConfirmedAt(undefined)).toBeNull();
    expect(heartbeatConfirmedAt("null")).toBeNull();
  });
});

describe("#10090 J=A the controller reports confirmed_at as transport only", () => {
  it("a heartbeat with confirmed_at reaches onConfirmedAt and nothing else", () => {
    const source = new FakeSource();
    const frames: unknown[] = [];
    const delivering: boolean[] = [];
    const confirmed: string[] = [];
    const controller = createLiveStreamController({
      open: () => source,
      now: () => 0,
      onFrame: (f) => frames.push(f),
      onDeliveringChange: (d) => delivering.push(d),
      onConfirmedAt: (at) => confirmed.push(at),
    });
    controller.start();
    source.emit("open");
    const deliveringAfterOpen = [...delivering];
    source.emit("heartbeat", JSON.stringify({ t: 1, confirmed_at: CONFIRMED }));
    source.emit("heartbeat", JSON.stringify({ t: 2 }));
    expect(confirmed).toEqual([CONFIRMED]);
    expect(frames).toEqual([]);
    expect(delivering).toEqual(deliveringAfterOpen);
    controller.stop();
  });

  it("a stopped controller reports nothing", () => {
    const source = new FakeSource();
    const confirmed: string[] = [];
    const controller = createLiveStreamController({
      open: () => source,
      now: () => 0,
      onFrame: () => undefined,
      onDeliveringChange: () => undefined,
      onConfirmedAt: (at) => confirmed.push(at),
    });
    controller.start();
    source.emit("open");
    controller.stop();
    source.emit("heartbeat", JSON.stringify({ t: 1, confirmed_at: CONFIRMED }));
    expect(confirmed).toEqual([]);
  });
});

describe("#10090 J=A priceAgeClock", () => {
  it("ages from the later of the adopted clock and the confirmation", () => {
    expect(priceAgeClock(OBSERVED, CONFIRMED)).toBe(CONFIRMED);
  });

  it("an older confirmation leaves the adopted clock", () => {
    expect(priceAgeClock(CONFIRMED, OBSERVED)).toBe(CONFIRMED);
  });

  it("an old server (no confirmation) is exactly today's clock", () => {
    expect(priceAgeClock(OBSERVED, null)).toBe(OBSERVED);
    expect(priceAgeClock(OBSERVED, undefined)).toBe(OBSERVED);
    expect(priceAgeClock(OBSERVED, "garbage")).toBe(OBSERVED);
  });

  it("a confirmation of nothing on screen ages nothing", () => {
    expect(priceAgeClock(null, CONFIRMED)).toBeNull();
    expect(priceAgeClock(undefined, CONFIRMED)).toBeNull();
  });
});

describe("#10090 J=A the open socket's words", () => {
  const input = { status: "open" as const, terminalLabel: null, priceMayBeOld: false, scoreMayBeOld: false };

  it("a confirmed value on an open socket reads Connected, not waiting", () => {
    expect(presentConnectionStatus(EMPTY_CONNECTION_TRACKER, { ...input, priceConfirmed: true }, NOW).label)
      .toBe("Connected");
  });

  it("with no confirmation the words are today's", () => {
    expect(presentConnectionStatus(EMPTY_CONNECTION_TRACKER, input, NOW).label).toBe("Connected · waiting");
    expect(presentConnectionStatus(EMPTY_CONNECTION_TRACKER, { ...input, priceConfirmed: false }, NOW).label)
      .toBe("Connected · waiting");
  });

  it("only the open socket changes: quiet, retrying and the warnings are untouched", () => {
    const t = EMPTY_CONNECTION_TRACKER;
    expect(presentConnectionStatus(t, { ...input, status: "quiet", priceConfirmed: true }, NOW).label)
      .toBe("Connected · checking");
    expect(presentConnectionStatus(t, { ...input, status: "retrying", priceConfirmed: true }, NOW).label)
      .toBe("Updates interrupted · reconnecting");
    expect(presentConnectionStatus(t, { ...input, priceMayBeOld: true, priceConfirmed: true }, NOW).label)
      .toBe("Price may be old");
    expect(presentConnectionStatus(t, { ...input, terminalLabel: "Finished", priceConfirmed: true }, NOW).label)
      .toBe("Finished");
  });
});

describe("#10090 J=A the tap details", () => {
  const presentation = { label: "Connected", tone: "live" as const, breathes: true, announcement: "" };
  const base = {
    presentation,
    priceObservedAt: OBSERVED,
    scoreShown: false,
    scoreConfirmedAt: null,
    oldestFact: null,
    now: NOW,
  };

  it("a newer confirmation is the latest source update, a few seconds old; the observation is untouched", () => {
    const html = renderToStaticMarkup(<LiveConnectionStatus {...base} priceConfirmedAt={CONFIRMED} />);
    const latest = html.match(/Latest source update<\/dt><dd>(.*?)<\/dd>/)![1];
    expect(latest).toContain(`dateTime="${CONFIRMED}"`);
    expect(latest).toContain("2s ago");
    expect(html).toContain(`data-observation-at="${OBSERVED}"`);
    expect(html).not.toContain(`dateTime="${OBSERVED}"`);
    expect(html).not.toContain("Probability confirmed");
  });

  it("no confirmation, or an older one, is today's markup", () => {
    const today = renderToStaticMarkup(<LiveConnectionStatus {...base} />);
    expect(today).toContain(`Latest source update</dt><dd><span><time dateTime="${OBSERVED}"`);
    expect(today).toContain("25s ago");
    expect(renderToStaticMarkup(<LiveConnectionStatus {...base} priceConfirmedAt={null} />)).toBe(today);
    expect(
      renderToStaticMarkup(<LiveConnectionStatus {...base} priceConfirmedAt="2026-10-29T23:00:01.000Z" />),
    ).toBe(today);
  });
});

describe('#10090 heartbeat activity_at (the EKG pulse)', () => {
  test('reads a parseable activity_at and nothing else', () => {
    const { heartbeatActivityAt } = jest.requireActual('@/lib/liveStreamController');
    const iso = '2026-11-01T21:20:00.123+00:00';
    expect(heartbeatActivityAt(JSON.stringify({ t: iso, confirmed_at: null, activity_at: iso }))).toBe(iso);
    expect(heartbeatActivityAt(JSON.stringify({ t: iso, confirmed_at: iso }))).toBeNull();
    expect(heartbeatActivityAt(JSON.stringify({ activity_at: 'soon' }))).toBeNull();
    expect(heartbeatActivityAt('not json')).toBeNull();
  });
});

describe("#10090 the controller reports activity_at as transport only", () => {
  it("a heartbeat with activity_at reaches onActivityAt, never onConfirmedAt", () => {
    const source = new FakeSource();
    const frames: unknown[] = [];
    const confirmed: string[] = [];
    const activity: string[] = [];
    const controller = createLiveStreamController({
      open: () => source,
      now: () => 0,
      onFrame: (f) => frames.push(f),
      onDeliveringChange: () => undefined,
      onConfirmedAt: (at) => confirmed.push(at),
      onActivityAt: (at) => activity.push(at),
    });
    controller.start();
    source.emit("open");
    source.emit("heartbeat", JSON.stringify({ t: 1, confirmed_at: null, activity_at: CONFIRMED }));
    expect(activity).toEqual([CONFIRMED]);
    expect(confirmed).toEqual([]);
    expect(frames).toEqual([]);
    controller.stop();
  });
});
