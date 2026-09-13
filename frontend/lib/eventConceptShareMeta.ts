/**
 * THE COPY A PASTED `/event/<domain>/<slug>` LINK UNFURLS WITH (#5833).
 *
 * Pure, so the decision is testable without a browser and without the network:
 * `app/event/[domain]/[slug]/layout.tsx` fetches, this module decides, and the
 * two jobs never mix. `lib/tournamentShareMeta.ts` is the same split for
 * tournament hubs and `lib/eventShareMeta.ts` for single games.
 *
 * ═══ WHAT WAS ON PRODUCTION BEFORE THIS ═══
 *
 * `app/event/[domain]/[slug]/` held one `"use client"` `page.tsx` and no
 * layout, so the route rendered the ROOT metadata verbatim. Read with a crawler
 * UA at 2026-09-13 06:43:37Z, `/event/election/2026-midterms` — which
 * `BottomNav` and `DesktopNav` link from EVERY page of the site — and
 * `/event/ufc/nonexistent-slug-xyz-99` were byte-identical:
 *
 *   <title>Bain Luck — Prediction Market Discovery</title>
 *   <link rel="canonical" href="https://www.bainluck.com">
 *   <meta property="og:url" content="https://www.bainluck.com">
 *
 * The page DOES compute a canonical, in a `useEffect` that writes a `<link>`
 * into the DOM. An unfurler does not run JavaScript, so that code has never
 * once run for the reader this is about.
 *
 * The legacy single-segment route `/event/event%3A<domain>%3A<slug>` is a real
 * server-side 308 to this one (measured: `308 → /event/ufc/26sep15`), so every
 * old shared link inherits whatever this route says.
 *
 * ═══ THE SEPARATOR IS AN EM DASH WHEN THE NAME ALREADY HAS A COLON ═══
 *
 * `/events/[id]` and `/tournaments/[slug]` both write `<subject>: <A> <p>%`.
 * That shape is right here too, except that combat cards — the single biggest
 * family on this route — are NAMED with a colon: "Contender Series: Hunt vs
 * Perea", "Fight Night: Klose vs Gantt". The house shape would print two colons
 * in one title. So the separator is chosen from the name, not from the surface.
 *
 * ═══ DUEL VS FIELD, AND WHY NOT A FIXED CAP ═══
 *
 * `primary.kind` is `"co_equal_list"` for BOTH a two-fighter main event and a
 * 25-candidate governor's race, so it cannot make this decision. The count can:
 * exactly two priced competitors is a duel and both get named; three or more is
 * a field and only the leader does. Naming the runner-up of a 25-way race at 5%
 * spends the title on nothing.
 *
 * ═══ WHY NOT `settledChampion()` ═══
 *
 * `lib/eventConceptDisplay.ts` already has a champion helper, and reusing it
 * here would be wrong. It falls back to "top competitor priced ≥ 0.9" when no
 * `won` flag is set. That is a reasonable tiebreak for a leaderboard ROW, which
 * prints a percentage either way — and a false result claim on a share card,
 * which prints a sentence. It is not hypothetical: `event:ufc:26sep12` was
 * `status: "live"` with its favourite at 0.99 while this was written, so the
 * helper would have unfurled a fight in progress as won.
 *
 * So a winner is claimed from the authoritative pair ONLY — `event.status` is
 * `"settled"` AND some competitor carries `won === true`. A settled event with
 * no flagged winner gets `/events/[id]`'s last rung verbatim in spirit: it is
 * over, and we do not have the result. That rung exists because a forecast
 * printed on a closed question is not a smaller lie than a wrong result
 * (#1495).
 *
 * No settled specimen was reachable while this was built — the adapters only
 * synthesize current events, so past keys answer with an empty envelope and
 * `event:tennis:us-open-men-s-singles-winner` still read `live` with every
 * `won` false. The settled branches are therefore proven against manufactured
 * payloads, which is the only way to shoot a fallback path that has no natural
 * specimen.
 */

import { formatShareProbability, truncateShareText } from "@/lib/share";

/** The slice of `GET /api/event/{key}` this copy reads. */
export interface EventConceptShareCompetitor {
  name?: string | null;
  probability?: number | null;
  /** L2-81: authoritative settled winner flag, written from resolution. */
  won?: boolean | null;
}

export interface EventConceptShareSource {
  event?: {
    name?: string | null;
    /** The pretty, self-resolving slug the backend supplies, when it has one. */
    slug?: string | null;
    status?: string | null;
    venue?: string | null;
    location?: string | null;
  } | null;
  primary?: {
    label?: string | null;
    competitors?: EventConceptShareCompetitor[] | null;
  } | null;
}

/** A competitor we are willing to print: a name and a printable probability. */
interface PricedCompetitor {
  name: string;
  /** Already formatted, e.g. `"55%"`. */
  probability: string;
}

/**
 * Labels that name the ROLE rather than a sub-contest, so a sentence must not
 * say "leads the ___".
 *
 * The tennis adapter's primary label is the bare word "Winner", which turns the
 * natural sentence into "Alexander Zverev leads the Winner at 57%". A label
 * that names something real — "Main event", "California Governor" — reads
 * correctly in the same slot, so only the generic ones are dropped.
 */
const GENERIC_PRIMARY_LABEL = /^(winner|winner\?|champion|champ|outright)$/i;

function cleanText(value: string | null | undefined): string | null {
  const trimmed = (value ?? "").trim();
  return trimmed.length > 0 ? trimmed : null;
}

/** The primary's label, or null when it is absent or names only the role. */
function contestLabel(source: EventConceptShareSource): string | null {
  const label = cleanText(source.primary?.label);
  if (!label || GENERIC_PRIMARY_LABEL.test(label)) return null;
  return label;
}

/** Venue and location as one phrase ("Flushing Meadows, New York"), or null. */
function place(source: EventConceptShareSource): string | null {
  const parts = [
    cleanText(source.event?.venue),
    cleanText(source.event?.location),
  ].filter((part): part is string => part !== null);
  return parts.length > 0 ? parts.join(", ") : null;
}

/**
 * The primary's priced competitors, best first.
 *
 * Sorted here rather than trusting arrival order: the payload does arrive
 * ranked, but depending on that makes the copy rest on a property of the
 * producer that nothing on this side asserts. `boardLeader` in
 * `tournamentShareMeta` and `topOutcome` in `/futures/[id]` sort for the same
 * reason.
 *
 * `formatShareProbability` returns null for null/NaN/0, so a 0% longshot is
 * dropped rather than printed — the tennis winner field is mostly those.
 */
function pricedCompetitors(
  source: EventConceptShareSource
): PricedCompetitor[] {
  const competitors = (source.primary?.competitors ?? []).filter(
    (competitor): competitor is EventConceptShareCompetitor => competitor != null
  );

  return [...competitors]
    .sort((a, b) => (b.probability ?? -1) - (a.probability ?? -1))
    .map((competitor) => {
      const name = cleanText(competitor.name);
      const probability = formatShareProbability(competitor.probability);
      return name && probability ? { name, probability } : null;
    })
    .filter((competitor): competitor is PricedCompetitor => competitor !== null);
}

/** The flagged winner's name, or null. Never inferred from a price. */
function flaggedWinner(source: EventConceptShareSource): string | null {
  if (cleanText(source.event?.status)?.toLowerCase() !== "settled") return null;
  const won = (source.primary?.competitors ?? []).find(
    (competitor) => competitor?.won === true
  );
  return cleanText(won?.name);
}

/**
 * `": "` normally, `" — "` when the event's own name already carries a colon.
 *
 * See the header: combat cards are named "Contender Series: Hunt vs Perea", and
 * the house `<subject>: <leaders>` shape would print two colons in one title.
 */
function separator(name: string): string {
  return name.includes(":") ? " — " : ": ";
}

/** The unfurl copy for one event concept. */
export function buildEventConceptShareCopy(source: EventConceptShareSource): {
  title: string;
  description: string;
} {
  const name = cleanText(source.event?.name) ?? "Event";
  const label = contestLabel(source);
  const where = place(source);
  const sep = separator(name);

  // ── SETTLED, WITH AN AUTHORITATIVE WINNER ──────────────────────────────────
  const winner = flaggedWinner(source);
  if (winner) {
    return {
      title: `${name}${sep}${winner} won`,
      description: truncateShareText(
        label ? `Final: ${winner} won the ${label}.` : `Final: ${winner} won.`
      ),
    };
  }

  // ── SETTLED, AND NOTHING NAMED A WINNER ────────────────────────────────────
  // `/events/[id]`'s last rung. A price here is a forecast on a closed
  // question, which is why it is not printed.
  if (cleanText(source.event?.status)?.toLowerCase() === "settled") {
    return {
      title: `${name}${sep}Final`,
      description: truncateShareText(
        `Final. Bain Luck does not have a confirmed result for ${name} yet.`
      ),
    };
  }

  const priced = pricedCompetitors(source);

  // ── NOTHING PRICED ─────────────────────────────────────────────────────────
  // Say what the page is; claim nothing about who is ahead.
  if (priced.length === 0) {
    return {
      title: name,
      description: truncateShareText(
        where
          ? `${name}, ${where}. Every market on this event, as one clean probability.`
          : `${name}: every market on this event, as one clean probability.`
      ),
    };
  }

  // ── A DUEL: BOTH SIDES NAMED ───────────────────────────────────────────────
  if (priced.length === 2) {
    const [first, second] = priced;
    const line = `${first.name} ${first.probability}, ${second.name} ${second.probability}`;
    const context = [where, label].filter(
      (part): part is string => part !== null
    );
    return {
      title: `${name}${sep}${line}`,
      description: truncateShareText(
        context.length > 0 ? `${context.join(". ")}. ${line}.` : `${line}.`
      ),
    };
  }

  // ── A FIELD: THE LEADER ONLY ───────────────────────────────────────────────
  //
  // The title names the leader without naming what they lead, and the
  // description says it one line below — the same trade `/tournaments/[slug]`
  // makes. Spelling the contest out in the title costs the event's own name,
  // which is the one word a reader needs, and unfurlers truncate a title long
  // before a description.
  const leader = priced[0];
  const sentence = label
    ? `${leader.name} leads the ${label} at ${leader.probability}.`
    : `${leader.name} leads at ${leader.probability}.`;

  return {
    title: `${name}${sep}${leader.name} ${leader.probability}`,
    description: truncateShareText(where ? `${where}. ${sentence}` : sentence),
  };
}
