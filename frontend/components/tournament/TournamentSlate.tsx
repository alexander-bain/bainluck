"use client";

import React from "react";
import ShowMore, { COLLAPSED_LIST_COUNT } from "./ShowMore";
import {
  formatMove,
  formatSlateProbability,
  matchNarrative,
  matchTime,
  moveDirection,
  orderedSides,
  slateGroups,
  slateNotice,
  slateRowFreshnessLabel,
  slateRowIsPresentedAsLive,
  matchBroadcast,
  type Broadcast,
  type SlateData,
  type SlateMatch,
} from "@/lib/slate";

/**
 * The daily slate — the day's matches, "the script vs the divergence".
 *
 * This is the half of the US Open hub that has live prices. The championship
 * boards have been dark for 8-32 days (#2199); the match markets were captured
 * minutes ago. So the honesty treatment here is the exception rather than the
 * rule — but it is the SAME treatment, because a page that words staleness two
 * ways teaches the reader that one of them is decorative.
 *
 * Two rules to preserve if this is ever rewritten:
 *
 * 1. **Never print Yes/No.** Both sides come from the register's `sides` map,
 *    pinned offline from the source's own ordered labels. If the mapping is
 *    missing the server drops the row; this component never guesses a side.
 *
 * 2. **An incoherent pair shows no split.** When two independent binary quotes
 *    do not describe one question (gotcha #23), the server sends
 *    `coherent: false` and both probabilities `null`. The row still renders —
 *    the match is still on, and that is the useful part — but it says the
 *    prices disagree instead of showing a normalized number with no referent.
 *
 * 3. **A muted row says why it is muted.** Since UX-P135 a pair is only live
 *    when BOTH its sides are, so a row can be greyed while the slate banner
 *    above it still reads live. A muted number with no stated reason is worse
 *    than either a live one or an absent one — the reader assumes a bug or,
 *    worse, does not notice. So the age travels with the row.
 *
 * 4. **Where to watch rides the ROW** (UX-P137, Alex's ruling 8). It used to
 *    be one line above the whole list, on the argument that the rights are
 *    tournament-wide. Alex overruled that: the answer differs match to match,
 *    and a single line at the top of a long list is wrong. Note that today
 *    every row resolves to the same region-wide answer, because that is all
 *    the register holds — `matchBroadcast` explains what refuses to invent the
 *    rest.
 *
 * 5. **Five matches then an expander**, per day group (ruling 5/9).
 */

function SlateRow({
  match,
  broadcasts,
}: {
  match: SlateMatch;
  broadcasts?: Broadcast[];
}) {
  const isLive = slateRowIsPresentedAsLive(match);
  const ordered = orderedSides(match);
  const freshness = slateRowFreshnessLabel(match);
  const watch = matchBroadcast(match, broadcasts);

  return (
    <li
      className="border-t border-surface-border px-3.5 py-3 first:border-t-0"
      data-testid="slate-row"
      data-matchup={match.matchup_key}
      data-live={isLive ? "true" : "false"}
      data-coherent={match.coherent ? "true" : "false"}
      data-price-state={match.price_state}
    >
      <div className="mb-1.5 flex items-center gap-2 text-[10.5px] uppercase tracking-[0.06em] text-text-muted">
        <span className="tabular-nums">{matchTime(match.scheduled_date)}</span>
        <span aria-hidden="true">·</span>
        <span>{match.draw_label}</span>
        {watch && (
          <>
            <span aria-hidden="true">·</span>
            <span
              data-testid="slate-row-broadcast"
              data-region={watch.region}
              data-broadcast-scope={watch.scope}
            >
              <span className="sr-only">Where to watch: </span>
              {watch.channels.join(", ")}
            </span>
          </>
        )}
        {match.has_moved && isLive && (
          <span className="text-accent-brand" data-testid="slate-moved">
            Moved
          </span>
        )}
        {freshness !== null && (
          <span className="normal-case tracking-normal text-accent-warning" data-testid="slate-row-age">
            {freshness}
          </span>
        )}
      </div>

      {ordered === null ? (
        <div data-testid="slate-incoherent">
          <div className="text-[15px] font-semibold text-text-primary">
            {match.sides.map((side) => side.display_name).join(" vs ")}
          </div>
          <p className="mt-0.5 text-[12px] text-text-secondary">
            The two prices for this match do not agree yet, so we are not showing a split.
          </p>
        </div>
      ) : (
        <>
          {ordered.map((side, index) => {
            const direction = moveDirection(side.move);
            const move = formatMove(side.move);
            return (
              <div
                key={side.entity_key}
                className="flex items-baseline justify-between gap-3 py-0.5"
                data-testid="slate-side"
                data-entity={side.entity_key}
                data-favourite={index === 0 ? "true" : "false"}
              >
                <span
                  className={`min-w-0 truncate text-[15px] ${
                    index === 0
                      ? "font-semibold text-text-primary"
                      : "font-normal text-text-secondary"
                  }`}
                >
                  {side.display_name}
                  {side.seed !== null && (
                    <span className="ml-1.5 text-xs font-normal text-text-muted">
                      [{side.seed}]
                    </span>
                  )}
                </span>

                <span className="flex shrink-0 items-baseline gap-2">
                  {move !== "" && (
                    <span
                      className={`text-[11px] tabular-nums ${
                        !isLive
                          ? "text-text-muted"
                          : direction === "up"
                            ? "text-accent-live"
                            : "text-accent-danger"
                      }`}
                      data-testid="slate-move"
                    >
                      {move}
                    </span>
                  )}
                  <span
                    className={`text-[17px] font-bold tabular-nums tracking-tight ${
                      isLive ? "text-text-primary" : "text-text-secondary"
                    }`}
                    data-testid="slate-probability"
                  >
                    {formatSlateProbability(side.probability)}
                  </span>
                </span>
              </div>
            );
          })}

          <p className="mt-1 text-[11.5px] leading-snug text-text-muted" data-testid="slate-narrative">
            {matchNarrative(match)}
          </p>
        </>
      )}
    </li>
  );
}

/**
 * One calendar day of matches, collapsed to five (ruling 5).
 *
 * Per group and not across the whole slate: the collapse exists so the reader
 * can see WHAT SECTIONS THE PAGE HAS without scrolling past one of them, and a
 * single cap over a multi-day slate would hide tomorrow entirely behind
 * today's long list — which is the same failure with a different victim.
 */
function SlateGroup({
  dayKey,
  heading,
  matches,
  broadcasts,
}: {
  dayKey: string;
  heading: string;
  matches: SlateMatch[];
  broadcasts?: Broadcast[];
}) {
  const [expanded, setExpanded] = React.useState(false);
  const visible = expanded ? matches : matches.slice(0, COLLAPSED_LIST_COUNT);

  return (
    <div data-testid="slate-group" data-day={dayKey} data-count={matches.length}>
      <h2 className="mb-2 mt-6 text-xs font-bold uppercase tracking-[0.07em] text-text-muted">
        {heading}
        <span className="ml-1.5 font-normal normal-case tracking-normal">
          · {matches.length} {matches.length === 1 ? "match" : "matches"}
        </span>
      </h2>
      <div className="overflow-hidden rounded-2xl border border-surface-border bg-surface-card">
        <ol>
          {visible.map((match) => (
            <SlateRow key={match.matchup_key} match={match} broadcasts={broadcasts} />
          ))}
        </ol>
        {matches.length > COLLAPSED_LIST_COUNT && (
          <ShowMore
            expanded={expanded}
            total={matches.length}
            onToggle={() => setExpanded((value) => !value)}
          />
        )}
      </div>
    </div>
  );
}

export default function TournamentSlate({
  slate,
  draw,
  broadcasts,
}: {
  slate: SlateData;
  /** When set, show only this draw's matches — the gender pill drives it, and
   *  the page never stacks two gender lists (Alex's mock verdict). */
  draw?: string;
  /** Where to watch (Alex's item 4, moved to the row by ruling 8). */
  broadcasts?: Broadcast[];
}) {
  const notice = slateNotice(slate);
  const matches = draw
    ? slate.matches.filter((match) => match.draw === draw)
    : slate.matches;
  const groups = slateGroups(matches);
  const incoherent = matches.filter((match) => !match.coherent).length;

  if (matches.length === 0) {
    return (
      <div
        className="mt-6 rounded-2xl border border-surface-border bg-surface-card px-4 py-6 text-center"
        data-testid="slate-empty"
      >
        <div className="text-[15px] font-semibold text-text-primary">No matches scheduled</div>
        <p className="mt-1 text-[13px] text-text-secondary">
          Nothing is on right now. The day&rsquo;s matches appear here as they are scheduled.
        </p>
      </div>
    );
  }

  return (
    <section data-testid="tournament-slate">
      {notice && (
        <div
          className="mt-6 flex items-start gap-2 rounded-2xl border border-surface-border bg-accent-warning/10 px-3.5 py-2.5 text-[11.5px] text-text-secondary"
          data-testid="slate-notice"
          data-tone={notice.tone}
          role="status"
        >
          <span aria-hidden="true" className="text-accent-warning">
            &#9888;
          </span>
          <span>
            <b className="font-bold text-text-primary">{notice.headline}.</b> {notice.detail}
          </span>
        </div>
      )}

      {groups.map((group) => (
        <SlateGroup
          key={group.dayKey}
          dayKey={group.dayKey}
          heading={group.heading}
          matches={group.matches}
          broadcasts={broadcasts}
        />
      ))}

      {incoherent > 0 && (
        <p className="mt-2 text-[11px] text-text-muted" data-testid="slate-incoherent-count">
          {incoherent} {incoherent === 1 ? "match has" : "matches have"} prices that do not agree
          yet.
        </p>
      )}
    </section>
  );
}
