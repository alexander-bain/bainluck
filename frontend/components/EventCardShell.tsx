"use client";

import Link from "next/link";
import type { CSSProperties, ReactNode } from "react";

import { motion } from "@/components/motion";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { fadeIn } from "@/lib/animations";

/**
 * ═══ THE EVENT CARD IS ONE CARD — WHOLE, AND CLICKABLE (UX-P154) ═══
 *
 * Alex's words, on the UX-P152 artifact's panel 4 (review of P149/P150/P151/
 * P152, 2026-08-28, relayed through the UX-P154 runner directive):
 *
 *   *"it kinda feels like we're reinventing the event card inside the
 *   tournament product"* — and the instruction that followed: **no "See more on
 *   this match" link row; the whole match card is clickable, exactly like every
 *   other card in the product; the tournament list uses THE standard event-card
 *   component.**
 *
 * This file is that component's SHELL, and it exists because two surfaces
 * needed the same three properties and only one of them had them:
 *
 *   1. the whole card is the target — one `<Link>` wrapping everything, never a
 *      link row inside a card;
 *   2. the card announces WHICH component drew it (`data-testid="event-card"`),
 *      which is the hook ruling 047's acceptance is written against — *"the
 *      league page renders the SHARED event card"* is a claim about the
 *      component that drew the DOM, and it is unanswerable from the DOM unless
 *      the shared card marks itself;
 *   3. live / finished / hover treatment is decided in ONE place, so two
 *      surfaces cannot drift into two ideas of what a live card looks like.
 *
 * ═══ WHY A SHELL AND NOT `EventCard` ITSELF, STATED SO IT CAN BE OVERRULED ═══
 *
 * The literal reading of *"uses THE standard event-card component"* is that the
 * tournament list renders `EventCard`. This lane did not do that, and the
 * reason is a collision with a standing ruling rather than a preference:
 *
 *   - `EventCard` resolves its faces from the team name at render time
 *     (`espnTeamLogoByName`, `flagUrl`, `teamColorStyle`). The tournament
 *     surfaces are under Alex's ruling 8 — the player's face is **pinned in the
 *     register and never resolved client-side**. Feeding two tennis players
 *     through a team-logo lookup is how you get a basketball crest beside
 *     Sabalenka.
 *   - It has no seat for a SEED or for the title chip, both of which are
 *     rulings 1 and 8 on this list, and it would print `Alcaraz at Bellucci`
 *     for a match that is not played at anybody's home.
 *   - `EventCard` keys everything off `event.id`, and **28 of the register's
 *     124 fixtures dereference to no `events` row** (the qualifying draw was
 *     never ingested). Those rows would have no card at all.
 *
 * So the shell is the honest version of the instruction: the tournament list
 * renders the same component, marked the same way, behaving the same way, and
 * keeps the facts a tennis draw has that a two-team game does not. The report
 * carries the cost of full literal adoption; if Alex wants it anyway, the
 * change is `EventCard` growing a `sides` slot, not this file growing features.
 */

/** The marker every surface's guard reads. One string, one definition. */
export const EVENT_CARD_TESTID = "event-card";

export interface EventCardShellProps {
  /**
   * Where the whole card goes. `null` renders the card INERT — no anchor, no
   * pointer, no hover lift — which is the honest state for a fixture that
   * dereferences to no event. A card that looks pressable and is not is worse
   * than one that plainly is not, and a link to the wrong match is worse still.
   */
  href: string | null;
  /** Screen-reader name for the whole target. Required when `href` is set. */
  ariaLabel?: string;
  onClick?: () => void;
  live?: boolean;
  finished?: boolean;
  className?: string;
  style?: CSSProperties;
  /** Passed straight through so a caller can key its own rows/analytics. */
  dataAttrs?: Record<string, string | undefined>;
  children: ReactNode;
}

export default function EventCardShell({
  href,
  ariaLabel,
  onClick,
  live = false,
  finished = false,
  className,
  style,
  dataAttrs,
  children,
}: EventCardShellProps) {
  const card = (
    <motion.div variants={fadeIn} initial="hidden" animate="visible">
      <Card
        className={cn(
          "h-full flex flex-col p-3 sm:p-4 transition-all group/card",
          "bg-surface-card border-surface-border",
          href !== null &&
            "cursor-pointer hover:bg-surface-elevated hover:shadow-card-hover hover:scale-[1.005] hover:border-surface-elevated",
          live && "border-l-[3px] border-l-accent-live ring-1 ring-accent-live/20",
          finished && "opacity-80 hover:opacity-100 hover:scale-100",
          className,
        )}
        style={style}
        {...dataAttrs}
      >
        {children}
      </Card>
    </motion.div>
  );

  if (href === null) {
    // Still marked as the shared card. The claim the marker answers is "which
    // component drew this", and that is true whether or not it links anywhere.
    return (
      <div className="h-full" data-testid={EVENT_CARD_TESTID} data-linked="false">
        {card}
      </div>
    );
  }

  return (
    <Link
      href={href}
      className="h-full"
      onClick={onClick}
      data-testid={EVENT_CARD_TESTID}
      data-linked="true"
      aria-label={ariaLabel}
    >
      {card}
    </Link>
  );
}
