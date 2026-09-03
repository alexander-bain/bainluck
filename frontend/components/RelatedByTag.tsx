"use client";

import useSWR from "swr";
import { fetchFeed } from "@/lib/api";
import type { FeedConceptData, FeedEventData, FeedFuturesData } from "@/lib/types";
import Link from "next/link";
import { formatProbability } from "@/lib/api";
import { eventPath } from "@/lib/eventKey";

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
               so the two lines below read in the order the title names them. */
            const sides: { name: string; probability: number | null | undefined }[] = [
              { name: d.away_team, probability: d.current_odds?.away_probability },
              { name: d.home_team, probability: d.current_odds?.home_probability },
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
                          {formatProbability(side.probability)}
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
                  {field.map((outcome) => (
                    <li key={outcome.name} className={FIELD_ROW}>
                      <span className={FIELD_NAME}>{outcome.name}</span>
                      <span className={FIELD_VALUE}>
                        {formatProbability(outcome.probability)}
                      </span>
                    </li>
                  ))}
                </ol>
              )}
              {/* How much of the field is NOT on the card. The hub's list says
                  this too; without it a four-row card over a 128-player draw
                  reads as the whole answer. */}
              {d.outcome_count > field.length && field.length > 0 && (
                <span
                  className="mt-1.5 text-[11px] text-text-muted"
                  data-testid="related-card-more"
                >
                  +{d.outcome_count - field.length} more
                </span>
              )}
            </Link>
          );
        })}
      </div>
    </section>
  );
}
