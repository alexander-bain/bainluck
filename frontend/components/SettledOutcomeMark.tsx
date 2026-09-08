/**
 * #3868 (CERT-2215) — SETTLED MEANS SETTLED. The one settled vocabulary every
 * card that renders a `LeagueMarketOutcome` speaks.
 *
 * `/sport/tennis/atp` showed Carlos Alcaraz at 78% to reach a quarterfinal he
 * had already reached. The backend half of #3868 taught the refresh rail to read
 * the venue's settlement, which fixed the NUMBER — and a settled leg then
 * arrived at the card as a bare `probability: 1.0` and was drawn as an ordinary
 * "100%". A result rendered as a probability is still the card offering odds on
 * a question that has been answered.
 *
 * The words are `FuturesCard`'s, character for character, not a second settled
 * vocabulary invented on a second card — Alex's standing ruling is one
 * system-wide settled language. (The COLOUR half of that claim turns out not to
 * hold; see the note on `SettledMark` below and #4040.)
 *
 * ── #4036: LIFTED OUT OF `PropGroupCard`, WHICH IS WHY THIS FILE EXISTS ──
 *
 * `PropGroupCard` owned this privately and honoured it correctly, so #3868 read
 * as shipped. It was not: the hub's own `OutcomeRow`
 * (`app/hub/[competition]/page.tsx`) renders the same `top_outcomes` rows off
 * the same payload and read neither field, so the identical bug was live on
 * `/hub/*` the whole time. Measured 2026-09-08 across all five hubs: of 426
 * cards carrying outcomes, **10 drew a settled leg as an ordinary percentage** —
 * worst of them `/hub/tennis`' "Who will win a ATP Grand Slam in 2026?", where
 * Zverev, Sinner and Alcaraz were shown at 99% / 99% / 97%, bars and all, while
 * each carried `is_winner: true`. Three men who had won, priced as contenders.
 *
 * A private helper on one card cannot be reused, and a rule that cannot be
 * reused gets re-derived or forgotten. This is the shared home so the third card
 * to need it imports the rule instead of restating it — or, as happened here,
 * instead of not having it at all.
 */
import type { LeagueMarketOutcome } from "@/lib/api";

/**
 * Reads the GRADE the payload carries and never `probability === 1`. Inferring
 * settlement from certainty would stamp a result on a live book at 0.9995,
 * which is what the Alcaraz leg genuinely read for a day before it closed.
 *
 * `settled` is optional across a split deploy — Vercel ships the frontend before
 * Heroku, so an older payload carries neither field. Absent reads as not
 * settled, and renders exactly as it did before.
 */
export function isSettledOutcome(o: Pick<LeagueMarketOutcome, "settled">): boolean {
  return o.settled === true;
}

/**
 * 🔴 `text-emerald-600` IS A DEAD CLASS AND THIS IS DELIBERATELY UNCHANGED (#4040).
 *
 * `tailwind.config` defines `emerald` as a FLAT colour (`emerald: '#10B981'`),
 * which replaces Tailwind's default emerald SCALE — so `emerald-600` does not
 * exist and the utility generates no rule. Verified in the built CSS: there is
 * no `.text-emerald-600` anywhere in `.next/static/css/*`. The mark therefore
 * inherits its parent's `text-text-primary` and "Won" has been rendering
 * near-black (`rgb(17,24,39)`) on `PropGroupCard` since #3868 — measured on a
 * local production build 2026-09-08.
 *
 * Left byte-identical ON PURPOSE. #4036 lifted this out of `PropGroupCard`, and
 * the value of that move is that it is provably a no-op for the card that
 * already had it; changing the colour in the same diff would make the extraction
 * unprovable and would repaint two surfaces this ship never looked at. The words
 * carry the meaning either way — "Won" bold against "Lost" muted reads correctly
 * today. Filed as #4040; fix it there, for every caller at once.
 */
export function SettledMark({ won }: { won: boolean }) {
  return won ? (
    <span className="text-xs font-mono font-bold text-emerald-600">Won</span>
  ) : (
    <span className="text-xs font-mono text-text-muted">Lost</span>
  );
}
