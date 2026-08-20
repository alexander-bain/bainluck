"use client";

/**
 * The travelled bar — ONE implementation, shared by THE DIVERGENCE rail and its
 * detail view.
 *
 * Extracted from `PropDivergenceRail` in UX-P101 rather than copied. The rail
 * and the detail view are allowed to disagree about which rows they show and
 * about nothing else; two bar implementations would drift on exactly the thing
 * the reader compares across the fold — the position of the tick and the head.
 *
 * Domain is fixed 0-100% so rows are comparable to each other and to the native
 * chart's single-axis convention (`project_native_chart_single_axis`).
 *
 * ── POST-GAME IS A DIFFERENT ELEMENT, NOT A DIFFERENT COLOUR (UX-P105, #2011) ──
 *
 * Alex, on the expand captures: *"shouldn't it always finish at 0% or 100%? …
 * post-game it doesn't make any sense."* It didn't: the head was drawn at
 * `row.current`, which after settlement is the LAST TRADED PRICE, and the label
 * read `final 58%` — a price wearing the grammar of a result. So a settled row
 * renders the mark and the outcome, and no travel bar at all.
 *
 * The dispatch lives HERE, in the one shared component, for the same reason the
 * component was extracted: both surfaces get the post-game treatment, or the
 * two halves of one screen disagree about whether a game is over.
 */

import type { DivergenceRow } from "@/lib/propDivergence";
import { propVerdictLabel, SETTLED_NO_GRADE_LABEL } from "@/lib/propGrade";

export function pct(p: number): string {
  return `${Math.round(p * 100)}%`;
}

/** Signed travel in points, the mock's "−40" pill. In-game only. */
export function signedTravelPoints(row: DivergenceRow): string {
  const pts = Math.round((row.current - row.pregameMark) * 100);
  if (pts === 0) return "0";
  return pts > 0 ? `+${pts}` : `${pts}`;
}

/**
 * Distance from the pregame mark to the outcome, in points. Post-game only, and
 * unsigned on purpose — the direction is already stated in words next to it,
 * and a "+93" reads as a price move, which is the thing this replaces.
 */
export function surprisePoints(row: DivergenceRow): string | null {
  if (row.surprise == null) return null;
  return `${Math.round(row.surprise * 100)} pts`;
}

/**
 * The outcome, in the site's ONE settled vocabulary. `null` when nothing may be
 * stated.
 *
 * This function's first draft returned "HAPPENED" / "DIDN'T HAPPEN" — a THIRD
 * vocabulary on a screen that already stacks the prop cards and WHAT HIT, both
 * of which say HIT / MISS. That is #1650 reproduced inside the fix for #2011,
 * and it was caught in the rendered screenshot rather than by any test, which
 * is why the words now live in `propGrade` and all three surfaces import them.
 */
export function resolutionLabel(row: DivergenceRow): string | null {
  if (row.resolution == null) return null;
  return propVerdictLabel(row.resolution === 1);
}

/**
 * A settled row: what the market marked it at, and what actually happened.
 *
 * No bar, per #2011's scope. The mark is still shown — it is the whole point of
 * THE SCRIPT, and dropping it would leave the outcome with nothing to be
 * surprising against.
 */
function ResolvedMark({ row }: { row: DivergenceRow }) {
  const label = resolutionLabel(row);

  // Settled, but the backend published no verdict we may state. `propGrade` is
  // the one authority for that sentence; restating it here is how #1650 got one
  // backend state wearing three vocabularies on one screen.
  if (label == null) {
    return (
      <div className="mt-1.5 flex items-baseline justify-between gap-3 text-[11px]">
        <span className="text-text-muted">marked {pct(row.pregameMark)}</span>
        <span className="text-text-muted">{SETTLED_NO_GRADE_LABEL}</span>
      </div>
    );
  }

  const tone = row.resolution === 1 ? "text-accent-live" : "text-accent-danger";

  return (
    <div
      className="mt-1.5 flex items-baseline justify-between gap-3 text-[11px] tabular-nums"
      role="img"
      aria-label={`${row.label}: marked ${pct(row.pregameMark)}, ${
        row.resolution === 1 ? "hit" : "missed"
      }`}
    >
      <span className="text-text-muted">
        marked {pct(row.pregameMark)} <span aria-hidden="true">&rarr;</span>{" "}
        <span className={`font-semibold ${tone}`}>{label}</span>
      </span>
      <span className="text-text-secondary">{surprisePoints(row)}</span>
    </div>
  );
}

/**
 * THE SCRIPT's row — what the market expects, before anything has happened.
 *
 * UX-P106. A pregame page has no travel and no outcome, so it gets neither a
 * travelled bar (there is no journey to draw) nor a resolution (nothing has
 * landed). It gets the CLAIM: how far the market is willing to go from a coin
 * flip, and in which direction.
 *
 * ── WHY THE 50% LINE IS DRAWN AND THE BAR FILLS FROM IT ──────────────────────
 *
 * **84.2% of pregame marks on the measured population sit BELOW 0.5.** A
 * conventional left-anchored fill renders that majority as a nearly-empty
 * track — visually "nothing here" — when the market is in fact making its most
 * confident statements. A prop at 7% is not a weak claim; it is a strong claim
 * pointing the other way, and it must look as loud as a prop at 93%.
 *
 * So the track is centred on the coin flip and the bar grows OUT from it. Bar
 * length is conviction; the side it grows to is the direction. The two 7%/93%
 * rows then draw as mirror images of equal weight, which is what they are.
 *
 * That is ruling (a) applied to a shape rather than to a sentence: the code
 * types the direction off the OVER-SIDE price, never off the row's own outcome.
 *
 * The bar quotes `current` — the standing expectation at the moment the page is
 * opened — not the opening capture. A first draft quoted the opening mark and
 * the rendered capture showed the cost immediately: Schwarber's row read
 * "opened at 27% — it's 55% now" above a bar saying "market says NO, 73%".
 */
function ScriptMark({ row }: { row: DivergenceRow }) {
  const willHappen = row.scriptSide === "will";
  const tossUp = row.scriptSide === "toss_up";

  // The probability OF THE STATED DIRECTION, read off the SAME number the
  // direction was typed from.
  //
  // The second render caught this too: after `scriptSide` moved to `current`,
  // this line still read `pregameMark`, so Schwarber's row printed "market says
  // YES — 27%" — the direction from the live price and the number from the
  // opening capture, contradicting each other inside four words. Deriving both
  // from one value is what makes that unexpressible rather than merely fixed.
  const stated = willHappen ? row.current : 1 - row.current;

  // Half-width, because the bar spans from the centre to one side only.
  //
  // ROUNDED, and a test caught why: `0.43 * 100` is `43.00000000000001` in
  // IEEE-754, so a 7% claim shipped that into the DOM while its 93% mirror
  // shipped a clean `43`. Two bars that are the same length by construction
  // must be the same STRING, or every diff of this markup carries a phantom.
  const half = `${Math.round(row.conviction * 1000) / 10}%`;
  const tone = tossUp
    ? "bg-surface-border"
    : willHappen
      ? "bg-accent-live"
      : "bg-accent-danger";
  const textTone = tossUp
    ? "text-text-muted"
    : willHappen
      ? "text-accent-live"
      : "text-accent-danger";

  return (
    <div className="mt-1.5">
      <div
        className="relative h-2 rounded-full bg-surface-border/40"
        role="img"
        aria-label={
          tossUp
            ? `${row.label}: a coin flip, the market has no view`
            : `${row.label}: the market says this ${
                willHappen ? "will" : "will not"
              } happen, ${pct(stated)}`
        }
      >
        {/* The coin flip. Every claim on the page is measured from here. */}
        <div className="absolute left-1/2 -top-0.5 h-3 w-px -translate-x-1/2 bg-text-muted" />
        {/* Conviction, growing out from the centre toward the side it favours. */}
        <div
          className={`absolute top-0 h-2 rounded-full ${tone}`}
          style={
            willHappen
              ? { left: "50%", width: half }
              : { right: "50%", width: half }
          }
        />
      </div>
      <div className="mt-1 flex items-baseline justify-between gap-2 text-[11px] tabular-nums">
        <span className="text-text-muted">
          {tossUp ? (
            "coin flip"
          ) : (
            <>
              market says{" "}
              <span className={`font-semibold ${textTone}`}>
                {willHappen ? "YES" : "NO"}
              </span>
            </>
          )}
        </span>
        {!tossUp && <span className="text-text-secondary font-medium">{pct(stated)}</span>}
      </div>
    </div>
  );
}

export default function PropTravelBar({ row }: { row: DivergenceRow }) {
  if (row.settled) return <ResolvedMark row={row} />;
  if (row.pregame) return <ScriptMark row={row} />;

  const from = Math.min(row.pregameMark, row.current);
  const to = Math.max(row.pregameMark, row.current);
  const left = `${from * 100}%`;
  const width = `${Math.max(to - from, 0) * 100}%`;

  // Direction by colour, design-system tokens only (the site is light-mode
  // only; raw Tailwind dark classes are banned).
  const spanTone =
    row.direction === "over"
      ? "bg-accent-live"
      : row.direction === "under"
        ? "bg-accent-danger"
        : "bg-surface-border";
  const headTone =
    row.direction === "over"
      ? "bg-accent-live"
      : row.direction === "under"
        ? "bg-accent-danger"
        : "bg-text-muted";

  return (
    <div className="mt-1.5">
      <div
        className="relative h-2 rounded-full bg-surface-border/40"
        role="img"
        aria-label={`${row.label}: opened at ${pct(row.pregameMark)}, now ${pct(row.current)}`}
      >
        {/* the travel */}
        <div
          className={`absolute top-0 h-2 rounded-full ${spanTone}`}
          style={{ left, width }}
        />
        {/* where the market opened the question */}
        <div
          className="absolute -top-0.5 h-3 w-px bg-text-muted"
          style={{ left: `${row.pregameMark * 100}%` }}
        />
        {/* where it is now */}
        <div
          className={`absolute -top-0.5 h-3 w-[3px] rounded-sm ${headTone}`}
          style={{ left: `${row.current * 100}%` }}
        />
      </div>
      <div className="mt-1 flex items-center justify-between text-[11px] text-text-muted tabular-nums">
        <span>opened {pct(row.pregameMark)}</span>
        <span className="text-text-secondary font-medium">now {pct(row.current)}</span>
      </div>
    </div>
  );
}
