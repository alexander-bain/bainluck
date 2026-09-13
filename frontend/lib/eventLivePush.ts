/**
 * What an OPEN event page still refetches while the push stream is healthy, and
 * what a pushed frame is allowed to overwrite when it lands.
 *
 * Both were inline in `app/events/[id]/page.tsx`. They are here because they are
 * the two halves of one question — *does a value that is not in the frame ever
 * reach a page somebody left open?* — and because that question is answerable
 * without a DOM, which is the only way it gets a test in this repo (no jsdom, no
 * React Testing Library).
 *
 * ═══ THE BUG THAT MOVED THEM (CERT-1994) ═══
 *
 * live/034 S2 shipped SSE push for live events: while the stream delivers,
 * `refreshInterval` is **0** and polling stops entirely. That is right for the
 * probability, which the frame carries.
 *
 * It is wrong for everything the frame does NOT carry. The frame holds one
 * probability, one source and one stamp; the cache update spreads `...prev` for
 * the rest. So on a page left open, every other field is frozen at the moment it
 * was first fetched: the score, the status — and the tennis games line and its
 * `observed_at`, which is what made this visible.
 *
 * The freshness chip (#3242) turned that freeze into a false statement. The
 * server re-confirms the games line against ESPN every ~10 minutes; the page
 * never heard, so the chip counted up from a stamp nobody had refreshed and said
 * `Stale · 40m ago` about a number the server had re-confirmed a minute earlier.
 * A worse failure than the one the chip exists to prevent, because it is the
 * honesty mechanism itself lying.
 */

/**
 * How often an open event page revalidates, given what the stream is doing.
 *
 * `connected` no longer means "never" — it means SLOWLY. The push ship stands:
 * the probability still arrives in ~2s instead of waiting up to 32s, and that
 * was always the point. What changes is that the rest of the payload is
 * reconciled on a bounded background poll instead of never.
 *
 * ═══ WHY 120s AND NOT A TASTE ═══
 *
 * It is derived from the chip it has to keep honest, not chosen. `FreshnessChip`
 * calls a stamp stale past `STALE_MS` (5 min). If the page can go longer than
 * that without refetching, then a page-induced staleness is indistinguishable on
 * screen from a real one, and the chip stops meaning "the data is old" and starts
 * meaning "one of two different things is old". So the interval must sit
 * comfortably under the stale threshold; `SCHEDULED_REFRESH_INTERVAL` (120s)
 * already does, at 2.5x headroom, and reusing it beats inventing a fourth
 * cadence constant. `pushedRefreshIntervalIsHonest` pins that relationship so it
 * cannot be broken by editing either number alone.
 */
export function eventRefreshInterval(
  status: string | null | undefined,
  streamConnected: boolean,
  intervals: { live: number; scheduled: number },
): number {
  if (streamConnected) return intervals.scheduled;
  return status === "live" ? intervals.live : intervals.scheduled;
}

/** True while the pushed-page poll cannot itself cause a false `Stale`. */
export function pushedRefreshIntervalIsHonest(
  pushedInterval: number,
  staleMs: number,
): boolean {
  return pushedInterval > 0 && pushedInterval < staleMs;
}

/**
 * How many of the page's own poll intervals may pass with nothing landing
 * before the header stops promising an update.
 *
 * Two, and it is derived rather than chosen: one missed interval is the
 * ordinary shape of a slow response or a single dropped request, and calling
 * that "stalled" would flicker the header on a healthy page. Two consecutive
 * intervals cannot happen while the poll is working.
 */
export const STALLED_POLL_INTERVALS = 2;

/**
 * Is the open page still being fed the payload it is claiming to show live?
 *
 * ═══ THE BUG (#4861) ═══
 *
 * #5016 established that a failed refresh must not take the page away — SWR
 * keeps `data` when a revalidation fails, and the reader should keep the last
 * good page. This is the other half of that sentence: a page we keep must stop
 * SAYING it is live.
 *
 * Measured on the SF@LAR opener, 2026-09-10, on a tab opened at 6:36pm PT and
 * never touched. From halftime onward the event payload stopped landing, and
 * eleven minutes AFTER the final whistle the header still read
 * `LIVE · Next update: 11` over `48% – 52%`, on a game that had ended 7–27.
 * The server was not at fault: it served `status: completed` and a settled hero
 * throughout, and a fresh load of the same url in the same minute rendered
 * Final correctly.
 *
 * What made it look alive is that the page's OTHER fetches were still landing.
 * The hero's score comes from `historyData` (`lastChartPoint`), not from the
 * event, so the score advanced 7–10 → 7–27 beside a probability frozen at the
 * halftime value. A reader has no way to tell those two apart, and the header
 * actively told them the opposite: a countdown ring driven by a `setInterval`
 * that ticks whether or not anything arrives.
 *
 * ═══ WHY THE ERROR ALONE IS NOT ENOUGH ═══
 *
 * `hasError` catches the loud case (a 429, a refused fetch) the moment it
 * happens. It does not catch the quiet one — a poll whose timer a mobile
 * browser suspended when the tab stopped being frontmost, which is what an iPad
 * left on a page through the end of a game is, and which produces no error at
 * all because no request was ever made. Only the silence itself sees that, so
 * both are asked and either is enough.
 *
 * The caller keeps polling either way. This decides what the header may
 * PROMISE, never whether to try again — and it clears itself the moment
 * anything lands, because `msSinceLastLanding` resets on success.
 */
export function eventFeedIsStalled(args: {
  hasError: boolean;
  msSinceLastLanding: number;
  refreshInterval: number;
}): boolean {
  const { hasError, msSinceLastLanding, refreshInterval } = args;
  if (hasError) return true;
  // A non-positive interval means the caller is not polling on a clock at all,
  // so silence proves nothing about it and this must not invent a verdict.
  if (!(refreshInterval > 0)) return false;
  return msSinceLastLanding > STALLED_POLL_INTERVALS * refreshInterval;
}

/**
 * How old the blend may be before the page stops calling itself live (#5459).
 *
 * NOT a new number. It is the server's own floor in
 * `_pinned_live_probability` — a pinned verdict needs the probability to have
 * held across ≥5 observations spanning **≥60 minutes** measured from kickoff —
 * reused rather than re-chosen, so the two halves of this pair cannot drift into
 * disagreeing about how long is too long. That is the argument
 * `STALE_AFTER_S_BY_FACT` makes inside `LiveAgeStamp`, one module outward.
 *
 * It is deliberately an order of magnitude past the badge's own stale boundary
 * (120s for a price). The badge greying at two minutes is a whisper on a healthy
 * page mid-poll; withdrawing the LIVE pill there would flicker it off and on
 * every poll cycle on every healthy game in the app. Removing a word needs a
 * bound nothing ordinary can reach, and an NFL game on a two-minute beat never
 * comes within thirty times of this one.
 */
export const LIVE_CLAIM_MAX_BLEND_AGE_MS = 60 * 60 * 1000;

/**
 * Is this page's LIVE claim backed by anything? (#5459, consumer half of #5077)
 *
 * ═══ WHAT THE READER SAW ═══
 *
 * Jeanjean v Liu, production, 2026-09-12 03:26Z
 * (`artifacts/ux-1204/BEFORE-15310172-390-top.png`). A **LIVE** chip, a **20s**
 * refresh ticker beside it, a second **20s** beside "Win Probability" — and two
 * centimetres above all three, the page's own age badge reading a grey
 * `146m ago`. Hero 1% – 99%, no score anywhere, chart dead flat at 1% for three
 * hours. The match was long over and Liu had won; 1%/99% is the settled-market
 * signature (bid 0.00 / ask 1.00 on every rung), not a forecast.
 *
 * The page already contained its own refutation. `LiveAgeStamp` had computed
 * that the number was two and a half hours old and had greyed itself and dropped
 * the word "live" accordingly, while the element beside it promised a fresh one
 * in twenty seconds. That is the #4469/#5069 lesson — *a second copy of the
 * comparison is how a dot and its caption come to disagree* — reaching one more
 * element outward, and it is why this is one predicate and not three JSX
 * conditions.
 *
 * ═══ TWO DISQUALIFIERS, BECAUSE THEY SEE DIFFERENT ROWS ═══
 *
 * `pinned` is the server's verdict and is the authoritative one: it is the only
 * thing that can see a value the polls keep rewriting UNCHANGED, where the stamp
 * is genuinely fresh and no age rule could ever fire. It is also rare — live/162
 * measured the shipped rule firing on **2–3 of the 39** rows in #5077's target
 * shape, because 28 of them have no probability series in the window at all.
 *
 * `blendAgeMs` is this page's own reading and covers most of the rest: a blend
 * an hour old cannot back a twenty-second promise, whatever the server managed
 * to work out. Alex's MiLB specimen (15310413, `234m ago` under a 20s ticker) is
 * one of the 24 rows #5469 says the backend rule currently cannot reach, and is
 * the argument these are complementary rather than redundant.
 *
 * Neither is a claim about the MATCH — we are not asserting it ended. It is a
 * claim about our own number, which is the only thing we are entitled to speak
 * about. Under standing notice 34 the remedy is to stop making the claim, not to
 * explain on the page why it was withdrawn.
 *
 * An absent or unparseable stamp is NOT unbacked. "We cannot say how old this
 * is" and "this is old" are different claims, and only the second earns the
 * removal of a word — the same rule `heroStampIsStale` is written to.
 *
 * Pure and exported because a Next.js page may not carry named exports, so this
 * is the only seam a guard can hold.
 */
export function liveClaimIsUnbacked(args: {
  /** `Event.live_probability_pinned` — present ONLY when the server says so. */
  pinned: unknown;
  /**
   * Age of the freshest write across the blend's sources, in ms. `null` when
   * nothing on the page is stamped.
   *
   * The BLEND's age (`freshestSourceStamp`, a max across sources) and not the
   * glance's (`heroStamp`, a min across facts) — deliberately the same input
   * #5069's caption reads, because both are claims about the number rather than
   * about the whole hero. Using the glance here would strip "LIVE" off a
   * ten-second-old probability whenever a score on a ten-minute beat happened to
   * be the older fact.
   */
  blendAgeMs: number | null;
  maxBlendAgeMs?: number;
}): boolean {
  const { pinned, blendAgeMs } = args;
  if (pinned) return true;
  if (blendAgeMs === null || !Number.isFinite(blendAgeMs)) return false;
  return blendAgeMs > (args.maxBlendAgeMs ?? LIVE_CLAIM_MAX_BLEND_AGE_MS);
}

/**
 * The EVENT PAGE's answer to the same question — the one the hero, the phase
 * badge, the age stamp and the refresh ring all read. (#5885)
 *
 * ═══ WHY IT IS NOT `liveClaimIsUnbacked` ═══
 *
 * A claim of liveness cannot be unbacked on a page that has not made one. The
 * predicate above is keyed on the blend alone and must stay that way — it is a
 * statement about our number's age and nothing else — but the page composes it
 * with `hasNoReportedResult` into `isSuspended`, and a bare age rule reaching
 * that disjunct put the suspended badge on a game that had not kicked off.
 *
 * Measured on production 2026-09-13 10:09Z, /events/14780147: `status
 * "scheduled"`, kickoff 20:25Z — ten hours away — sources at 08:52:40Z,
 * 09:06:12Z and 09:08:03Z, so a 61-minute blend, so "No result reported" over a
 * hero that had read "Starts in 10h 34m" twenty minutes before. It also deleted
 * `Projected final: 28 – 19`, which the same flag gates under #5257.
 *
 * `LIVE_CLAIM_MAX_BLEND_AGE_MS` is not wrong; it was being asked the wrong
 * question. Its own reasoning is about a live game on a two-minute beat. A
 * pregame market is polled slowly by design, so an hour-old blend hours before
 * kickoff is the ordinary state of a healthy page.
 */
export function pageLiveClaimIsUnbacked(args: {
  /** `commence_time` is in the past. The page already computes this. */
  hasStarted: boolean;
  pinned: unknown;
  blendAgeMs: number | null;
  maxBlendAgeMs?: number;
}): boolean {
  if (!args.hasStarted) return false;
  return liveClaimIsUnbacked(args);
}

export interface LiveFrame {
  p: number;
  source: string;
  source_value?: number | null;
  updated_at: string;
}

/**
 * A pushed frame applied to whatever the cache currently holds.
 *
 * The spread is the important part and it runs in this order on purpose: `prev`
 * first, then only the fields the frame actually speaks for. A frame knows one
 * probability. It must never be able to reinstate an older copy of anything
 * else — so when the background poll above lands a newer games line, the next
 * frame carries it forward rather than reverting it.
 */
export function applyLiveFrame<T>(prev: T | undefined, frame: LiveFrame): T | undefined {
  if (!prev) return prev;
  // A source entry carries display metadata (`display_name`, `type`, `color`)
  // that a frame cannot know, so the merge is structural and the type is
  // asserted at this one boundary — the same escape the inline version made
  // with `as never`, named instead of scattered. What actually guarantees the
  // spread preserves everything else is the behavioural test, not this cast.
  const sources = ((prev as { win_probability_sources?: Record<string, Record<string, unknown>> })
    .win_probability_sources ?? {}) as Record<string, Record<string, unknown>>;
  const existing = sources[frame.source] ?? {};
  return {
    ...prev,
    // `resolveProbability` reads `hero_probability` first on the live branch, so
    // this is the number the hero actually renders.
    hero_probability: frame.p,
    hero_probability_away: 1 - frame.p,
    win_probability_sources: {
      ...sources,
      [frame.source]: {
        ...existing,
        value: frame.source_value ?? frame.p,
        updated_at: frame.updated_at,
      },
    },
  } as unknown as T;
}
