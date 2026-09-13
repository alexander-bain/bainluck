/**
 * THE COPY A PASTED `/hub/<competition>` LINK UNFURLS WITH (#5877).
 *
 * Pure, so the decision is testable without a browser and without the network:
 * `app/hub/[competition]/layout.tsx` fetches, this module decides, and the two
 * jobs never mix. `lib/tournamentShareMeta.ts` and `lib/eventConceptShareMeta.ts`
 * are the same split for the two routes check 8 fixed before this one.
 *
 * ═══ WHAT WAS ON PRODUCTION BEFORE THIS ═══
 *
 * `app/hub/[competition]/` held one `"use client"` `page.tsx` and no layout, so
 * the route rendered the ROOT metadata verbatim. Measured with a crawler UA at
 * 2026-09-13 09:46:33Z, all five hubs AND a competition that does not exist were
 * byte-identical in metadata (md5 `f72c90da46e788dab512b5c3a1a1732a` across all
 * six):
 *
 *   canonical      https://www.bainluck.com
 *   og:url         https://www.bainluck.com
 *   og:title       Bain Luck — Prediction Market Discovery
 *   twitter:title  Bain Luck — Prediction Market Discovery
 *   robots         index, follow
 *
 * `/hub/mma`, `/hub/boxing`, `/hub/golf`, `/hub/tennis` and `/hub/esports` are
 * hardcoded in BOTH `BottomNav` and `DesktopNav`, so that is five entries on the
 * navigation of every page telling search engines they duplicate the home page.
 *
 * ═══ WHY THIS MODULE IS SHORT, AND WHY THAT IS THE POINT ═══
 *
 * The sibling modules compute: `tournamentShareMeta` ranks board leaders and
 * formats probabilities. There is nothing to compute here, and inventing
 * something would be the defect. `GET /api/hub/{competition}` already serves
 * product-written per-competition copy, and the PAGE ALREADY RENDERS EXACTLY
 * THESE TWO FIELDS — `title` as its `<h1>` and `blurb` as the paragraph under it
 * (`app/hub/[competition]/page.tsx:281-285`). So the share and the page a reader
 * lands on say the same thing, which is the whole contract of an unfurl.
 *
 * This is therefore a client throwing away a good value, not a missing field —
 * the same shape as #5847's team-page league label.
 *
 * ═══ WHAT IT DELIBERATELY DOES NOT DO ═══
 *
 * **No counts, and no "leader" of a hub.** A hub is a COLLECTION — `/hub/tennis`
 * served 98 matches, 66 props, 17 more markets and 1 future on the morning this
 * was written — so there is no single question and no single probability to
 * quote. A title naming one of 182 markets would be arbitrary, and a title
 * naming the count ("98 matches") is a number about our inventory rather than
 * about the world, which is what notice 34 exists to keep off a reader's screen.
 *
 * **No emoji.** The payload carries one and the page renders it, but as
 * `aria-hidden` decoration beside the heading. A share title is read aloud by
 * screen readers and truncated by unfurlers; the competition's name is the part
 * that must survive both.
 */

import { toTitleCaseAcronymSafe } from "@/lib/titleCase";

/** The fields of `GET /api/hub/{competition}` this copy is built from. */
export interface HubShareSource {
  competition?: string | null;
  label?: string | null;
  title?: string | null;
  blurb?: string | null;
}

export interface HubShareCopy {
  /**
   * The `<title>`, WITHOUT a site suffix — the root layout's template is
   * `%s | Bain Luck` and appends one. See `UnresolvedCopy.title` for the bug
   * that taught us to say so.
   */
  title: string;
  description: string;
}

/**
 * The description used when the payload arrived but carried no `blurb`.
 *
 * Generic on purpose: it is true of every hub, names no sport, and claims no
 * inventory. The alternative — dropping `description` entirely — is worse than
 * it looks, because an absent description on a route that declares `openGraph`
 * inherits the ROOT's, and the home page's blurb under a competition's name is
 * the defect this ship exists to remove, one field over.
 */
const FALLBACK_BLURB =
  "Every market in this competition, translated into plain probabilities.";

function cleanText(value: string | null | undefined): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

/**
 * The share copy for a hub that RESOLVED.
 *
 * The title falls back through the payload's own two names before it derives
 * one, and each step is a real field rather than a guess:
 *
 *   `title`        "Mixed Martial Arts" — the long name, what the `<h1>` shows.
 *   `label`        "MMA" — the short name, what the nav shows.
 *   `competition`  the payload's own key, title-cased.
 *   the segment    the URL the reader actually pasted.
 *
 * The last step is why this takes `requested` at all. A 200 whose body is `{}`
 * is not a 404 — we must not tell a crawler the hub is absent — but neither may
 * the card fall silent and inherit the home page's title, which is precisely
 * the bug. Naming the requested segment is the honest floor: it is what the
 * reader asked for, and it is never empty.
 */
export function buildHubShareCopy(
  source: HubShareSource | null | undefined,
  requested: string
): HubShareCopy {
  const payload = source ?? {};

  const name =
    cleanText(payload.title) ??
    cleanText(payload.label) ??
    cleanText(toTitleCaseAcronymSafe(cleanText(payload.competition) ?? "")) ??
    cleanText(toTitleCaseAcronymSafe(requested)) ??
    requested;

  return {
    title: name,
    description: cleanText(payload.blurb) ?? FALLBACK_BLURB,
  };
}
