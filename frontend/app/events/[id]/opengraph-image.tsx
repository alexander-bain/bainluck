import { ImageResponse } from "next/og";
import type { EventDetailResponse } from "@/lib/types";
import { UnfurlCard } from "@/components/og/UnfurlCard";
import { servedDuelPercents } from "@/lib/servedDuelPercents";
import { getSportLabel } from "@/lib/sportCategories";
import { teamCrestBadge } from "@/lib/teamShortName";
import { teamTextColor } from "@/lib/teamColors";
import { unresolvedCardCopy } from "@/lib/unresolvedCardCopy";
import type { ResolutionFailure } from "@/lib/unresolvedShareMeta";
import { unfurlImageOptions } from "@/lib/unfurlImageCache";
import { isFinishedForShare } from "@/lib/eventShareMeta";
import { resolveEventOutcome } from "@/lib/eventOutcome";
import { prematchReading } from "@/lib/prematchReading";

export const runtime = "edge";
export const alt = "Bain Luck game probability";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "https://api.bainluck.com").replace(/\/$/, "");

/** The game, or WHY there is no game — #5846 needs the two apart. */
type EventLookup =
  | { ok: true; event: EventDetailResponse }
  | { ok: false; failure: ResolutionFailure };

/**
 * #5846: the 404-vs-anything-else split is `layout.tsx`'s, kept here because
 * the CARD now makes the same claim the title does.
 *
 * "This game isn't on Bain Luck" is a statement about the world. Drawing it
 * because the API was restarting is the failure `unresolvedShareMeta.ts`
 * documents at length (gotcha #53) — and a picture is harder to take back than
 * a sentence, because the unfurler caches it.
 */
async function fetchEvent(id: string): Promise<EventLookup> {
  const eventId = Number.parseInt(id, 10);
  if (!Number.isFinite(eventId) || eventId <= 0) {
    return { ok: false, failure: "not-found" };
  }

  try {
    const response = await fetch(`${API_URL}/api/events/${eventId}`, {
      next: { revalidate: 60 },
    });
    if (response.status === 404) return { ok: false, failure: "not-found" };
    if (!response.ok) return { ok: false, failure: "unavailable" };
    return { ok: true, event: await response.json() };
  } catch {
    return { ok: false, failure: "unavailable" };
  }
}

/**
 * #6049 — the one predicate behind both the word this card prints and how long
 * the card may be cached, so "Final" and a settled cache window can never be
 * decided from two different readings of `status`.
 *
 * #6085 — and now behind the third thing too: whether the card may print a
 * forecast at all. It delegates to `eventShareMeta`'s `isFinishedForShare`
 * rather than keeping its own `===` pair, because that is the SAME question the
 * title beside this picture already asks, and the whole defect was the two
 * halves of one preview answering it apart. The set is unchanged
 * (`completed` | `closed`); the owner is now shared, and the delegate also
 * trims and lower-cases, so this predicate can only get harder to fool.
 */
function isFinal(event: EventDetailResponse): boolean {
  return isFinishedForShare(event);
}

function eventStatus(event: EventDetailResponse): string {
  if (event.status === "live") return "Live now";
  if (isFinal(event)) return "Final";
  return "Upcoming";
}

export default async function Image({ params }: { params: { id: string } }) {
  const lookup = await fetchEvent(params.id);

  // #5846 — A DEAD LINK DOES NOT GET A GAME DRAWN FOR IT.
  //
  // This branch used to fall through to the layout below with every field
  // coalesced, so `/events/99999999/opengraph-image` answered `200 image/png`
  // with two crests reading `AWA` and `HOM`, the names "Away" and "Home", and
  // 50% against 50% in 74px type — a fabricated matchup, not a blank one.
  //
  // The `?? 0.5` pair below is what produced those numbers and is deliberately
  // left alone: on a game that DID resolve it is the live card's existing,
  // certed behaviour for a row with no price, and it is now unreachable from a
  // missing event. Narrowing `lookup` here is what makes that true — the fields
  // below are no longer optional, so a future edit cannot quietly re-open the
  // path by adding one more `?.`.
  //
  // The quiet card is `UnfurlCard`'s empty-`rows` shape — the same picture
  // `/tournaments/[slug]`, `/event/[domain]/[slug]` and `/hub/[competition]`
  // already draw for this condition, so the five routes answer a rotted link
  // as one family.
  // #6049 — "moving" because this card is a claim we may need to retract, not
  // because it carries a number; see the block above on `unavailable`.
  if (!lookup.ok) {
    return new ImageResponse(
      <UnfurlCard {...unresolvedCardCopy("game", lookup.failure)} />,
      unfurlImageOptions(size, "moving"),
    );
  }

  const event = lookup.event;
  const homeProbability = event.current_odds?.home_probability ?? 0.5;
  const awayProbability = event.current_odds?.away_probability ?? 0.5;
  // #4963 — THE TWO NUMBERS ON THIS CARD ARE ONE DECISION, AND THE SERVER
  // ALREADY MAKES IT. UX-P114 moved the duel's whole percents to
  // `current_odds.{away,home}_rendered_percent` precisely because a game strip
  // is drawn by four surfaces; this card is the surface that never adopted it,
  // and went on formatting each side on its own. The feed derives away as
  // `1 - home`, so whenever the blend lands on an exact half-percent both sides
  // round up and the pair prints 101.
  //
  // Measured on production 2026-09-10, Pirates @ Cubs (event 15304803): the API
  // served `home_rendered_percent: 53` / `away_rendered_percent: 47`, and this
  // card drew `48%` beside `53%` — in the largest type on the image, on a card
  // whose entire job is "this side, or that side".
  //
  // `servedDuelPercents` and not a local rounding rule: a third copy of this
  // decision is how the second one drifted. It also takes the served pair WHOLE
  // or not at all (#2279) — a payload carrying one field and not the other is
  // the same 101 arriving from the other direction.
  const [awayRendered, homeRendered] = servedDuelPercents(
    awayProbability,
    homeProbability,
    event.current_odds?.away_rendered_percent,
    event.current_odds?.home_rendered_percent,
  );
  const awayPct = awayRendered != null ? `${awayRendered}%` : "--";
  const homePct = homeRendered != null ? `${homeRendered}%` : "--";

  const awayTeam = event.away_team || "Away";
  const homeTeam = event.home_team || "Home";
  const final = isFinal(event);

  // ═══ #6085 — A FINISHED GAME DOES NOT GET A FORECAST DRAWN ON IT ═══
  //
  // Measured on production 2026-09-14, `/events/15310688` (US Open semi-final):
  // this card drew `3%` and `97%` in 74px type with no score on it, while the
  // `og:title` and `og:description` rendered from the SAME payload, by
  // `layout.tsx`, two files away, read "Alexander Zverev won 3-1" and "Final:
  // Alexander Zverev beat Ben Shelton 3-1." One preview, two claims.
  //
  // 97% is not the pre-match number a settled card is allowed to print. It is
  // `current_odds`, captured at 21:51:16Z against a `completed_at` of
  // 21:53:36Z — the last in-game blend, two minutes and twenty seconds before
  // the final whistle, frozen. The honest pre-match reading (58/42) and the
  // score (3-1) were both in the same payload, unread.
  //
  // THIS IS THE DEFECT THE TEXT HALF OF THIS ROUTE ALREADY CLOSED. Q441/#1495
  // wrote `lib/eventShareMeta.ts` because the metadata "printed the last
  // captured win probability next to the word 'Final.', so a game that turned
  // late published the losing team as the favorite". That repair reached the
  // title and the description and stopped at the picture, so the picture went
  // on printing the forecast beside its own "Final" label for another fortnight.
  //
  // Nothing here is a new rule. Three modules already own these three
  // decisions and this card is simply the surface that never asked them — the
  // same shape as the `servedDuelPercents` note 40 lines up, which is the last
  // time this card was found deciding on its own something four surfaces share.
  const scoresAreTrusted = event.hero_probability_source === "settled";
  // Fed STRICTLY, copied from `layout.tsx`'s call and for its reason: handing
  // the ladder `event.home_score` unconditionally re-admits `closed`'s frozen
  // mid-game scores, measured there to INVERT the winner in 2 of 8 sampled
  // rows. `closed` is trusted to withhold a claim, never to make one.
  //
  // Rung 2 (the tournament container) is deliberately NOT asked here, and the
  // omission is safe in the one direction that matters: this card can end up
  // QUIETER than the title beside it, never in contradiction with it. Asking it
  // means a second network call on the edge image path — `layout.tsx` can
  // afford that for a string; a picture that crawlers time out on is a blank
  // preview. A finished row with no trusted score gets the withholding
  // treatment below, which is correct on its own terms.
  const outcome = resolveEventOutcome({
    isFinished: final,
    homeTeam,
    awayTeam,
    homeScore: scoresAreTrusted ? event.home_score ?? null : null,
    awayScore: scoresAreTrusted ? event.away_score ?? null : null,
    linescore: event.linescore,
  });
  const showScore =
    scoresAreTrusted &&
    typeof event.home_score === "number" &&
    typeof event.away_score === "number";

  // The number a settled card IS allowed to print, from the module that owns
  // which number that is for the other three surfaces. The detail payload
  // carries no `prematch_odds` key at all, so this always lands on the
  // documented `opening_odds` fallback — which is exactly the case that helper
  // exists for, and it labels the reading as the sportsbook median it is.
  //
  // `null` is a real answer here and licenses the empty space: a finished card
  // with no pre-match reading prints nothing rather than a number about a
  // different question.
  const prematch = final ? prematchReading({ opening_odds: event.opening_odds }) : null;

  // THE BIG SLOT. On a live or scheduled game it is the probability, unchanged.
  // On a finished one it is the SCORE — "the score + bold winner tell the
  // story" is the settled treatment CERT-786 named and `FeedCard` has rendered
  // since L2-112, where the live probability is DROPPED rather than shrunk.
  const awayHero = final ? (showScore ? `${event.away_score}` : null) : awayPct;
  const homeHero = final ? (showScore ? `${event.home_score}` : null) : homePct;

  // The bar under the two numbers is the SAME pair drawn as a width, so it
  // reads off the same rounding instead of being a third one that can disagree
  // with the percentages printed directly above it.
  //
  // #6085: on a finished game that pair is the pre-match one, matching
  // `FeedCard`'s `barHomeProb` ("finished events show opening odds"). A bar
  // still split 97/3 under a settled score would be the forecast surviving as
  // a shape after being removed as a number.
  const barAwayPercent = final ? prematch?.awayPercent ?? null : awayRendered;
  const showBar = !final || barAwayPercent != null;
  const awayWidth = Math.max(
    3,
    Math.min(97, barAwayPercent ?? Math.round(awayProbability * 100)),
  );

  // The settled card's emphasis: the winner reads as what happened and the
  // loser recedes, which is the half of `FeedCard`'s treatment that carries the
  // result once the probability is gone.
  //
  // Gated on `winnerSide` and not on `final`, because a finished game we cannot
  // crown must not mute BOTH names — "we do not know who won" would render as
  // "nobody won". A tie reaches here the same way: `resolveEventOutcome`
  // returns `null` on equal scores rather than crowning the home side.
  const decided = final && outcome?.winnerSide != null;
  const homeColor = event.home_team_data?.primary_color || "#2563eb";
  const awayColor = event.away_team_data?.primary_color || "#dc2626";
  // #5696 — the crest tiles and the split bar keep the raw brand colour as a
  // FILL; the two big percents are TEXT and take #5165's floor. This canvas is
  // `#f8fafc` rather than `--surface-card`'s `#FFFFFF`, so the helper's ratio
  // is off by under 2% here — nowhere near enough to move a 3:1 standard, and
  // a white club reads 1.02:1 against slate-50 just as invisibly.
  const homeTextColor = teamTextColor(homeColor) || "#2563eb";
  const awayTextColor = teamTextColor(awayColor) || "#dc2626";
  // Declared here and not beside `decided`, which is 60 lines up: these two
  // read the brand colours above, and a settled card's emphasis has to fall
  // back to the exact colour a live card would have used.
  const awayNameColor = decided ? (outcome?.winnerSide === "away" ? "#111827" : "#64748b") : "#111827";
  const homeNameColor = decided ? (outcome?.winnerSide === "home" ? "#111827" : "#64748b") : "#111827";
  const awayHeroColor = decided
    ? (outcome?.winnerSide === "away" ? "#111827" : "#94a3b8")
    : awayTextColor;
  const homeHeroColor = decided
    ? (outcome?.winnerSide === "home" ? "#111827" : "#94a3b8")
    : homeTextColor;
  // #4839. This card is the first thing anyone sees of Bain Luck — a pasted
  // link in iMessage, Slack or a tweet — and it was printing the raw sport key.
  // Precedence is unchanged (`sport_key` then `sport`) so no row that renders a
  // league today renders "Event" instead; only the WORDS change. `getSportLabel`
  // is the same call `EventCard` makes, which is what keeps the card and the
  // page it links to from naming one league two ways (notice 34 / D102).
  const sportKey = event.sport_key || event.sport || null;
  const leagueLabel = sportKey ? getSportLabel(sportKey, event.sport_name) : "Event";

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: 64,
          background: "#f8fafc",
          color: "#111827",
          fontFamily: "Inter, Arial, sans-serif",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <div style={{ fontSize: 38 }}>🍀</div>
            <div style={{ fontSize: 30, fontWeight: 800 }}>Bain Luck</div>
          </div>
          <div
            style={{
              border: "2px solid #d1d5db",
              borderRadius: 999,
              padding: "10px 18px",
              fontSize: 20,
              color: "#4b5563",
            }}
          >
            {leagueLabel}
          </div>
        </div>

        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 36 }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 18, width: 460 }}>
            <div
              style={{
                width: 126,
                height: 126,
                borderRadius: 32,
                background: awayColor,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "white",
                fontSize: 44,
                fontWeight: 900,
              }}
            >
              {teamCrestBadge(awayTeam)}
            </div>
            <div style={{ fontSize: 44, fontWeight: 850, lineHeight: 1.05, color: awayNameColor }}>{awayTeam}</div>
            {awayHero !== null && (
              <div style={{ fontSize: 74, fontWeight: 950, color: awayHeroColor }}>{awayHero}</div>
            )}
            {/* #6085 — the prior, beside the name it is about, in the grey the
                card family gives it on BOTH rows. Never rendered on a live or
                scheduled game: there the big number IS the current reading and
                a second percentage under it would be two answers to one
                question, which is the defect this block exists to close. */}
            {final && prematch?.awayPercent != null && (
              <div style={{ fontSize: 28, fontWeight: 700, color: "#64748b" }}>
                {`${prematch.awayPercent}%`}
              </div>
            )}
          </div>

          <div style={{ color: "#94a3b8", fontSize: 38, fontWeight: 800 }}>vs</div>

          <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 18, width: 460 }}>
            <div
              style={{
                width: 126,
                height: 126,
                borderRadius: 32,
                background: homeColor,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "white",
                fontSize: 44,
                fontWeight: 900,
              }}
            >
              {teamCrestBadge(homeTeam)}
            </div>
            <div style={{ fontSize: 44, fontWeight: 850, lineHeight: 1.05, textAlign: "right", color: homeNameColor }}>{homeTeam}</div>
            {homeHero !== null && (
              <div style={{ fontSize: 74, fontWeight: 950, color: homeHeroColor }}>{homeHero}</div>
            )}
            {final && prematch?.homePercent != null && (
              <div style={{ fontSize: 28, fontWeight: 700, color: "#64748b" }}>
                {`${prematch.homePercent}%`}
              </div>
            )}
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          {showBar && (
            <div
              style={{
                width: "100%",
                height: 30,
                borderRadius: 999,
                background: homeColor,
                overflow: "hidden",
                display: "flex",
              }}
            >
              <div style={{ width: `${awayWidth}%`, height: "100%", background: awayColor }} />
            </div>
          )}
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", color: "#64748b", fontSize: 23 }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {/* The "Probability-first odds" arm this used to carry was the
                  missing-event fallback, and it is unreachable now that the miss
                  returns above — a card that reaches here has a status. */}
              {/* #6085 — the result in the sport's own units, from the same
                  `resolveEventOutcome` line the title prints, so the two halves
                  of the preview cannot word one scoreline two ways. `null` on
                  every sport whose numbers are already the two big figures
                  above (a basketball card does not repeat "112-108"), so this
                  reads "Final" alone exactly as it did before. */}
              {/* One string and not two children: satori lays out adjacent text
                  nodes as separate boxes, and a reader would see the gap. */}
              <div>
                {outcome?.resultLine
                  ? `${eventStatus(event)} · ${outcome.resultLine}`
                  : eventStatus(event)}
              </div>
              {/* The rung, named once. `prematchReading` only ever sets this for
                  a non-prediction-market reading, and Alex's rule is that such a
                  number says so ("labelled when not a prediction market") — an
                  unlabelled sportsbook median is the old footnote in a new
                  shape. `sportsbooks` and never a venue name (notice 33). */}
              {final && prematch?.label && prematch.awayPercent != null && (
                <div style={{ fontSize: 20 }}>{`Pre-match · ${prematch.label}`}</div>
              )}
            </div>
            {/* #4957: the bare wordmark, matching the other three share cards. This card is
                for ONE event, so naming /discover advertised a page other than the picture. */}
            <div>bainluck.com</div>
          </div>
        </div>
      </div>
    ),
    // #6049 — a finished game's score is settled; a scheduled or live game's
    // win probability is the number that moved under a frozen picture.
    unfurlImageOptions(size, isFinal(event) ? "settled" : "moving")
  );
}
