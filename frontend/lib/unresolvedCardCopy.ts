/**
 * THE PICTURE A DEAD LINK UNFURLS WITH (#5846).
 *
 * ═══ WHAT WAS ON PRODUCTION BEFORE THIS ═══
 *
 * #5840 gave `/events/[id]` and `/futures/[id]` honest WORDS for a link that no
 * longer resolves — "This game isn't on Bain Luck", self-canonical, `noindex`.
 * Their `opengraph-image.tsx` routes never learned the same thing. Both take
 * `event`/`market` as nullable and coalesce every field, so a dead id renders
 * the LIVE layout with the facts replaced by defaults. Read on production
 * 2026-09-13 11:49:13Z:
 *
 *   /events/99999999/opengraph-image   200 image/png, md5 12e3f23f4984…
 *   /futures/99999999/opengraph-image  200 image/png, md5 6a4c72c052a8…
 *
 * `/futures` drew "Prediction market", a `- -` glyph where the probability goes
 * and "0 outcomes tracked" — authoritative-looking, saying nothing.
 *
 * ⚠️ `/events` was worse than "empty", and it is why this is a card and not a
 * caption. `homeProbability = event?.current_odds?.home_probability ?? 0.5`
 * with the same fallback on the away side made the miss branch INVENT a game:
 * two coloured crests reading `AWA` and `HOM`, the names "Away" and "Home", and
 * **50% against 50%** in the largest type on the image, over a half-and-half
 * bar. A reader pasting a rotted link saw a real-looking even-money matchup.
 * That is a fabricated fact on the most public screen we have, not a blank.
 *
 * ═══ WHY THE DECISION IS HERE AND NOT IN THE TWO ROUTES ═══
 *
 * `hubCardCopy` is the precedent and the reason: when `/hub/[competition]` left
 * the accent in the route rather than in the pure function, `accentFor(null)` —
 * all five hubs one colour, the exact defect that ship removed — survived the
 * whole suite, because no test could reach a decision the route still owned.
 * So the route is a spread and every field is decided here, where a test can
 * read it without a build, a browser or a network.
 *
 * Both dead branches also have to say the SAME thing the title says, and the
 * title is `unresolvedShareCopy`'s. Deriving the card's headline from that same
 * call is what stops the picture claiming a link is dead while the sentence
 * beside it says "Game Odds".
 *
 * ═══ NAMED RESIDUE ═══
 *
 * `/tournaments/[slug]` still inlines its own two dead strings and
 * `/hub/[competition]` keeps them inside `hubCardCopy`. Both are live, correct
 * and certed; folding them in here is a change with no reader on the other end.
 * The table below is written to hold all five subjects so that fold is a
 * deletion when somebody has a reason to do it.
 */

import { accentFor, type UnfurlCardProps } from "@/components/og/UnfurlCard";
import {
  unresolvedShareCopy,
  type ResolutionFailure,
  type UnresolvedSubject,
} from "@/lib/unresolvedShareMeta";

/**
 * The pill in the top right, per subject.
 *
 * The reader's word for the thing, matching `SUBJECT_NOUN` in
 * `unresolvedShareMeta.ts` — a dead `/hub/tennis` says "Competition", not
 * "Hub". Capitalised because every other card's eyebrow is ("Tournament",
 * "UFC", "Election").
 */
const SUBJECT_EYEBROW: Record<UnresolvedSubject, string> = {
  game: "Game",
  market: "Market",
  tournament: "Tournament",
  event: "Event",
  hub: "Competition",
  team: "Team",
};

/**
 * The second line, when the link names nothing.
 *
 * Not the title's own description: that one is written to be read in a preview
 * ALONGSIDE the headline, so it repeats the noun ("There's no game at this
 * link…"). Under the headline on the card that reads as a stutter. These say
 * the one useful thing instead — why a link a person actually had might have
 * stopped working.
 *
 * Plain English, no diagnostics, no status code, no invitation to retry
 * (notice 34).
 */
const NOT_FOUND_SUBTITLE: Record<UnresolvedSubject, string> = {
  game: "The link may be old, or the game may never have been on the schedule.",
  market: "The link may be old, or the market may have closed and been retired.",
  tournament: "The link may be old, or the hub may not have opened yet.",
  event: "The link may be old, or this may not be an event we cover.",
  hub: "The link may be old, or this may not be a competition we cover.",
  team: "The link may be old, or this may not be a team we cover.",
};

/**
 * Everything `UnfurlCard` needs to draw a link that did not resolve.
 *
 * `rows` is empty and `note` is absent by construction — there is no fact to
 * print, and `UnfurlCard`'s empty-`rows` shape (`SUBTITLE_MAX_QUIET`, no bar,
 * no footer note) is drawn for exactly this case.
 *
 * The accent is the default rather than a category colour: the segment on both
 * routes is a bare numeric id, so unlike `/hub/<competition>` there is no
 * signal to take one from. Guessing one would put a sport's colour on a card
 * that does not know the sport.
 */
export function unresolvedCardCopy(
  subject: UnresolvedSubject,
  failure: ResolutionFailure
): UnfurlCardProps {
  const { title, description } = unresolvedShareCopy(subject, failure);

  return {
    eyebrow: SUBJECT_EYEBROW[subject],
    title,
    // `"unavailable"` claims nothing about whether the thing exists (gotcha
    // #53), so it keeps the neutral blurb the title already carries. Only
    // `"not-found"` gets a sentence about a link that is gone.
    subtitle: failure === "not-found" ? NOT_FOUND_SUBTITLE[subject] : description,
    rows: [],
    accent: accentFor(null),
  };
}
