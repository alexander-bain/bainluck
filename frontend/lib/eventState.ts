/**
 * How a surface reads an event's state — one module, so no two surfaces
 * disagree about what a status MEANS.
 *
 * This exists because `suspended` (live/048) landed in a vocabulary that every
 * card and page had been reading with its own inline `=== "closed"` chain. Each
 * of those chains buckets an unrecognised status into the "upcoming" branch by
 * falling through, and the upcoming branch renders a START TIME — so a match
 * suspended for rain would have advertised itself as about to begin. That is a
 * quieter lie than "Final", not a smaller one.
 *
 * The rule the ladder gives us (EVENT-GRAPH-DOCTRINE §R):
 *
 *   - `live`      — something that watches the match says it is being played.
 *   - `suspended` — the clock ran out and NOTHING that watches it said it
 *                   ended. Asserts no outcome. Never Final, never a start time.
 *   - `completed` / `closed` — something with standing said it is over.
 *
 * Keep this in step with `EventStatus` in `lib/types.ts` and with
 * `SETTLED_STATUSES` in `backend/app/utils/event_completion.py`.
 */

/** Something with standing said this event is over. Renders as Final. */
export function isFinishedStatus(status: string | null | undefined): boolean {
  return status === "completed" || status === "closed";
}

/**
 * The clock ran out and no authority, venue settlement or score feed said the
 * match ended. Non-terminal: it can still go back to `live`, and it can still
 * be settled later by something that actually watched.
 */
export function isSuspendedStatus(status: string | null | undefined): boolean {
  return status === "suspended";
}

/**
 * How long past its own kickoff a `scheduled` row is still plausibly about to
 * start.
 *
 * 🔴 THIS NUMBER IS ALSO IN PYTHON and the two must not drift:
 * `UPCOMING_GRACE` in `backend/app/utils/event_completion.py` is the bound the
 * rails SELECT on, and this is the bound the card RENDERS on. If the backend's
 * were larger, a row would reach a surface that then printed a start time for
 * it — the exact fall-through this module exists to refuse — and if smaller, a
 * card would say "No result reported" about a fixture the rail still calls
 * upcoming. `__tests__/lib/railGraceMatchesTheBackend3211.test.ts` reads the
 * Python source and fails on any disagreement, because a comment asking two
 * languages to stay in step is not a mechanism.
 */
export const UPCOMING_GRACE_MS = 2 * 60 * 60 * 1000;

/**
 * A row that still calls itself `scheduled` well after its own kickoff.
 *
 * ── #3211, AND WHY IT IS NOT A NEW STATE ──
 *
 * `suspended` means a source watched the match and stopped reporting. This
 * means nothing ever reported anything — the fixture's clock ran out while the
 * row still said it had not begun. On production 2026-09-05 there were 171 of
 * them across the two US Open tours, all `commence_time_source = kalshi_ticker`
 * and all stamped exactly `00:00:00Z`, because a Kalshi row's commence is the
 * ticker's CLOSE date rather than a start (gotcha #14) and tennis has no ESPN
 * anchor to settle it afterwards (#2700).
 *
 * To the person reading a card those two states are ONE sentence — *this match
 * should have happened and nobody has told us anything* — so they render as one
 * (`SUSPENDED_LABEL`) and bucket as one. Inventing a second badge would ask a
 * reader to care about which of our sources failed.
 *
 * ⚠️ It takes a TIME, so unlike every other predicate here it can change answer
 * without the row changing. `now` is a parameter for that reason: a component
 * that closes over `Date.now()` at render is correct, and a test that pins the
 * clock is the only way to assert the boundary at all (gotcha #44 — offset from
 * an injected anchor, never branch on the real clock).
 *
 * An absent or unparseable `commence_time` is FALSE. A row we cannot place on
 * the clock is one we have no standing to move off the schedule, and `new
 * Date("").getTime()` is `NaN`, which compares false against everything — so
 * the guard is written out rather than left to that accident.
 */
export function startedWithoutResult(
  status: string | null | undefined,
  commenceTime: string | null | undefined,
  now: number = Date.now(),
): boolean {
  if (status !== "scheduled") return false;
  if (!commenceTime) return false;
  const t = new Date(commenceTime).getTime();
  if (!Number.isFinite(t)) return false;
  return t < now - UPCOMING_GRACE_MS;
}

/**
 * THE DISPLAY QUESTION every card and section actually asks: has this match
 * passed the point of being upcoming without anyone reporting how it went?
 *
 * True for `suspended` and for {@link startedWithoutResult}. This — not
 * `isSuspendedStatus` — is what a SURFACE should call, because a surface is
 * choosing between "print a start time" and "say no result was reported", and
 * that choice has the same right answer for both states.
 *
 * `isSuspendedStatus` stays, and stays narrow: it answers "is the status
 * literally `suspended`", which is the right question for anything reasoning
 * about the ladder's own vocabulary rather than about pixels.
 */
export function hasNoReportedResult(
  status: string | null | undefined,
  commenceTime: string | null | undefined,
  now: number = Date.now(),
): boolean {
  return isSuspendedStatus(status) || startedWithoutResult(status, commenceTime, now);
}

/**
 * The short badge a suspended event wears.
 *
 * Deliberately NOT "Suspended" as a bare word: for a rain-delayed US Open match
 * that reads right, but the same state also covers a fixture whose only source
 * went dark, and telling a user that match is "suspended" invents a stoppage
 * nobody reported. What both cases actually share is that no result was ever
 * reported, so that is what the badge says.
 */
export const SUSPENDED_LABEL = "No result reported";

/**
 * The longer form, for surfaces with room for a sentence.
 *
 * Present tense only, and that is a constraint rather than a style note: the
 * shipped-copy ban rejects "we will update it if a source confirms the finish"
 * as will-populate language, and it is right to. A promise about a future
 * update is not a description of the state, and this state's whole job is to
 * describe exactly what is and is not known right now.
 */
export const SUSPENDED_DESCRIPTION =
  "This match left the live board and no source has reported a result.";

/**
 * The badge a match wears when a source that carried its markets has settled
 * them, while nothing has reported a score to us (#6381).
 *
 * NOT "Final". `completed`/`closed` mean something with standing said the match
 * ended, and this row's status still says otherwise — the ladder's word would
 * be a claim we cannot make. "Settled" is the word the rest of the app already
 * uses for a question whose answer is in (`eventConceptDisplay`,
 * `propDivergence`), and it is the honest one here: the markets are graded, the
 * scoreboard never arrived.
 */
export const VENUE_SETTLED_LABEL = "Settled";

/**
 * The sentence behind {@link VENUE_SETTLED_LABEL}, on the `title` where
 * `SUSPENDED_DESCRIPTION` sits — standing notice 34 keeps the explanation off
 * the page body, and this state needs one more than most: a reader who watched
 * the badge say "No result reported" yesterday is owed the reason it no longer
 * does.
 */
export const VENUE_SETTLED_DESCRIPTION =
  "The markets on this match have been settled.";

/**
 * What the hero says INSTEAD of {@link SUSPENDED_LABEL} when the venue has
 * already graded the match — or `null` when it has not, which is the caller's
 * signal to keep the sentence it was printing.
 *
 * ── #6381: THE PAGE DENIED A RESULT IT WAS DRAWING ONE SCREEN BELOW ──
 *
 * `/events/15310639` (Liverpool FC v Fulham FC, tier 1) served `scheduled`,
 * both scores null and the hero badge "No result reported", while its own
 * markets on the same payload read `Correct Score · Draw 0-0 · Won`, graded
 * three days earlier. 1,471 events all-time make that contradiction; 68 of them
 * also hold the score.
 *
 * ⚠️ THIS DOES NOT TOUCH {@link hasNoReportedResult}, AND THAT IS THE DESIGN.
 * That predicate is shared card vocabulary keyed on status and time alone
 * (#3211), and the producer's guard reddens if it grows a fourth arm. Every
 * other consumer of the page's `isSuspended` — the suppressed countdown
 * (#3211), the suppressed projected final (#5257), the map's past-tense marks
 * (#5206) — is still RIGHT about a venue-settled match: there is nothing left
 * to forecast and no update to promise. Only the SENTENCE was wrong, so only
 * the sentence moves.
 *
 * The result is printed VERBATIM. It is an outcome name, not a score, and its
 * shape is the sport's: `"Draw 0-0"`, `"Brighton & Hove Albion wins 5-0"`,
 * `"Aryna Sabalenka wins 2-0"` (sets). The producer already refused the
 * lookalikes — `1st Half Correct Score`, `First Team to Score` — by
 * segment-exact market name, and both of those were live on the specimen event
 * itself, so a client that re-derived anything here would be the second place
 * that judgement lives and the first place it drifts.
 *
 * A settled match with NO graded score prints the badge alone — the tennis
 * shape, where 16 prop grades settle the event and no market ever quoted a
 * scoreline. Deliberately not "Settled · no score": on a page whose sibling
 * states print real scorelines, "no score" reads as 0-0, which is a result we
 * do not have. Saying less is the only way to say nothing false.
 */
export function venueSettledSummary(
  venueSettled: boolean | null | undefined,
  venueSettledResult: string | null | undefined,
): string | null {
  if (!venueSettled) return null;
  const result = venueSettledResult?.trim();
  return result ? `${VENUE_SETTLED_LABEL} · ${result}` : VENUE_SETTLED_LABEL;
}

/**
 * Which side a surface paints FIRST when it prints a pair of scores.
 *
 * Not a preference and not a style token — a fact about a specific component,
 * which each caller reads off its own markup and passes in.
 */
export type ScoreOrder = "away-home" | "home-away";

/**
 * The one line every card prints for a suspended event — ONE function, because
 * CERT-786 blocked on four surfaces reading this state four different ways and
 * three of them not reading it at all.
 *
 * It carries the LAST SCORE when there is one, and that is the substance of the
 * fix rather than a decoration. The badge alone says what is not known; the
 * score says what is, and the pair is the whole honest statement a suspended
 * match can make: play reached 1-2 and nothing since has spoken. A card that
 * printed only "No result reported" beside two visible team crests invites the
 * reader to supply the missing half themselves.
 *
 * SIDE ORDER FOLLOWS THE SURFACE, and is therefore an argument (#2786).
 *
 * It was a hardcoded away-home, justified as "matching every card in the app".
 * That premise was measured and is FALSE for three of the four callers: the
 * shared `EventCard` prints home-away in its FINAL block, its live scores and
 * its `Proj` footer; `FeedCard` prints `{home} - {away}` in the very SAME SLOT
 * this string occupies, so a live 3-6 became "last score 6-3" the moment the
 * match stopped, with no change in play; and the event page's hero stacks home
 * above away. Only the Discover card paints away first, and it still does.
 *
 * On production 2026-09-03 that shipped an inverted score: event 15293347
 * (`home_score=3`, `away_score=6`) rendered "last score 6-3" on a card listing
 * the HOME team directly above it, one glance from its settled twin's "3 – 6".
 *
 * So the shared string is still one string — but the ORDER it prints is the
 * order the surface around it already uses, because the alternative is a
 * function that standardises the wrong half and makes each card contradict
 * itself. The state exists to refuse a quiet lie; an inverted score is one.
 *
 * The parameter is REQUIRED on purpose: a new caller must state what its own
 * card does rather than inherit a default that may not be true of it.
 *
 * A partial line (one side scored, the other null) prints the badge alone. Half
 * a score under a "last score" label is the same partial-line trap that graded
 * the CERT-752 specimen 1.0/0.0, told smaller.
 */
export function suspendedSummary(
  awayScore: number | null | undefined,
  homeScore: number | null | undefined,
  order: ScoreOrder,
): string {
  if (awayScore == null || homeScore == null) return SUSPENDED_LABEL;
  const [first, second] =
    order === "home-away" ? [homeScore, awayScore] : [awayScore, homeScore];
  return `${SUSPENDED_LABEL} · last score ${first}-${second}`;
}

/**
 * The word the phase badge prints when an event is NOT live, NOT final and NOT
 * {@link hasNoReportedResult} — i.e. the branch that speaks about its START.
 *
 * ── #6031: THE TWO-HOUR HOLE ──
 *
 * `startedWithoutResult` only fires past {@link UPCOMING_GRACE_MS}, so a
 * `scheduled` row between its own kickoff and the two-hour mark is neither live
 * nor "no result reported" — and the badge's old inline ternary
 * (`countdown && !hasStarted ? … : "Pregame"`) sent it to the literal word
 * **Pregame**. #3211 had already fixed the louder half of that lie by
 * suppressing the countdown, which left the page suppressing a countdown to a
 * moment in the past while still calling the match pregame, directly above a
 * chart labelled "Since Start". Measured on production 2026-09-13: event
 * 15308588 (Barcelona v Delfin), 77 minutes past its served kickoff
 * (`artifacts/live-216/barcelona-delfin-pregame-0010Z.png`).
 *
 * EVERY match passes through this window — a row is `scheduled` until a source
 * flips it to `live` — so this is the badge a reader sees when they tap a card
 * at kickoff, not a rare tail state. It lasts seconds where ESPN anchors the
 * fixture and up to the full two hours where nothing does (tennis, #2700).
 *
 * ⚠️ THE GRACE IS NOT THE BUG AND MUST NOT BE WIDENED TO CLOSE THIS. Making
 * `startedWithoutResult` fire sooner would print "No result reported" over a
 * match twenty minutes in, which is false and is the precise claim the grace
 * exists to refuse. The repair is the WORD, and only the word.
 *
 * "Started" and not "Underway"/"In progress": `hasStarted` is
 * `commence_time <= now` and nothing more, so the only thing this branch has
 * standing to say is that the scheduled start has passed. The stronger words
 * assert play is happening, which is exactly what no source has told us — that
 * is why the row is still `scheduled` and why the badge is amber rather than
 * the live branch's pulsing emerald.
 *
 * Lives here rather than inline for the reason #5885 moved `hasStarted` into
 * `pageLiveClaimIsUnbacked`: a Next.js page carries no named exports, so a
 * ternary in the JSX is a decision no test can hold.
 */
export function startBadgeLabel(
  hasStarted: boolean,
  countdown: string | null | undefined,
): string {
  if (hasStarted) return "Started";
  return countdown ? `Starts in ${countdown}` : "Pregame";
}

/**
 * Whether the hero's blend caption must drop the word "Live" (#2800).
 *
 * ── WHY AN AGE TEST ALONE CANNOT ANSWER THIS ──
 *
 * #5069 removed "Live" from a blend past its own freshness boundary, and the
 * boundary it spends is an AGE (`heroStampIsStale(stamp, "price")`, 120s). That
 * is the right test for a source that went dark. It cannot see the other way a
 * number stops being current: a price that is rewritten punctually with an
 * IDENTICAL value.
 *
 * Measured on production 2026-09-14 07:26Z, `/events/15312054` (Peliwo v
 * Ziegann, ATP): `live_probability_pinned` read `{pinned: true, probability:
 * 0.99, observations: 84, span_seconds: 5247}` — 84 reads over 87 minutes, all
 * 0.99, over a chart flat at 99% for the whole match. The page's own age badge
 * said `1m ago`, so `heroStampIsStale` was FALSE and the caption said
 * "Live · Bain Luck blend" — one line under a phase badge that already said
 * "No result reported". A frozen price that is refreshed on schedule is new and
 * unchanging at once, so it is permanently fresh to an age test.
 *
 * ── THE RULE IS ALREADY WRITTEN, ONE CONSUMER OVER ──
 *
 * `LiveAgeStamp` takes `claimWithdrawn` and comments it "#5459 — a withdrawn
 * claim takes the stale presentation whatever the age says. OR rather than a
 * replacement: an old number is still old when nobody withdrew anything." This
 * is that same OR, for the caption, which `page.tsx:356` should already have
 * covered: `effectivelyLive` exists so that "everything on this page that
 * ASSERTS motion reads this", and "Live · Bain Luck blend" asserts motion. The
 * caption was simply not on that list.
 *
 * ── WHAT THIS DELIBERATELY DOES NOT DO ──
 *
 * It does not withdraw the number. Standing notice 34 and #5069 both say the
 * repair is removing a word rather than adding a sentence, and a pinned match
 * is not the same state as a `suspended` one: the venue still lists it and the
 * book is still quoted at 0.99, so blanking the hero would assert LESS than we
 * know. `status='suspended'` keeps its own `No price` answer, reached through
 * `isLive === false`, and is untouched here.
 *
 * Lives here rather than inline for the same reason as {@link startBadgeLabel}:
 * a Next.js page carries no named exports, so a conjunction spelled in the call
 * is a decision no test can hold.
 */
export function blendCaptionIsStale(
  stampIsStale: boolean,
  liveClaimUnbacked: boolean,
): boolean {
  return stampIsStale || liveClaimUnbacked;
}

/**
 * The section a status belongs to on every grid surface that groups events.
 *
 * `suspended` returns "live" — NOT because a suspended match is being played,
 * but because the three buckets answer "has this happened yet?" and the honest
 * answer for a suspended row is the same as a live one: it started, it has not
 * finished. Filing it under "upcoming" (which is where every surface put it by
 * falling through) claims it has not started; filing it under "finished" claims
 * a result. Both are the lie this state exists to refuse.
 *
 * The section TITLE changes when the bucket holds one — see
 * `liveSectionTitle` — so the header does not claim "Live Now" over a match
 * nobody is watching.
 *
 * ── #3211: `commenceTime` IS OPTIONAL AND THAT IS A COMPROMISE, NOT A DEFAULT ──
 *
 * A `scheduled` row past its own kickoff belongs in the same bucket for exactly
 * the reason `suspended` does: "upcoming" claims it has not started, and it
 * has. But answering that needs the row's TIME, which the original signature
 * did not take.
 *
 * Callers that omit it get the old behaviour — such a row falls through to
 * "upcoming" — and that is deliberately not an error, because the surfaces
 * whose backend window cannot yet return one of these rows (Discover and the
 * feed sections, whose candidate window is unchanged by #3211) would otherwise
 * be forced to pass a time in order to enable a branch nothing can reach. The
 * three surfaces that CAN reach one pass it: `lib/sports/leagueSections`,
 * `app/my-stuff` and this module's own guard.
 *
 * ⚠️ So the omission is a live edge: when the feed's window is widened, its
 * `eventSectionKey` call is the second half of that change.
 * `__tests__/lib/startedWithoutResultIsNotUpcoming3211.test.ts` pins BOTH arms
 * so neither can be altered by accident.
 */
export function eventSectionKey(
  status: string | null | undefined,
  commenceTime?: string | null,
  now: number = Date.now(),
): "live" | "finished" | "upcoming" {
  if (status === "live" || isSuspendedStatus(status)) return "live";
  if (isFinishedStatus(status)) return "finished";
  if (startedWithoutResult(status, commenceTime, now)) return "live";
  return "upcoming";
}

/**
 * What the live section calls itself, given what landed in it.
 *
 * "Live Now" over a rain-delayed match is the section-header sized version of
 * the same false claim the card branch fixes, so the header reads the bucket
 * rather than assuming it. Shared by `/sports`, the category grids and My
 * Stuff so the three cannot drift.
 */
export function liveSectionTitle(hasSuspended: boolean): string {
  return hasSuspended ? "Live & Paused" : "Live Now";
}
