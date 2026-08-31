/**
 * WHAT THE HEADING OVER THE HUB `upcoming` RAIL IS ALLOWED TO SAY.
 *
 * ── THE DEFECT THIS EXISTS TO END (UX-P210, repairing CERT-525) ──────────────
 *
 * UX-P209 stopped a hub card claiming a phase nobody had established: the
 * tennis lister emits `unknown` when it has no trustworthy start signal, and
 * `HubStatusPill` renders no pill for it. CERT-525 found the same claim one
 * level up, untouched:
 *
 *   > Unknown tennis cards lose the per-card Upcoming pill but remain directly
 *   > beneath the visible `Upcoming Tournaments` heading, so the hub still
 *   > makes the same unsupported phase claim one level up.
 *
 * A heading is a claim about every card underneath it. "Upcoming Tournaments"
 * over the live US Open is the same sentence the pill was blocked for saying,
 * printed once instead of eight times. Silencing the pill and leaving the
 * heading is not a repair — it is the claim relocated.
 *
 * ── THE RULE ─────────────────────────────────────────────────────────────────
 *
 * The affirmative heading is licensed only when EVERY card on the rail is
 * `upcoming`. Anything else — one `live` card, one `settled` card, one
 * `unknown` card — and the rail is named by its noun with no WHEN attached:
 * "Tournaments", "Cards". The cards keep their names, dates, links and pills;
 * the section stops asserting a phase on their behalf.
 *
 * Note this is broader than the `unknown` case the cert names, deliberately.
 * Every hub lister (`list_ufc_card_concepts`, `list_boxing_card_concepts`,
 * `list_golf_tournament_concepts`, `list_tennis_tournament_concepts`) admits
 * `live` in its default `statuses`, so "Upcoming Cards" over a live UFC card is
 * the identical false claim reachable on four hubs today. A rule keyed only on
 * `unknown` would knowingly leave that standing, which is the mistake CERT-519
 * blocked in the first place: fixing the arm you were asked about and leaving
 * the one beside it.
 *
 * ── WHY THE CLIENT DECIDES AND THE SERVER ONLY SUPPLIES WORDS ────────────────
 *
 * The rail's composition is only known once the cards are in hand, and this is
 * what renders the claim. If the backend picked the heading, this file would
 * print whatever it was handed — and the render guard the cert asked for would
 * prove nothing except that the page is obedient. So `HubConfig` declares both
 * words (`upcoming_label`, `upcoming_label_neutral`) and the choice is made
 * here, against the cards actually being rendered.
 *
 * ── EVERY FAILURE PATH LANDS ON A TRUE WORD, NEVER ON THE PHASE ──────────────
 *
 * Two ways this can be left without a usable neutral word:
 *
 *   1. A payload served before this shipped. The hub mirror lives up to 24h, so
 *      for one day after deploy some payloads carry `upcoming_label` and no
 *      neutral twin. Falling back to the affirmative label would reinstate the
 *      defect for exactly the population a deploy cannot reach.
 *   2. A neutral label that itself contains a phase word — a config typo, or a
 *      hub added later by copy-paste. The backend refuses this too
 *      (`TestHubNeutralUpcomingLabel`), and the two checks are deliberately
 *      independent rather than a shared contract, so a mistake at either end is
 *      absorbed instead of rendered.
 *
 * Both land on `NEUTRAL_LABEL_FALLBACK`. The first draft of this file returned
 * null — no heading — on the reasoning that silence is never a lie. It is not,
 * but it is not the only thing that is not: "Events" is TRUE of every rail on
 * every hub, and unlike the phase word it is a claim the payload can support
 * without knowing anything about when. Withholding is the right answer when the
 * alternative is a false statement (that is why the pill withholds); here a true
 * statement is available, so the section keeps its heading. It is also the
 * backend dataclass default for `upcoming_label_neutral`, so a hub that declares
 * nothing reads the same word from either end.
 *
 * The invariant that survives all four paths, and the one the guards pin: the
 * heading asserts a phase ONLY when every card on the rail is in it.
 */

/** The one status that licenses the affirmative heading. */
export const HEADING_AFFIRMATIVE_STATUS = "upcoming";

/** Used when the payload declares no label and the rail is genuinely upcoming. */
export const UPCOMING_LABEL_FALLBACK = "Upcoming";

/**
 * Used when the rail is NOT all upcoming and no usable neutral word was served.
 * True of every hub rail, and carries no phase — mirrors the backend's
 * `HubConfig.upcoming_label_neutral` default.
 */
export const NEUTRAL_LABEL_FALLBACK = "Events";

/**
 * Words that say WHEN. A neutral label may contain none of them.
 *
 * Mirrors `TestHubNeutralUpcomingLabel.PHASE_WORDS`. Kept as a local defence
 * rather than a served contract on purpose — see failure path 2 above.
 */
export const HEADING_PHASE_WORDS = [
  "upcoming",
  "live",
  "final",
  "settled",
  "soon",
  "next",
  "today",
] as const;

export function containsPhaseWord(text: string): boolean {
  const low = text.toLowerCase();
  return HEADING_PHASE_WORDS.some((w) => low.includes(w));
}

export interface HeadingCard {
  status: string;
}

export interface HubUpcomingLabels {
  /** The affirmative heading, e.g. "Upcoming Tournaments". */
  label?: string | null;
  /** The same heading with no phase claim, e.g. "Tournaments". */
  neutralLabel?: string | null;
}

/**
 * The heading to print over `cards`, or `null` for no heading.
 *
 * @param cards the cards this heading will actually sit above — not the
 *   payload's full rail, the rendered slice, so a cap or a filter upstream
 *   cannot leave the heading describing cards nobody can see.
 */
export function hubUpcomingHeading(
  cards: readonly HeadingCard[],
  labels: HubUpcomingLabels,
): string | null {
  // No cards, nothing to name. The rail does not render in this state; being
  // explicit keeps the helper total rather than relying on its caller's guard.
  if (!cards.length) return null;

  const everyCardIsUpcoming = cards.every(
    (c) => c.status === HEADING_AFFIRMATIVE_STATUS,
  );
  if (everyCardIsUpcoming) {
    return labels.label || UPCOMING_LABEL_FALLBACK;
  }

  const neutral = labels.neutralLabel;
  if (!neutral || containsPhaseWord(neutral)) return NEUTRAL_LABEL_FALLBACK;
  return neutral;
}
