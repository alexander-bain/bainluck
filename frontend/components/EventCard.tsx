"use client";

import { useEffect } from "react";
import { useSpring, useTransform } from "framer-motion";
import { motion } from "@/components/motion";
import type { Event } from "@/lib/types";
import { getSportLabel } from "@/lib/sportCategories";
import { useAnalytics } from "@/hooks";
import { cn } from "@/lib/utils";
import EventCardShell from "./EventCardShell";
import PersonalizedBadge from "./PersonalizedBadge";
import ProbabilityBar from "./ProbabilityBar";
import EntityImage from "./EntityImage";
import { isInternationalSport, flagUrl, espnTeamLogoByName } from "@/lib/images";
import { teamColorStyle } from "@/lib/teamColors";
import TeamNameLink from "./TeamNameLink";
import { shouldWithholdProbability } from "@/lib/probabilityEvidence";
import { renderedDuelPercents } from "@/lib/renderedPercent";
import { awayIsTheComplement } from "@/lib/drawPricedWinner";
import { PREMATCH_SAID, prematchReading } from "@/lib/prematchReading";
import { teamCrestInitials, teamShortNames } from "@/lib/teamShortName";
import { formatFinishedGameLabel, formatLiveClockLabel } from "@/lib/gameTimeLabel";
import type { HostCue } from "@/lib/sameFixtureHostCue";
import { providerGameNumber } from "@/lib/teamGames";
import { PinIcon } from "@/components/PinButton";
import {
  hasNoReportedResult,
  isFinishedStatus,
  suspendedSummary,
  venueSettledSummary,
} from "@/lib/eventState";

type SourceSection = 'featured' | 'sport_category' | 'recently_finished' | 'archived' | 'search_results' | 'pinned' | 'my_stuff';

interface EventCardProps {
  event: Event;
  showSport?: boolean;
  /** Source section for analytics tracking */
  sourceSection?: SourceSection;
  /** Position in list for analytics tracking */
  positionIndex?: number;
  /** Optional highlight label from backend */
  highlightLabel?: string | null;
  /** Whether the event is pinned */
  isPinned?: boolean;
  /** Callback when pin is toggled */
  onPinToggle?: (eventId: number) => void;
  /** Whether max pins has been reached (disable pin button) */
  pinDisabled?: boolean;
  /** Whether this item was personalized by the feed */
  personalized?: boolean;
  /** Personalization multiplier */
  multiplier?: number;
  /** Personalization reason strings */
  personalizationReasons?: string[];
  /**
   * #7529 — the host, printed ONLY when a sibling in the same list is the same
   * two clubs at the same minute (an NHL preseason split-squad home-and-home is
   * the case that produced this). A card cannot see its siblings, so the LIST
   * decides: `hostCuesForEvents(events).get(event.id) ?? null`. Absent on every
   * unambiguous card, which is all but a handful — see `lib/sameFixtureHostCue`
   * for why this is not a venue line on every card (notice 34 / D102).
   */
  hostCue?: HostCue | null;
}

// ---------------------------------------------------------------------------
// AnimatedProbability — smoothly counts between ALREADY-RESOLVED whole percents
// ---------------------------------------------------------------------------
//
// #2787: this took a raw probability and did its own `Math.round(v * 100)`
// inside `useTransform`, which is what put the card's two chips outside the
// rendered-percent contract. The rounding happens on the SPRING's output, so a
// per-side `renderedPercent` at the call site would have been discarded — the
// contract has to be applied to the spring's TARGET. So the target is the whole
// percent now, and this component only animates towards it.
function AnimatedProbability({
  percent,
  className,
}: {
  percent: number | null;
  className?: string;
}) {
  const springValue = useSpring(percent ?? 0, {
    stiffness: 80,
    damping: 20,
    mass: 0.5,
  });
  const display = useTransform(springValue, (v: number) => `${Math.round(v)}%`);

  // Update spring target when value changes
  useEffect(() => {
    springValue.set(percent ?? 0);
  }, [percent, springValue]);

  if (percent === null) {
    return <span className={className}>-</span>;
  }

  return <motion.span className={className}>{display}</motion.span>;
}

// ---------------------------------------------------------------------------
// ParticipantCrest — the 20px square (or 20x15 flag) at the head of a team row
// ---------------------------------------------------------------------------
//
// #3784. This was two identical inline chains, one per row, differing only in
// which CSS colour var the initials square took. Adding a fourth and fifth rung
// to a chain that exists twice is how the two rows drift apart, so the ladder is
// stated ONCE and each row names its side.
//
// PRECEDENCE, and the order is the whole decision — it mirrors `FeedCard`'s
// exactly, because "the two cards disagree about the same match" is the bug
// being fixed and a second opinion about ordering would re-open it:
//
//   1. the served headshot — a picture of the person, the best answer;
//   2. the served flag — what every draw sheet has printed for fifty years,
//      and the right answer for the registered players with no face;
//   3. the country flag this card already resolved for international TEAM
//      sports (`flagUrl()` by country name);
//   4. the club crest — `logo_small`, then `espnTeamLogoByName()`;
//   5. initials, unchanged, which stays the honest fallback for a player the
//      register has never heard of.
//
// A served value can never displace a crest for a team sport, because the
// server only fills these keys for individual ones.
//
// A FACE IS SQUARE AND A FLAG IS 20x15. Which box gets drawn follows what is
// ACTUALLY being rendered, never what the sport usually gets — a headshot
// squashed into a flag's letterbox is the defect this distinction prevents.
// The face takes `object-cover` so a portrait crop is cropped rather than
// squashed; a flag keeps `object-cover` at its own ratio and a crest keeps
// `object-contain`, which is what each was already doing.
function ParticipantCrest({
  name,
  servedFace,
  servedFlag,
  countryFlagUrl,
  crestUrl,
  colorVar,
}: {
  name: string;
  servedFace: string | null;
  servedFlag: string | null;
  countryFlagUrl: string | null;
  crestUrl: string | null;
  colorVar: string;
}) {
  if (servedFace) {
    return (
      <img
        src={servedFace}
        alt={name}
        width={20}
        height={20}
        loading="lazy"
        data-testid="event-card-participant-face"
        className="w-5 h-5 object-cover rounded-sm flex-shrink-0"
      />
    );
  }
  const flag = servedFlag || countryFlagUrl;
  if (flag) {
    return (
      <img
        src={flag}
        alt={name}
        width={20}
        height={15}
        loading="lazy"
        data-testid="event-card-participant-flag"
        className="w-5 h-[15px] object-cover rounded-sm flex-shrink-0"
      />
    );
  }
  if (crestUrl) {
    return (
      <img
        src={crestUrl}
        crossOrigin="anonymous"
        alt=""
        width={20}
        height={20}
        loading="lazy"
        className="w-5 h-5 object-contain flex-shrink-0"
      />
    );
  }
  return (
    <div
      className="w-5 h-5 rounded-sm flex-shrink-0 flex items-center justify-center text-[9px] font-bold text-white/90"
      style={{ backgroundColor: `rgb(var(${colorVar}))` }}
    >
      {teamCrestInitials(name)}
    </div>
  );
}

export default function EventCard({
  event,
  showSport = true,
  sourceSection = 'sport_category',
  positionIndex = 0,
  highlightLabel,
  isPinned = false,
  onPinToggle,
  pinDisabled = false,
  personalized,
  multiplier,
  personalizationReasons,
  hostCue = null,
}: EventCardProps) {
  const { trackEventCardClick } = useAnalytics();
  const gameNumber = providerGameNumber(event);

  // Handle pin button click (prevent navigation)
  const handlePinClick = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (onPinToggle) {
      onPinToggle(event.id);
    }
  };
  const odds = event.current_odds;
  const opening = event.opening_odds;

  // UX-P166 — the live footer's "Opened 62/38" prints both sides of one question
  // in fixed positions, which makes it a duel. Rounding the two independently
  // printed 101 whenever the opening line landed on a half-percent: measured on
  // production 2026-08-29, 207 of 24,117 events carrying an opening line do, and
  // none print 99. The away side is derived as `1 - home` when absent, exactly as
  // before, which is precisely what makes the pair an exact complement and the
  // both-sides-round-up case reachable.
  //
  // #2787 AMENDMENT: that reasoning was right and its SCOPE was wrong. The
  // HEADLINE CHIPS print both sides of the same question in fixed positions too
  // — home above, away below — so they are the same duel, and they were not
  // going through this. See `chipAwayPct`/`chipHomePct` below.
  const [openedAwayPct, openedHomePct] = renderedDuelPercents(
    opening?.away_probability ?? (opening ? 1 - opening.home_probability : null),
    opening?.home_probability,
  );

  // Determine which probability to display based on game status
  let homeProb: number | null;
  let awayProb: number | null;

  if (isFinishedStatus(event.status) && opening) {
    homeProb = opening.home_probability;
    awayProb = opening.away_probability;
  } else if (shouldWithholdProbability(event)) {
    // UX-P042 (#1640) — the only evidence is an untraded Polymarket midpoint, so
    // `current_odds` reads a confident 0.5/0.5 built from nothing. Show no number.
    homeProb = null;
    awayProb = null;
  } else if (!odds) {
    // ═══ #4797 — THE CARD STOPS SAYING "NO PRICE YET" OVER A PRICE IT HOLDS ═══
    //
    // WHAT A READER SAW. `/search?q=chiefs`, 2026-09-19, one screenshot:
    // the GAMES card for `15313996` Lamontville Golden Arrows v Kaizer Chiefs
    // printed `No price yet` while the ANSWERS card ~400px below it printed
    // `Kaizer Chiefs 47%` for the same fixture. Not a missing number — the page
    // disagreeing with itself in one scroll.
    //
    // THE MECHANISM (lane1/233, measured 2026-09-10; re-measured today). The
    // blend IS computed and IS served: `hero_probability = 0.225`,
    // `hero_probability_source = "blend"`, `win_probability_sources` carrying a
    // verified Polymarket reading. This card read `current_odds` and nothing
    // else, and no sportsbook ever priced the fixture, so both sides came out
    // null and the #2882 no-reading chrome fired over a served price. Across ten
    // search queries on production today: 20 of 146 rows are in this state.
    //
    // ⚠️ THE AWAY SIDE IS NULL ON EXACTLY THE ROWS THIS RESCUES, AND THAT IS
    // CORRECT, NOT A HOLE. `resolve_hero` always builds away as `1 − home`, and
    // `routes/events.py` then runs it through `printable_away` — so on a
    // draw-priced sport the server withholds it for #6238's reason before we
    // ever see it. 19 of 21 rows on the specimen's own payload carry an away
    // figure; the one row that does not is the one row this arm exists for. The
    // fallback therefore hands `awayProb` the served `null` and lets
    // `awayWithheld` below do what it already does: home keeps its number and
    // its full-size treatment, the away slot prints nothing. Deriving `1 − 0.225`
    // here would put 78% under Kaizer Chiefs on a 22.5 / 47 / ~30 three-way
    // market — the exact fabrication #6238 exists to stop.
    //
    // WHY THIS ARM AND NOT THE OTHERS:
    //  * `odds` PRESENT wins, always. This is a last rung, not an override, and
    //    gating on `!odds` makes "no row that renders today changes" structural:
    //    the arm is unreachable whenever `current_odds` exists, and when it does
    //    not, today's answer is null on both sides.
    //  * `shouldWithholdProbability` is deliberately ABOVE this. An untraded
    //    Polymarket midpoint produces a `hero_probability` of exactly 0.5 too
    //    (UX-P042/#1640's specimen is that payload), so reading the hero first
    //    would re-publish the fabricated coin flip the gate exists to refuse.
    //  * A FINISHED ROW IS NOT EXCLUDED HERE, AND THAT IS A DELIBERATE
    //    NON-GUARD. It wants one: on a finished card these two slots hold the
    //    OPENING line — the #2764 pre-match prior, grey beside each name — and a
    //    finished hero is either `settled` (1.0/0.0) or `final_unresolved`
    //    (whatever price was last captured before capture stopped; Q441/#1495
    //    measured 5 of 44 games publishing the LOSER as favourite). Production
    //    carries the row: `15291547` is `closed`, `final_unresolved 0.91`, no
    //    opening line. But an `!isFinishedStatus(...)` clause here SURVIVES its
    //    mutant, because on a finished card `homeProb`/`awayProb` are read by
    //    nothing — the chips, the bar and the no-reading sentence are each gated
    //    `!isFinished`, and `isLive` cannot be true beside it. A guard that
    //    cannot be killed is a guard that proves nothing, so the protection is
    //    put where it IS killable: ARM 8 of `searchCardReadsItsHero4797` asserts
    //    that a closed row with a 0.91 hero prints no percent, and it goes red
    //    the moment any of those render gates is un-gated. Un-gate one and the
    //    test names this paragraph.
    //
    // A SUSPENDED row gains a reading here and still prints nothing, because
    // every print site below is already gated `!isSuspended` (CERT-792: a stale
    // live blend is not a statement a suspended card may make). That is the
    // intended outcome, pinned by an arm, and it is why the two original
    // specimens on this issue — both `suspended` — are not what closes it.
    homeProb = event.hero_probability ?? null;
    awayProb = event.hero_probability_away ?? null;
  } else {
    homeProb = odds?.home_probability ?? null;
    awayProb = odds?.away_probability ?? null;
  }

  // #2787 — the fourth arm of #2084/#2085/#2279. The chips below print
  // `homeProb` and `awayProb` in two fixed slots of one card, and each side was
  // rounded ALONE inside `AnimatedProbability`, so an exact complement pair
  // landing on a half-percent on both sides rounded up twice: measured on
  // production 2026-09-03, `/sports/tennis_atp_us_open` printed 82/19, 20/81
  // and 18/83 on three of ~16 upcoming cards. Resolved ONCE here, as a pair, and
  // handed to the chips already whole — never a per-side round at the leaf.
  //
  // `homeFavorite` deliberately still reads the raw probabilities: which side is
  // emphasised is a comparison, not a printed number, and it must not flip on a
  // rounding tie.
  const [chipAwayPct, chipHomePct] = renderedDuelPercents(awayProb, homeProb);

  // ═══ #6238 — NO AWAY NUMBER ON A SPORT THAT PRICES A DRAW ═══
  //
  // The shared card: `/sport/[sport]/[league]`, team pages, search. Every away
  // figure it can print — the live/pregame chip, the `Opened X/Y` footer, the
  // settled per-team prior — is `1 − home`, which on soccer is "home does not
  // win": away win OR draw, wearing the away team's name. The argument, the
  // payload checks and the production specimens are in `lib/drawPricedWinner.ts`.
  //
  // `awayProb` itself is deliberately NOT nulled here. It feeds `noReading`,
  // `homeFavorite` and the rounding pair, and blanking it at the top would make
  // a priced match look unpriced and hand every draw-priced card a permanent
  // "home favourite". The question this rule asks is only ever "may this surface
  // PRINT the away number", so it is asked at the print sites.
  // PER PAIR — see `awayIsTheComplement`. The chips read `current_odds`, which
  // production serves as an exact complement on every soccer row measured; the
  // `Opened` footer below reads `opening_odds`, which since #1011 is de-vigged
  // over the whole board and usually is NOT a complement. Asking once for the
  // whole card would delete a real opening away price on 11 of 13 live rows.
  const awayWithheld = awayIsTheComplement(awayProb, homeProb, event.sport);

  // With the away side withheld there is no pair, so there is no favourite to
  // name — `homeProb >= awayProb` is a comparison against the very number this
  // ship refuses to state. This file already has the answer for that shape
  // (`noReading`, a suspended card, a finished card with no winner): equal
  // weight is the only honest pair when the comparison is missing.
  const favoriteKnown = !awayWithheld;

  // The OPENING pair is its own question — see the note on `awayWithheld`. On
  // 11 of 13 live soccer rows measured this answers FALSE where `awayWithheld`
  // answers true, and the footer keeps printing the honest `Opened 62/38`.
  const openedAwayWithheld = awayIsTheComplement(
    opening?.away_probability,
    opening?.home_probability,
    event.sport,
  );

  const handleCardClick = () => {
    trackEventCardClick(event, sourceSection, positionIndex);
  };

  const hasStarted = new Date(event.commence_time).getTime() <= Date.now();
  const isLive = event.status === "live" && hasStarted;
  const isFinished = isFinishedStatus(event.status);
  // #3211 — `hasNoReportedResult`, not `isSuspendedStatus`. The branch below is
  // choosing between printing a START TIME and saying no result was reported,
  // and that choice has the same right answer for a `scheduled` row hours past
  // its own kickoff as it does for a suspended one. Before this, 171 US Open
  // matches that reached no rail at all would, on reaching one, have rendered
  // "Sep 1 5:00 PM" — the upcoming-branch fall-through `lib/eventState.ts`
  // opens by naming as the quieter lie.
  const isSuspended = hasNoReportedResult(event.status, event.commence_time);

  // #7070 — THE CARD STOPS DENYING A RESULT ITS OWN PAYLOAD CARRIES.
  //
  // `/sport/tennis/atp`, phone width: two cards reading "No result reported ·
  // Sep 18" over matches whose detail payload said "Settled · Sanchez
  // Izquierdo wins" in the same minute. 17 of 42 rail rows across eight
  // leagues, measured through the routes; four of those leagues at 0, which is
  // the shape that proves this is the venue's grade and not a relabelling.
  //
  // COMPUTED BESIDE `isSuspended`, NEVER INSTEAD OF IT — the event page's own
  // #6381 comment says why and this is the same decision on the other surface.
  // The flag's other consumers on this card (the withheld live chip, the
  // withheld bar, the pre-match-only reading) are all still right about a
  // venue-settled match: nothing is reporting on it and there is no forecast
  // left. Only the SENTENCE was wrong, so only the sentence moves.
  //
  // `venueSettledSummary` returns null on every row the venue has not graded —
  // including every row on a payload that does not carry the keys at all, which
  // today is every `/api/events` list row — so those cards are untouched.
  const venueSettledSentence = isSuspended
    ? venueSettledSummary(event.venue_settled, event.venue_settled_result)
    : null;

  // #2882 — NEITHER side has a number. This is #3459's rule reaching the league
  // and tour rails: `AnimatedProbability` prints `-` per side and has no notion
  // of both sides being absent, so a card with no price rendered as two dashes
  // and an empty bar in the same chrome as its priced neighbours. Measured on
  // production 2026-09-06 11:20Z, `/api/leagues/tennis_wta` returned FOUR
  // upcoming games and all four had `home_win_probability` and
  // `away_win_probability` null — the whole WTA rail was dashes, during the US
  // Open. Say it in the same words the hero and the play card already use.
  const noReading = homeProb === null && awayProb === null;

  // With no reading there is no favourite, so nothing may be emphasised as one.
  // `(homeProb ?? 0) >= (awayProb ?? 0)` is 0 >= 0 when both are absent, which
  // drew the home side in `text-text-primary` and the away side in
  // `text-text-secondary` — the card naming a favourite off a coin it never
  // flipped. Equal weight is the only honest pair when the number is missing.
  const homeFavorite = (homeProb ?? 0) >= (awayProb ?? 0);

  // #2764 — WHAT THE MARKET GAVE EACH TEAM, ON THE LEAGUE/TEAM/SEARCH CARD.
  //
  // Alex, on /sports at phone width: *"How come none of these show pre-event
  // probability?"* ux/1036 answered that for `FeedCard`, Discover's
  // `components/discover/EventCard.tsx` and the tennis hub. THIS component —
  // the shared card on `/sport/[sport]/[league]`, team pages and search — is a
  // different file and never got it, so it arrived at the same gap from the
  // other direction: `homeProb`/`awayProb` ARE computed from `opening` for a
  // finished event above, and then BOTH probability chips are gated
  // `!isFinished`, so nothing is printed. Its `Opened X/Y` footer is live-only.
  // Net today: a FINAL card here shows a score block and no pre-match figure.
  //
  // Read through `lib/prematchReading.ts` so the ladder, the rounding and the
  // label are one decision rather than a fourth copy of it. `Event` carries no
  // `prematch_odds` key — only `/api/feed` resolves the server-side ladder —
  // so this surface knowingly takes the module's `opening_odds` fallback and
  // wears its `books` label. That is honest rather than lossy: the sole writer
  // of `Event.opening_*` is `_maybe_set_opening_odds`, a sportsbook median
  // (#1841), so `books` is exactly what this number has always been. Passing
  // the key explicitly as `undefined` states that absence rather than letting a
  // future `Event` field silently start feeding an unlabelled rung.
  //
  // live/207 (#3016, #4822) — AND ON A SUSPENDED CARD, for the same reason.
  // CERT-792 was right to drop the live chip, the bar and the footer from a
  // suspended row: all three assert something about a match nothing is
  // reporting on. But `isFinished` alone left the row with NO number from any
  // branch, so a `suspended` card printed "No result reported" and nothing
  // else — while its payload carried `current_odds`, `opening_odds` and a
  // hero probability. Measured on production 2026-09-13: `/search?q=Hanwha
  // Eagles` returned 24 results, 17 of them suspended, and all 17 served an
  // opening line under a blank card. Across the table, 668 of 2,648 suspended
  // events carry `opening_home_probability`.
  //
  // The pre-match reading is the one number a suspended row can state
  // honestly, and it is the number the `closed` card sitting beside it on the
  // same search page already prints: grey, beside each name, labelled
  // `Pre-match · sportsbooks`. It says what the market thought BEFORE, which
  // is true whatever happened afterwards — the opposite of the stale live
  // blend the cert refused. The 820 `scheduled`-past-grace rows carry no
  // opening line at all, so they keep the bare summary; there is nothing to
  // print and the card says so by saying nothing.
  const prematch =
    isFinished || isSuspended
      ? prematchReading({ prematch_odds: undefined, opening_odds: event.opening_odds })
      : null;

  // On FINAL the emphasis follows WHO WON, not who was favoured. Everywhere
  // else on this card `homeFavorite` is the right question, but on a settled
  // card it reads `homeProb`/`awayProb` — which the branch above has already
  // swapped to the OPENING line. So a FINAL card was bolding the pre-match
  // favourite's name while the score block three lines up bolded the winner's,
  // and the card disagreed with itself whenever an underdog won. Printing the
  // prior beside each name makes that contradiction louder, so it is fixed
  // here: the names say what happened, the grey numbers say what was thought.
  //
  // A finished card we cannot name a winner on — either score absent, or a
  // genuine draw — emphasises NEITHER side. Muting both would say "they both
  // lost"; that is the same mistake `noReading` exists to stop one line up, so
  // it gets the same answer: equal weight is the only honest pair when the
  // answer is missing. This is also the state the score block itself declines
  // to render (it is gated on both scores being non-null).
  const winnerKnown =
    event.home_score !== null &&
    event.away_score !== null &&
    event.home_score !== event.away_score;
  const homeWon = winnerKnown && event.home_score! > event.away_score!;
  const awayWon = winnerKnown && event.away_score! > event.home_score!;
  const finishedNameClass = (won: boolean) =>
    !winnerKnown
      ? "text-text-primary"
      : won
        ? "font-semibold text-text-primary"
        : "text-text-muted";
  // live/207 — a SUSPENDED card emphasises neither side, for the same reason a
  // finished card with no winner and a card with no reading do not. Emphasis
  // here is `homeFavorite`, which is computed from `current_odds` — the stale
  // live blend CERT-792 refuses to PRINT. Bolding one name on the strength of
  // a number we decline to show is that claim made quietly, and once the grey
  // pre-match pair renders beside the names it can also contradict them
  // outright: an opening line and a last live blend disagree about the
  // favourite often enough that the card would bold one side while the number
  // beside it named the other.
  //
  // #6238 — `!favoriteKnown` joins that list for the same reason: on a
  // draw-priced sport the card no longer holds a second number to be ahead of.
  const homeNameClass = isFinished
    ? finishedNameClass(homeWon)
    : isSuspended || noReading || !favoriteKnown || homeFavorite
      ? "text-text-primary"
      : "text-text-secondary";
  const awayNameClass = isFinished
    ? finishedNameClass(awayWon)
    : isSuspended || noReading || !favoriteKnown || !homeFavorite
      ? "text-text-primary"
      : "text-text-secondary";

  // Format time and date compactly
  const gameTime = new Date(event.commence_time);
  // UX-P074: an unparseable/absent commence_time renders NO time chip. The
  // league rail now feeds this card and types that field nullable, and
  // `toLocaleTimeString` on an invalid Date prints the literal string
  // "Invalid Date" — a card is allowed to say nothing, never to say that.
  const hasGameTime = !Number.isNaN(gameTime.getTime());
  const now = new Date();
  const isToday = gameTime.toDateString() === now.toDateString();
  const tomorrow = new Date(now);
  tomorrow.setDate(tomorrow.getDate() + 1);
  const isTomorrow = gameTime.toDateString() === tomorrow.toDateString();
  
  const timeStr = gameTime.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
  });
  
  // For upcoming: show "Today 7:00 PM" or "Mar 8 7:00 PM"
  const dateTimeStr = isToday
    ? `Today ${timeStr}`
    : isTomorrow
      ? `Tomorrow ${timeStr}`
      : `${gameTime.toLocaleDateString("en-US", { month: "short", day: "numeric" })} ${timeStr}`;
  
  // For finished: show just the date. The impossible-state guard (L2-112 Item 2 /
  // gotcha #14 — a FINAL game can't be in the future when commence_time actually
  // holds a Kalshi close/resolution timestamp) now lives in one place for all
  // three surfaces. UX-P045: the "compact" style preserves this card's existing
  // month/day output exactly, so adopting the shared module is not a restyle.
  const finishedDateStr = formatFinishedGameLabel(
    event.commence_time,
    now.getTime(),
    "compact",
  );

  // International sport detection — show flags instead of team logos
  const showFlags = isInternationalSport(event.sport);
  const homeFlagUrl = showFlags ? flagUrl(event.home_team) : null;
  const awayFlagUrl = showFlags ? flagUrl(event.away_team) : null;

  // #3784 — the served face/flag, for individual sports. See `ParticipantCrest`
  // for the precedence and why it is stated once. `?? null` rather than a bare
  // read: the key is ABSENT on a team-sport payload, and `undefined` reaching a
  // `string | null` prop is a different type error than the missing photo it
  // would be mistaken for.
  const homeCrestUrl =
    event.home_team_data?.logo_small || espnTeamLogoByName(event.home_team, event.sport) || null;
  const awayCrestUrl =
    event.away_team_data?.logo_small || espnTeamLogoByName(event.away_team, event.sport) || null;

  // Short team names for compact display. UX-1065 (#2936): the last word alone
  // renders "Town" for Ipswich Town and "FC" for both sides of an FC-vs-FC
  // fixture, so the pair is decided together in `lib/teamShortName.ts`.
  const { home: homeShort, away: awayShort } = teamShortNames(
    { name: event.home_team, abbreviation: event.home_team_data?.abbreviation },
    { name: event.away_team, abbreviation: event.away_team_data?.abbreviation },
  );

  return (
    // UX-P083 (#1860) / UX-P154: the stable hook the browser rail counts and the
    // link-and-card treatment both live in `EventCardShell` now. Ruling 047's
    // acceptance is "the league page renders the SHARED event card", and that is
    // a claim about WHICH COMPONENT rendered — unanswerable from the DOM unless
    // the shared card marks itself. It moved one level down so the tournament
    // match list can make the same claim without copying a wrapper, which is
    // exactly the "reinventing the event card" Alex named.
    <EventCardShell
      href={`/events/${event.id}`}
      onClick={handleCardClick}
      live={isLive}
      finished={isFinished}
      ariaLabel={`${event.away_team} at ${event.home_team}${gameNumber !== null ? ` - Game ${gameNumber}` : ""}${isLive ? " - Live" : isFinished ? " - Final" : ""}`}
      style={teamColorStyle(
        event.home_team_data?.primary_color,
        event.away_team_data?.primary_color,
        event.home_team_data?.secondary_color,
        event.away_team_data?.secondary_color,
      )}
    >
      <>
          {/* Top bar: league + status + pin */}
          <div className="flex items-center justify-between gap-2 mb-2.5">
            <div className="flex items-center gap-1.5 min-w-0">
              {showSport && event.sport && (
                <span className="text-micro-xs text-text-muted uppercase tracking-widest truncate">
                  {getSportLabel(event.sport, event.sport_name)}
                </span>
              )}
              {/* #7529 — WHO IS HOSTING, on the rows where that is the only
                  thing telling two cards apart. A split-squad home-and-home
                  puts the same two clubs on the search page twice at the same
                  minute, and row order is the card's only home/away signal —
                  which reads as "the same game, shown twice".

                  It is `flex-shrink-0` and nowrap while the sport label beside
                  it truncates, because a cue clipped to "at T" is the one
                  element here that has to survive 390px intact: it is the whole
                  distinction. Same muted micro type as the sport label — this
                  is a mark, not a caption (notice 34 / D102).

                  Not announced separately, and that is correct: the shell's
                  aria-label is already "{away} at {home}", so a reader who
                  cannot see the layout has never had this ambiguity. */}
              {hostCue && (
                <span
                  className="text-micro-xs text-text-muted whitespace-nowrap flex-shrink-0"
                  data-testid="event-card-host-cue"
                  data-host={hostCue.name}
                >
                  at {hostCue.label}
                </span>
              )}
              {/* #8515 — WHICH GAME OF A DOUBLEHEADER. Two cards with the same
                  clubs on the same day, told apart only by a start time, read
                  as one game shown twice (Cubs@Red Sox, 9/25). Printed ONLY when
                  the provider itself says doubleheader + game N — never from a
                  same-teams-same-day pair, which is also exactly what a
                  duplicate row looks like (#2866). Same mark type and the same
                  survive-390px rule as the host cue beside it. Unlike the host
                  cue this one IS announced (aria-label), because the shell's
                  label is identical on both halves of a doubleheader. */}
              {gameNumber !== null && (
                <span
                  className="text-micro-xs text-text-muted whitespace-nowrap flex-shrink-0"
                  data-testid="event-card-game-number"
                  data-game-number={gameNumber}
                >
                  Game {gameNumber}
                </span>
              )}
              {highlightLabel && !isLive && (
                <span className="text-micro-xs bg-accent-warning/15 text-accent-warning px-1.5 py-0.5 rounded">
                  {highlightLabel}
                </span>
              )}
              <PersonalizedBadge
                personalized={personalized}
                multiplier={multiplier}
                personalizationReasons={personalizationReasons}
              />
            </div>

            <div className="flex items-center gap-1.5 flex-shrink-0">
              {isLive && (
                <span className="flex items-center gap-1 bg-accent-live/15 text-accent-live px-2 py-0.5 rounded text-micro-xs font-semibold">
                  <span className="w-1.5 h-1.5 rounded-full bg-accent-live animate-pulse" />
                  {/* Show period/clock if available, otherwise LIVE.
                      UX-P051 (#1710): "available" now means ESPN is reporting an
                      in-game state, not merely that the fields are non-empty —
                      this site printed the whole pre-game sentence followed by
                      "0.0". Composition and fallback are unchanged. */}
                  {formatLiveClockLabel(event.espn?.period, event.espn?.game_clock) || highlightLabel || "LIVE"}
                </span>
              )}
              {/* live/048: a suspended match must not advertise a start time.
                  Its commence_time is in the PAST and the clock has run out —
                  printing "Today 7:00 PM" beside it is the upcoming-branch
                  fall-through this state exists to avoid. */}
              {/* CERT-786 — one shared summary, not the bare badge this
                  originally carried. Four surfaces render this state and they
                  now render one string, so "the card says the same thing
                  wherever you meet it" is a property of the function rather
                  than of four editors remembering. Not uppercased: the settled
                  sibling below uppercases the single word "Final", and shouting
                  a whole sentence is a different register. */}
              {/* #2786 — HOME-AWAY, because that is what this component does
                  everywhere else: the FINAL block below prints home then away,
                  both live score slots put home above away, and the `Proj`
                  footer is home-away. The away-home default made this the only
                  numeric pair on the card reading the other way, and it shipped
                  an inverted score on production (event 15293347: "last score
                  6-3" for a 3-6 match, directly under the HOME team's name). */}
              {/* #6361 — AND ITS DATE, AFTER THE WORDS AND ATTACHED TO THEM.
                  live/262 photographed six of these stacked on one search page
                  with no date, between an "Aug 18 FINAL" and an "Aug 23 FINAL"
                  that both had one; two of the six were the same fixture pair,
                  so a reader could not tell them apart at all.

                  ORDER IS THE WHOLE CARE HERE, and it is what reconciles this
                  with #3211. That issue removed a BARE commence stamp from this
                  slot — "a date three days gone, in the position a reader reads
                  as 'when this begins'". Its objection is positional, so the
                  date returns only as the tail of the past-tense sentence
                  ("No result reported · Sep 13"), never as a standalone token
                  that could be read as a kickoff. The comment above still
                  refuses `dateTimeStr`, which is the UPCOMING branch's
                  future-tense start time and a different string entirely.

                  `finishedDateStr` is the already-computed, date-only label the
                  settled sibling below prints, so this carries the same gotcha
                  #14 guard: a row whose `commence_time` is really a Kalshi close
                  stamp renders "" — no date — rather than a future one. */}
              {/* #7070 — the venue's grade outranks our silence here exactly as
                  it does in the hero one tap away (`page.tsx`, #6381): the card
                  a reader taps and the page they land on now say the same
                  sentence about the same match. The date stays and stays LAST
                  for #6361's reason — it is what tells two meetings of the same
                  pair apart — and it is as true of a graded row as of a denied
                  one. `venueSettledSummary` is null on every other row, so the
                  fall-through below is unchanged for them. */}
              {isSuspended && (
                <span
                  className="text-micro-xs text-text-muted"
                  data-venue-settled={venueSettledSentence ? "true" : undefined}
                >
                  {venueSettledSentence ??
                    suspendedSummary(event.away_score, event.home_score, "home-away")}
                  {finishedDateStr && <> · {finishedDateStr}</>}
                </span>
              )}
              {!isLive && !isFinished && !isSuspended && hasGameTime && (
                <span className="text-micro text-text-muted">{dateTimeStr}</span>
              )}
              {isFinished && (
                <>
                  {finishedDateStr && <span className="text-micro-xs text-text-muted">{finishedDateStr}</span>}
                  <span className="text-micro-xs text-text-muted uppercase">Final</span>
                </>
              )}
              {/* Pin button */}
              {onPinToggle && (
                <button
                  onClick={handlePinClick}
                  disabled={pinDisabled && !isPinned}
                  className={cn(
                    "p-1 rounded transition-all",
                    isPinned
                      ? 'text-accent-warning'
                      : 'text-text-muted/30 hover:text-text-muted group-hover/card:text-text-muted/50',
                    pinDisabled && !isPinned && 'cursor-not-allowed opacity-30',
                  )}
                  title={isPinned ? 'Unpin' : pinDisabled ? 'Max 6 pins' : 'Pin'}
                  aria-label={isPinned ? 'Unpin event' : 'Pin event'}
                >
                  <PinIcon filled={isPinned} className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          </div>

          {/* Finished: centered score block */}
          {isFinished && event.home_score !== null && event.away_score !== null && (
            <div className="flex items-center justify-center gap-3 py-1.5 mb-2 bg-surface-elevated/50 rounded">
              <div className="text-center">
                <div className={cn(
                  "font-mono text-lg font-bold",
                  event.home_score! > event.away_score! ? "text-text-primary" : "text-text-muted",
                )}>
                  {event.home_score}
                </div>
                <div className="text-[9px] text-text-muted uppercase">{homeShort}</div>
              </div>
              <span className="text-text-muted text-xs">—</span>
              <div className="text-center">
                <div className={cn(
                  "font-mono text-lg font-bold",
                  event.away_score! > event.home_score! ? "text-text-primary" : "text-text-muted",
                )}>
                  {event.away_score}
                </div>
                <div className="text-[9px] text-text-muted uppercase">{awayShort}</div>
              </div>
            </div>
          )}

          {/* Teams + Probabilities */}
          <div className="space-y-1.5 flex-grow">
            {/* Home team */}
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 flex-1 min-w-0">
                <ParticipantCrest
                  name={event.home_team}
                  servedFace={event.home_image_url ?? null}
                  servedFlag={event.home_flag_url ?? null}
                  countryFlagUrl={homeFlagUrl}
                  crestUrl={homeCrestUrl}
                  colorVar="--team-home-primary"
                />
                <TeamNameLink
                  name={event.home_team}
                  sportKey={event.sport}
                  className={cn(
                    "text-sm font-medium truncate hover:underline",
                    homeNameClass,
                  )}
                />
                {/* #2764 — the prior, beside the name it is about. Grey on BOTH
                    rows, winner included: bold on this card means "this is what
                    happened", and the pre-match number is the opposite of that.
                    The `sr-only` prefix names the team because the layout is the
                    only thing pairing a bare percent to a side, and a reader who
                    cannot see the layout has nothing. */}
                {prematch && prematch.homePercent !== null && (
                  <span
                    className="flex-shrink-0 font-mono text-[11px] tabular-nums text-text-muted"
                    data-testid="event-card-prematch-home"
                    data-prematch={prematch.homeProbability}
                    data-prematch-source={prematch.source}
                  >
                    <span className="sr-only">
                      {PREMATCH_SAID} {event.home_team}{" "}
                    </span>
                    {prematch.homePercent}%
                  </span>
                )}
                {/* Inline live score */}
                {isLive && event.home_score !== null && (
                  <span className="font-mono text-sm font-bold text-accent-live ml-auto" aria-label={`${event.home_team} score: ${event.home_score}`}>{event.home_score}</span>
                )}
              </div>
              {/* Probability chip — scheduled/live only; a FINAL card drops the
                  live-style chip for the settled score block above (L2-112 Item 2),
                  and so does a SUSPENDED one (live/048, CERT-792). `suspended` is
                  neither live nor finished, so it fell through to the pregame chip
                  and printed a confident 72%/28% two lines under "No result
                  reported" — the card contradicting itself in one glance. The
                  suspended summary above is the whole statement. */}
              {!isLive && !isFinished && !isSuspended && !noReading && (
                <AnimatedProbability
                  percent={chipHomePct}
                  className={cn(
                    "font-mono tabular-nums",
                    // #6238 — when the away side is withheld this is the only
                    // number on the card, so it takes the full treatment. The
                    // small/secondary size means "the other one is bigger", and
                    // there is no other one.
                    !favoriteKnown || homeFavorite
                      ? "text-prob-md text-text-primary"
                      : "text-prob-sm text-text-secondary",
                  )}
                />
              )}
              {isLive && !noReading && (
                <AnimatedProbability
                  percent={chipHomePct}
                  className="font-mono tabular-nums text-xs text-text-muted"
                />
              )}
            </div>

            {/* Team-colored probability bar — hidden on FINAL (settled score
                above) and on SUSPENDED (CERT-792): a filled bar is the loudest
                claim on the card, and there is no live price behind it. */}
            {!isFinished && !isSuspended && !noReading && (
              <ProbabilityBar
                homeProbability={homeProb}
                homeFavorite={homeFavorite}
                // #6238 — the bar derives its away half as the remainder, which
                // is the same complement the chips above stopped printing. Left
                // whole it would keep saying it in pixels.
                awayWithheld={awayWithheld}
                homeColor={event.home_team_data?.primary_color ?? undefined}
                awayColor={event.away_team_data?.primary_color ?? undefined}
                height={isLive ? 3 : 5}
              />
            )}

            {/* #2882 — the bar's slot, in words. It sits BETWEEN the two names,
                where the bar was and where the hero puts the same sentence, so
                the statement lands on the matchup rather than on one side of
                it. A settled or unreported card is deliberately excluded: those
                two already carry their own whole statement (the score block and
                "no result reported"), and adding this under either would be the
                card saying two things about one absence. */}
            {!isFinished && !isSuspended && noReading && (
              <p
                className="text-xs text-text-muted py-0.5"
                data-testid="event-card-no-probability"
              >
                No price yet
              </p>
            )}

            {/* Away team */}
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 flex-1 min-w-0">
                <ParticipantCrest
                  name={event.away_team}
                  servedFace={event.away_image_url ?? null}
                  servedFlag={event.away_flag_url ?? null}
                  countryFlagUrl={awayFlagUrl}
                  crestUrl={awayCrestUrl}
                  colorVar="--team-away-primary"
                />
                <TeamNameLink
                  name={event.away_team}
                  sportKey={event.sport}
                  className={cn(
                    "text-sm font-medium truncate hover:underline",
                    awayNameClass,
                  )}
                />
                {/* #2764 — the away side's prior (see the home row above).
                    #6238 — withheld on a draw-priced sport: it is the opening
                    complement, and this row names itself, so it costs the home
                    prior nothing to leave the slot empty. */}
                {prematch &&
                  prematch.awayPercent !== null &&
                  !awayIsTheComplement(
                    prematch.awayProbability,
                    prematch.homeProbability,
                    event.sport,
                  ) && (
                  <span
                    className="flex-shrink-0 font-mono text-[11px] tabular-nums text-text-muted"
                    data-testid="event-card-prematch-away"
                    data-prematch={prematch.awayProbability}
                    data-prematch-source={prematch.source}
                  >
                    <span className="sr-only">
                      {PREMATCH_SAID} {event.away_team}{" "}
                    </span>
                    {prematch.awayPercent}%
                  </span>
                )}
                {/* Inline live score */}
                {isLive && event.away_score !== null && (
                  <span className="font-mono text-sm font-bold text-accent-live ml-auto" aria-label={`${event.away_team} score: ${event.away_score}`}>{event.away_score}</span>
                )}
              </div>
              {/* Probability chip — scheduled/live only (see home team above).

                  #6238 — and not at all on a draw-priced sport. This row names
                  itself (crest · team · number), so the withheld side simply
                  renders nothing and the surviving home number keeps its own
                  row and its own name: native's rule for a self-naming row
                  (`EventCardView.probabilityWithMovement`). Only the surfaces
                  that collapse a POSITIONAL pair have to name a survivor. */}
              {!isLive && !isFinished && !isSuspended && !noReading && !awayWithheld && (
                <AnimatedProbability
                  percent={chipAwayPct}
                  className={cn(
                    "font-mono tabular-nums",
                    !homeFavorite ? "text-prob-md text-text-primary" : "text-prob-sm text-text-secondary",
                  )}
                />
              )}
              {isLive && !noReading && !awayWithheld && (
                <AnimatedProbability
                  percent={chipAwayPct}
                  className="font-mono tabular-nums text-xs text-text-muted"
                />
              )}
            </div>
          </div>

          {/* #2764 — ONE label for the pair, never one per row: both grey
              numbers always come off the same rung, so saying it twice on one
              card is noise. Alex's rule is "labelled when not a prediction
              market", and `prematchReading` returns `label: null` for a
              prediction-market rung, so this renders only for the books
              reading — which, on this surface, is every reading (`Event`
              carries no `prematch_odds`). It sits outside the footer above
              deliberately: that footer is gated `!isFinished`, and un-gating it
              to host this would also bring back `Proj 6-4` and `Opened X/Y` on
              a settled card. */}
          {prematch?.label && (
            <div className="mt-2 pt-2 border-t border-surface-border/50 text-micro">
              <span
                className="text-[11px] text-text-muted"
                data-testid="event-card-prematch-label"
                data-prematch-source={prematch.source}
              >
                Pre-match · {prematch.label}
              </span>
            </div>
          )}

          {/* Footer — contextual info (hide for finished games, and for
              suspended ones: "Proj 6-4" is a pregame promise and the match is
              stopped, not upcoming — CERT-792). */}
          {!isFinished && !isSuspended && (
            <div className="mt-2.5 pt-2 border-t border-surface-border/50 flex justify-between items-center text-micro">
              {/* UX-P074: `!= null`, not `!== null`. An ABSENT key answered the
                  strict test with `undefined !== null` → true, and the card then
                  printed "Proj NaN-NaN". Found the moment the league rail — a
                  producer that carries a blend and no projection — started
                  feeding this shared card. */}
              {!isLive && odds && odds.projected_home_score != null && odds.projected_away_score != null ? (
                <span className="text-text-muted">
                  Proj <span className="font-mono text-text-secondary">{Math.round(odds.projected_home_score)}-{Math.round(odds.projected_away_score)}</span>
                </span>
              ) : isLive && opening && openedHomePct !== null && openedAwayWithheld ? (
                /* #6238 — the opening pair is the same complement at an earlier
                   instant, so the away half goes with the current one. The
                   footer is KEPT, not dropped: the home opening figure is as
                   legitimate as the home current one, and it is the only
                   pre-match context a live card carries. Losing the pair loses
                   the positional attribution that let both numbers go unnamed,
                   so it names its survivor, in native's words
                   (`EventCardView.footerRow`). Short name via the PAIR helper,
                   never per side — #3430. */
                <span className="text-text-muted">
                  Opened{" "}
                  <span className="font-mono text-text-secondary">
                    {teamShortNames({ name: event.home_team }, { name: event.away_team }).home} {openedHomePct}%
                  </span>
                </span>
              ) : isLive && opening && openedHomePct !== null && openedAwayPct !== null ? (
                <span className="text-text-muted">
                  Opened <span className="font-mono text-text-secondary">{openedHomePct}/{openedAwayPct}</span>
                </span>
              ) : null}
              {event.espn?.broadcast && (
                <span className="text-text-muted truncate ml-auto">
                  {event.espn.broadcast.split(",")[0].trim()}
                </span>
              )}
            </div>
          )}
      </>
    </EventCardShell>
  );
}

/* #7165 — the local `PinIcon` is gone; this card imports the shared one. Its
   unpinned state drew a goblet, not a hollow pushpin, and three byte-identical
   copies of it is why one wrong icon shipped on four surfaces. */
