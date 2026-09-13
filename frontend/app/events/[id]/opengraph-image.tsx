import { ImageResponse } from "next/og";
import type { EventDetailResponse } from "@/lib/types";
import { UnfurlCard } from "@/components/og/UnfurlCard";
import { servedDuelPercents } from "@/lib/servedDuelPercents";
import { getSportLabel } from "@/lib/sportCategories";
import { teamCrestBadge } from "@/lib/teamShortName";
import { teamTextColor } from "@/lib/teamColors";
import { unresolvedCardCopy } from "@/lib/unresolvedCardCopy";
import type { ResolutionFailure } from "@/lib/unresolvedShareMeta";

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

function eventStatus(event: EventDetailResponse): string {
  if (event.status === "live") return "Live now";
  if (event.status === "completed" || event.status === "closed") return "Final";
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
  if (!lookup.ok) {
    return new ImageResponse(<UnfurlCard {...unresolvedCardCopy("game", lookup.failure)} />, size);
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
  // The bar under the two numbers is the SAME pair drawn as a width, so it
  // reads off the same rounding instead of being a third one that can disagree
  // with the percentages printed directly above it.
  const awayWidth = Math.max(
    3,
    Math.min(97, awayRendered ?? Math.round(awayProbability * 100)),
  );
  const homeColor = event.home_team_data?.primary_color || "#2563eb";
  const awayColor = event.away_team_data?.primary_color || "#dc2626";
  // #5696 — the crest tiles and the split bar keep the raw brand colour as a
  // FILL; the two big percents are TEXT and take #5165's floor. This canvas is
  // `#f8fafc` rather than `--surface-card`'s `#FFFFFF`, so the helper's ratio
  // is off by under 2% here — nowhere near enough to move a 3:1 standard, and
  // a white club reads 1.02:1 against slate-50 just as invisibly.
  const homeTextColor = teamTextColor(homeColor) || "#2563eb";
  const awayTextColor = teamTextColor(awayColor) || "#dc2626";
  const awayTeam = event.away_team || "Away";
  const homeTeam = event.home_team || "Home";
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
            <div style={{ fontSize: 44, fontWeight: 850, lineHeight: 1.05 }}>{awayTeam}</div>
            <div style={{ fontSize: 74, fontWeight: 950, color: awayTextColor }}>{awayPct}</div>
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
            <div style={{ fontSize: 44, fontWeight: 850, lineHeight: 1.05, textAlign: "right" }}>{homeTeam}</div>
            <div style={{ fontSize: 74, fontWeight: 950, color: homeTextColor }}>{homePct}</div>
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
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
          <div style={{ display: "flex", justifyContent: "space-between", color: "#64748b", fontSize: 23 }}>
            {/* The "Probability-first odds" arm this used to carry was the
                missing-event fallback, and it is unreachable now that the miss
                returns above — a card that reaches here has a status. */}
            <div>{eventStatus(event)}</div>
            {/* #4957: the bare wordmark, matching the other three share cards. This card is
                for ONE event, so naming /discover advertised a page other than the picture. */}
            <div>bainluck.com</div>
          </div>
        </div>
      </div>
    ),
    size
  );
}
