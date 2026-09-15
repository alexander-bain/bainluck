import Link from "next/link";
import type { SportShowcaseEvent } from "@/lib/types";
import { tournamentHubHref } from "@/lib/tournamentHubs";

/**
 * A showcase event's card on `/sport/{sport}` — the Super Bowl, the Champions
 * League, Wimbledon.
 *
 * ═══ THE CARD IS A CLAIM ABOUT OUR OWN INVENTORY ═══
 *
 * Three branches, tried in this order, and the last one is a sentence:
 *
 *   1. the tournament HUB, when the competition has one (#2560);
 *   2. the MARKET, when we hold an open priced one (#6249);
 *   3. *"odds available closer to the event"*.
 *
 * Branch 3 is the right card for Wimbledon in September. It was also, until
 * #6249, the card the Super Bowl got — beside `/futures/86832` serving 32
 * priced teams, repriced that hour — because branches 1 and 2 did not exist
 * for any sport but tennis and the page had no way to ask the question.
 *
 * ⚠️ THIS COMPONENT NEVER DECIDES WHICH MARKET IS WHICH COMPETITION. It reads
 * `futures_market_id` off the served event. Matching the printed `name`
 * against market names here would attach the women's Champions League and the
 * league phase to the men's card — that exact over-admission is live one
 * surface over (#6250). The allowlist that decides it is
 * `backend/app/utils/showcase_futures.py`.
 *
 * (The golf branch — a live tournament with a field, rendered as a
 * `TournamentCard` — stays on the page: it needs the golf payload, which this
 * card has no business fetching.)
 */

/**
 * Approximate dates for events with nothing to point at.
 *
 * 🔴 A FACT WITH AN EXPIRY, COMPILED INTO A COMPONENT — the same shape
 * `tournamentHubs.ts` refuses in its own docstring, and these entries are
 * already drifting (a card reading "April 2026" in September 2026). Moved here
 * unchanged with the card it belongs to; fixing it is #1749's register, not
 * this card's branch order.
 */
const SHOWCASE_DATES: Record<string, string> = {
  "The Masters": "April 2026",
  "PGA Championship": "May 2026",
  "U.S. Open": "June 2026",
  "The Open Championship": "July 2026",
  "Chevron Championship": "April 2026",
  "KPMG Women's PGA Championship": "June 2026",
  "U.S. Women's Open": "June 2026",
  "AIG Women's Open": "August 2026",
  "The Evian Championship": "July 2026",
  "Ryder Cup": "September 2027",
  "Presidents Cup": "September 2026",
  "Walker Cup": "September 2027",
  "Solheim Cup": "September 2027",
};

const CARD_CLASS =
  "bg-surface-card border border-surface-border rounded-xl p-5";
const LINK_CLASS = `${CARD_CLASS} hover:shadow-md hover:-translate-y-0.5 transition-all group`;

export default function ShowcaseEventCard({
  sportSlug,
  event,
}: {
  sportSlug: string;
  event: SportShowcaseEvent;
}) {
  // #2560: THE HUB, WHEN THERE IS ONE. Checked first — a hub has the draw, the
  // probabilities and the results, which is strictly more than a single
  // market's page.
  const hubHref = tournamentHubHref(sportSlug, event.name);
  if (hubHref) {
    return (
      <Link href={hubHref} className={LINK_CLASS} data-testid="showcase-hub-link">
        <h3 className="text-text-primary font-medium group-hover:underline">
          {event.name}
        </h3>
        {/* Ruling 138: the word is PROBABILITY, never "price" — "Draw, live
            prices and results" tripped the shipped-copy ban on the first
            build, which is the guard doing its job on a card written in
            trading vocabulary out of habit. */}
        <p className="text-text-muted text-sm mt-1">
          Draw, live probabilities and results
        </p>
      </Link>
    );
  }

  // #6249: THE MARKET, WHEN WE HOLD ONE.
  const marketId = event.futures_market_id;
  if (marketId) {
    const priced = event.futures_priced_outcomes;
    return (
      <Link
        href={`/futures/${marketId}`}
        className={LINK_CLASS}
        data-testid="showcase-market-link"
      >
        <h3 className="text-text-primary font-medium group-hover:underline">
          {event.name}
        </h3>
        {/* No date: `resolution_date` is when the market closes, not when the
            competition is played, and printing one as the other is the "Date
            TBD" lie with a number on it. */}
        <p className="text-text-muted text-sm mt-1">
          {priced && priced > 0
            ? `Live probabilities · ${priced} contenders`
            : "Live probabilities"}
        </p>
      </Link>
    );
  }

  // Nothing to point at — and saying so is the honest card.
  const estimatedDate = SHOWCASE_DATES[event.name];
  return (
    <div className={CARD_CLASS} data-testid="showcase-empty-card">
      <h3 className="text-text-primary font-medium">{event.name}</h3>
      <p className="text-text-muted text-sm mt-1">{estimatedDate || "Date TBD"}</p>
      <p className="text-text-muted text-xs mt-2">
        Odds available closer to the event
      </p>
    </div>
  );
}
