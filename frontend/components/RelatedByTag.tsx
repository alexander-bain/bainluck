"use client";

import useSWR from "swr";
import { fetchFeed } from "@/lib/api";
import type { FeedConceptData, FeedEventData, FeedFuturesData } from "@/lib/types";
import Link from "next/link";
import { formatProbability } from "@/lib/api";
import { renderedOutcomeRowPercents } from "@/lib/renderedPercent";
import { servedDuelPercents } from "@/lib/servedDuelPercents";
import { eventPath } from "@/lib/eventKey";
import { PriceAgeMark } from "@/components/event/PriceAgeMark";

/** The item types this section knows how to render.
 *
 * UX-P177: this was an inverted list — `event` rendered, `tournament` returned
 * null, and EVERYTHING ELSE fell through to the futures branch. `concept` and
 * `bundle` are both in `FeedItem["type"]` and neither carries a numeric `id`, so
 * a concept rendered as `/futures/undefined` with no probability beside it.
 * Measured live on 2026-08-29: every one of the four rows on `/futures/195`'s
 * "More Mma" section was a concept, so all four were dead links.
 *
 * An allowlist means the next type added to the union is invisible here until
 * someone teaches this component to draw it, rather than silently broken.
 */
const RENDERABLE = new Set(["event", "futures", "concept"]);

/**
 * ═══ ux/1034 B6: "MORE TENNIS" IS A CARD GRID NOW ═══
 *
 * Alex, on `/events/15293830` during the US Open: the section at the bottom of
 * the page is *"formatted horribly"*, and *"make it the same card grid the hub
 * uses."*
 *
 * He was looking at two full-width 44px strips — a 12px market name on the left,
 * a name and a percentage crushed against the right edge, nothing else. At
 * desktop width that put ~900px of empty space between the question and its
 * answer, which is why the eye cannot pair them. It also threw away everything
 * the payload carries: `top_outcomes` holds a whole field, and the strip printed
 * one of them.
 *
 * The hub's grammar, adopted here verbatim rather than approximated (see
 * `components/tournament/TournamentProps`'s `PropCard`):
 *
 *   - a section heading in the site's small-caps rule, with a COUNT;
 *   - one bordered `rounded-2xl` card per item, two-up from `sm`;
 *   - the question at `text-[14px] font-semibold`, the answer beneath it as
 *     ranked rows — name left, probability right, `tabular-nums` so the column
 *     is a column.
 *
 * Two properties are deliberate and are guarded:
 *
 * - **The card is the same shape whatever the item is.** An event, a futures
 *   market and a concept are three different rows in the feed and one kind of
 *   thing to a reader — "something else worth looking at". Three layouts here
 *   would make the section read as three sections.
 * - **A card never invents a number.** A missing probability prints nothing;
 *   the row simply names the subject. The old strip's `formatProbability`
 *   already returned `-` for absent data and that is kept, but a card with no
 *   priced outcome at all shows its title and no field rather than a list of
 *   dashes.
 *
 * ═══ #5961: A CARD'S TWO ROWS ARE ONE ROUNDING ═══
 *
 * Both branches below called `formatProbability(probability)` with no second
 * argument, so every row was rounded on its own and a two-row card could print
 * 101. That is the arithmetic `contracts/rendered_percent.json` exists to
 * replace, and `formatProbabilityPercent`'s `{ rendered }` option is the exact
 * hole this component left unfilled.
 *
 * Measured on production 2026-09-13 19:38Z, over the 17 sport-category feeds
 * these two call sites can request (108 cards): **2 print a sum other than 100
 * and both are corrected** — `Buffalo Bills @ Houston Texans` at 0.625/0.375
 * printing `63` over `38`, and `Will Arthur Fils Make the Top 10…` at
 * 0.785/0.215 printing `79` over `22` while the payload it was handed carried
 * `79` and `21`. Four more print a non-100 and are deliberately LEFT ALONE —
 * `Novak Djokovic: Retirement` (49 + 21), `Russia x Ukraine ceasefire` (23 + 7),
 * `Worlds 2026: Winner` (38 + 1), `Worlds 2026: Finals MVP` (11 + 8) — because
 * those pairs fall outside the complement band and normalizing them would
 * invent probability rather than round it (gotcha #43: the unfixed direction is
 * asserted as explicitly as the fixed one).
 *
 * ALSO SEEN, ALSO THIS: ux/1239 photographed `US Open Men's Singles Winner` on
 * `/events/15310688` at 17:36Z printing `Alexander Zverev 58%` over
 * `Ben Shelton 43%` (`artifacts/ux-1239/SHOP-mens-final-prematch-1736Z-390.png`)
 * — 0.575 + 0.425, an exact complement, on the most-read page of the day.
 */
const CARD =
  "flex flex-col rounded-2xl border border-surface-border bg-surface-card px-3.5 py-3 " +
  "transition-colors hover:border-text-muted/40 hover:bg-surface-elevated/40";

const CARD_TITLE = "min-w-0 text-[14px] font-semibold leading-snug text-text-primary";

const FIELD_ROW = "flex items-baseline justify-between gap-3 text-[12px]";

const FIELD_NAME = "min-w-0 truncate text-text-secondary";

const FIELD_VALUE = "shrink-0 tabular-nums font-semibold text-text-primary";

/** The most outcomes a card lists. Beyond four the card stops being a card. */
const MAX_FIELD_ROWS = 4;

interface RelatedByTagProps {
  /** Tag queries to filter by, e.g. ["sport:basketball"] */
  tags: string[];
  /** ID to exclude from results (current item) */
  excludeId?: number;
  /** Type to match for exclusion */
  excludeType?: "event" | "futures";
  /** Max items to display */
  limit?: number;
  /** Section title */
  title?: string;
}

export default function RelatedByTag({
  tags,
  excludeId,
  excludeType,
  limit = 6,
  title = "More Like This",
}: RelatedByTagProps) {
  const { data, isLoading } = useSWR(
    tags.length > 0 ? ["related-by-tag", ...tags] : null,
    () => fetchFeed({ limit: limit + 5, tags }),
    { refreshInterval: 60000 }
  );

  if (!data || data.items.length === 0) return null;

  // Filter out the current item and limit
  const items = data.items
    .filter((item) => RENDERABLE.has(item.type))
    .filter((item) => {
      if (excludeId === undefined) return true;
      const id =
        item.type === "event"
          ? (item.data as FeedEventData).id
          : item.type === "futures"
          ? (item.data as FeedFuturesData).id
          : null;
      return !(item.type === excludeType && id === excludeId);
    })
    .slice(0, limit);

  if (items.length === 0) return null;

  return (
    <section className="mt-8" data-testid="related-by-tag" data-count={items.length}>
      {/* The hub's section rule, not this component's old `text-sm font-semibold`
          — every other section on an event page is set in it, and this one was
          the odd heading out. The count comes with it for the same reason the
          hub's does: a list that stops at four should say it is four. */}
      <h3
        className="mb-2 text-xs font-bold uppercase tracking-[0.07em] text-text-muted"
        data-testid="related-by-tag-heading"
      >
        {title}
        <span className="ml-1.5 font-normal normal-case tracking-normal">
          · {items.length}
        </span>
      </h3>
      <div className="grid gap-2 sm:grid-cols-2" data-testid="related-by-tag-grid">
        {items.map((item) => {
          if (item.type === "event") {
            const d = item.data as FeedEventData;
            /* A game's field is its two sides. Away first, matching the title,
               so the two lines below read in the order the title names them.

               THE SERVER DECIDES THIS PAIR (#5961), AND IT IS TAKEN WHOLE OR
               NOT AT ALL (#2279). `current_odds.{away,home}_rendered_percent` is
               the card-level answer for a duel, served precisely because four
               surfaces draw this strip; this one ignored it and rounded each
               side independently. `servedDuelPercents` is the adoption every
               other web surface uses: both served or the pair falls back whole
               to the contract rule. Coalescing the two fields SEPARATELY is the
               defect #2279 closed — a payload carrying one and not the other
               (the fields are optional because a Discover response is cached)
               then prints a served value beside a locally derived one, which is
               the same 101 arriving from the other side. */
            const awayProbability = d.current_odds?.away_probability;
            const homeProbability = d.current_odds?.home_probability;
            const duel = servedDuelPercents(
              awayProbability,
              homeProbability,
              d.current_odds?.away_rendered_percent,
              d.current_odds?.home_rendered_percent,
            );
            const sides: {
              name: string;
              probability: number | null | undefined;
              rendered: number | null | undefined;
            }[] = [
              { name: d.away_team, probability: awayProbability, rendered: duel[0] },
              { name: d.home_team, probability: homeProbability, rendered: duel[1] },
            ];
            const priced = sides.some(
              (side) => side.probability !== null && side.probability !== undefined
            );
            return (
              <Link
                key={`rel-event-${d.id}`}
                href={`/events/${d.id}`}
                className={CARD}
                data-testid="related-card"
                data-kind="event"
              >
                <span className="flex items-baseline gap-1.5">
                  {d.status === "live" && (
                    <span
                      aria-hidden="true"
                      className="h-1.5 w-1.5 shrink-0 self-center rounded-full bg-accent-live"
                    />
                  )}
                  <span className={CARD_TITLE}>
                    {d.away_team} @ {d.home_team}
                  </span>
                </span>
                {d.status === "live" && d.home_score !== null && (
                  <span className="mt-px text-[11.5px] tabular-nums text-text-muted">
                    {d.away_score} - {d.home_score}
                  </span>
                )}
                {priced && (
                  <ol className="mt-1.5 space-y-0.5" data-testid="related-card-field">
                    {sides.map((side) => (
                      <li key={side.name} className={FIELD_ROW}>
                        <span className={FIELD_NAME}>{side.name}</span>
                        <span className={FIELD_VALUE}>
                          {formatProbability(side.probability, {
                            rendered: side.rendered,
                          })}
                        </span>
                      </li>
                    ))}
                  </ol>
                )}
              </Link>
            );
          }

          // Event concepts (UFC cards, F1 Grands Prix, cycling grand tours) link
          // to /event/{key}, never /futures/{id} — a concept has no numeric id.
          // The leader is guarded exactly as `ConceptFeedCard` guards it, never
          // laxer: presence plus a real name plus a numeric probability.
          if (item.type === "concept") {
            const d = item.data as FeedConceptData;
            const leader =
              d.leader && (d.leader.name ?? "").trim() &&
              typeof d.leader.probability === "number"
                ? d.leader
                : null;
            return (
              <Link
                key={`rel-concept-${d.key}`}
                href={eventPath(d.key)}
                className={CARD}
                data-testid="related-card"
                data-kind="concept"
              >
                <span className={CARD_TITLE}>{d.name}</span>
                {leader && (
                  <ol className="mt-1.5 space-y-0.5" data-testid="related-card-field">
                    <li className={FIELD_ROW}>
                      <span className={FIELD_NAME}>{leader.name}</span>
                      <span className={FIELD_VALUE}>
                        {formatProbability(leader.probability)}
                      </span>
                    </li>
                  </ol>
                )}
              </Link>
            );
          }

          // Futures
          const d = item.data as FeedFuturesData;
          /* THE WHOLE FIELD, not just the leader (ux/1034 B6). `top_outcomes`
             has always been in this payload and the strip printed one row of
             it — on `US Open Men's Singles Winner` that is Alcaraz and nothing
             else, which is the least interesting true thing the card could say.
             Unpriced outcomes are dropped rather than printed as `-`: a rank
             with no number in it is not a rank. */
          const field = (d.top_outcomes ?? [])
            .filter((outcome) => typeof outcome.probability === "number")
            .slice(0, MAX_FIELD_ROWS);
          /* THE SERVED PERCENT ANSWERS FOR A CARD THIS ONE IS NOT (#5961), so
             here the card rule is re-derived over the rows actually printed and
             the served value is the fallback — the opposite precedence to the
             game branch above, for a reason.

             `feed._apply_card_percents` says it plainly: it is taken over the
             already-sliced `top_outcomes_data`, "which IS the printed card …
             the arity here is the arity a reader sees". True of `FeedCard`,
             which prints all three. NOT true here: the filter directly above
             drops unpriced outcomes (ux/1034 B6 — "a rank with no number in it
             is not a rank"), so a knockout market narrowed to two priced
             finalists arrives as arity 3 and is PRINTED as arity 2. The server
             rounded three outcomes independently and was right to; the card
             then showed two of them as a pair. That gap is the whole defect,
             and it opened the day this component started filtering.

             `renderedOutcomeRowPercents` yields all-nulls for any arity but
             two, so on every other card this reads through to the server's own
             answer and nothing moves.

             WHOLE OR NOT AT ALL, for #2279's reason one arm wider: the choice
             is made ONCE for the card rather than per row, so no card can ever
             print a derived number beside a served one. */
          const derivedField = renderedOutcomeRowPercents(
            field.map((outcome) => outcome.probability),
          );
          const fieldPercents = derivedField.every((percent) => percent !== null)
            ? derivedField
            : field.map((outcome) => outcome.rendered_percent ?? null);
          return (
            <Link
              key={`rel-futures-${d.id}`}
              href={`/futures/${d.id}`}
              className={CARD}
              data-testid="related-card"
              data-kind="futures"
            >
              <span className={CARD_TITLE}>{d.name}</span>
              {field.length > 0 && (
                <ol className="mt-1.5 space-y-0.5" data-testid="related-card-field">
                  {field.map((outcome, index) => (
                    <li key={outcome.name} className={FIELD_ROW}>
                      <span className={FIELD_NAME}>{outcome.name}</span>
                      <span className={FIELD_VALUE}>
                        {formatProbability(outcome.probability, {
                          rendered: fieldPercents[index],
                        })}
                      </span>
                    </li>
                  ))}
                </ol>
              )}
              {/* How much of the field is NOT on the card, and how old the
                  numbers on it are (#5752) — one muted footer line, because two
                  stacked ones would take a row off a card whose whole job is the
                  field above them.

                  The age is the reason this section was filed on. On the US Open
                  women's final page the hero said Sabalenka 40% with a `20s`
                  stamp and this rail said 59% two screens down with no stamp at
                  all: one question, two answers, and nothing telling a reader
                  which was current. The card was not wrong — its price was an
                  hour old, set twenty minutes before the match started.

                  `PriceAgeMark` draws nothing inside 30 minutes and nothing for
                  an undatable stamp, so a rail beside a quiet market stays as
                  plain as it is today. `justify-between` rather than a gap:
                  when only one of the two is present it keeps its own side.

                  🔴 #5843 MOVED THE DISCOVER CARDS TO A 6h FUTURES CADENCE AND
                  DELIBERATELY LEFT THIS RAIL AT 30 MINUTES. These are the same
                  hourly-polled ladders (this rail calls `fetchFeed`), so the
                  consistency argument says to move it too. The reason not to is
                  the paragraph above: this rail's specimen IS the 61-minute
                  card, and it is the one place a futures price is rendered two
                  screens under a hero that restamps every 20 seconds. On
                  Discover a 50-minute ladder has nothing to be ranked against
                  and the mark was noise on 30 of 30 cards; here the reader is
                  holding two answers to one question and the age is the only
                  thing that ranks them. Six rows, not thirty, and a mark that
                  earns its place. Moving this to 6h would silence exactly the
                  case #5752 was filed on. */}
              {(d.outcome_count > field.length && field.length > 0) ||
              d.price_observed_at ? (
                <span className="mt-1.5 flex items-baseline justify-between gap-2 text-[11px] text-text-muted">
                  {d.outcome_count > field.length && field.length > 0 ? (
                    <span data-testid="related-card-more">
                      +{d.outcome_count - field.length} more
                    </span>
                  ) : (
                    <span />
                  )}
                  <PriceAgeMark observedAt={d.price_observed_at} scope="card" />
                </span>
              ) : null}
            </Link>
          );
        })}
      </div>
    </section>
  );
}
