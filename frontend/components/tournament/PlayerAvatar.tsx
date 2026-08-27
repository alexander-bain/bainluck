"use client";

import React from "react";

import type { PlayerImage } from "@/lib/slate";

/**
 * A player's picture — Alex's ruling 8, and his 2026-08-27 finding on the live
 * page: "Players have no images."
 *
 * ═══ WHY THIS IS NOT `FighterAvatar` ═══
 *
 * The repo already has a person avatar. `components/event/FighterAvatar.tsx`
 * takes a NAME and fires `getWikipediaImage(name)` from the browser. It is the
 * right shape for UFC and it is the wrong shape here, for a reason the census
 * measured rather than guessed:
 *
 *     Bare-name Wikipedia for the tennis player `Aleksandar Kovacevic`
 *     returns a SERBIAN FOOTBALLER. `Andrew Johnson` returns the 17th
 *     President of the United States. Both answer 200, with a photograph,
 *     indistinguishable from success at the render.
 *
 * Seventeen of 378 registered players hit that class. A wrong face is the
 * worst kind of wrong answer on this page: instant, confident, and something
 * the reader cannot check. So the subject is verified ONCE, offline, in
 * `backend/scripts/census_player_images.py` — the article's own description
 * must say tennis — and this component renders the pinned answer. It performs
 * no lookup, holds no state, and cannot resolve a face for the wrong person
 * because it never resolves anything.
 *
 * ═══ THE THREE-STEP FALLBACK, AND WHY THERE IS NO BLANK ═══
 *
 * Alex's gate on ruling 8 was coverage: "enable ONLY if coverage is ~complete
 * per draw — half-covered looks worse than none." Measured 2026-08-27, on the
 * surfaces that actually render:
 *
 *   | surface                     | face        | any image |
 *   |-----------------------------|-------------|-----------|
 *   | men's championship board    | 36/36 100%  | 100%      |
 *   | women's championship board  | 44/44 100%  | 100%      |
 *   | men's main-draw fixtures    | 88/94  94%  | 94/94     |
 *   | women's main-draw fixtures  | 93/98  95%  | 98/98     |
 *
 * ESPN's own tennis headshots were censused first, as the ruling asks, and
 * FAIL it: 40% of the men's draw and 28% of the women's. They are not used.
 *
 * The last 5% get their COUNTRY FLAG, which ESPN carries at 100% on the same
 * record as the name. That is not a consolation prize — a flag beside a
 * player's name is what every draw sheet and every broadcast scoreboard in
 * tennis has printed for fifty years — and it is what makes the column
 * uniform. Initials are the third step and fire only for a player the register
 * has neither for, which is nobody on any main-draw surface today.
 */

/** `Felix Auger-Aliassime` -> `FA`. The last resort, and currently unreached. */
export function initialsOf(name: string): string {
  const parts = (name || "").trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export type AvatarKind = "face" | "flag" | "initials";

/** Which of the three steps a given image block lands on. Pure, so it is testable. */
export function avatarKind(image: PlayerImage | null | undefined): AvatarKind {
  if (image?.url) return "face";
  if (image?.flag_url) return "flag";
  return "initials";
}

export default function PlayerAvatar({
  name,
  image,
  size = 26,
  dim = false,
}: {
  name: string;
  image?: PlayerImage | null;
  /** px diameter. 26 on a match row, 22 in the grid, 30 on the board. */
  size?: number;
  /** A decided match's loser, muted with the rest of their row. */
  dim?: boolean;
}) {
  const kind = avatarKind(image);
  const box = { width: size, height: size };
  const shared = {
    "data-testid": "player-avatar",
    "data-kind": kind,
    "data-entity-name": name,
  };

  if (kind === "initials") {
    return (
      <span
        {...shared}
        style={{ ...box, fontSize: Math.round(size * 0.38) }}
        className={`flex shrink-0 self-center select-none items-center justify-center rounded-full bg-surface-elevated font-semibold text-text-secondary ${
          dim ? "opacity-60" : ""
        }`}
        aria-hidden="true"
      >
        {initialsOf(name)}
      </span>
    );
  }

  const src = kind === "face" ? image!.url! : image!.flag_url!;
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      {...shared}
      src={src}
      alt=""
      aria-hidden="true"
      style={box}
      loading="lazy"
      className={`shrink-0 self-center rounded-full bg-surface-elevated ${
        // A flag is a wide rectangle. `object-cover` on a circle would crop a
        // tricolour to its middle stripe and make France, Italy and Ireland
        // three plain white discs; `object-contain` keeps the whole flag and
        // pads it, which is legible at 22px and correct at any size.
        kind === "face" ? "object-cover" : "object-contain p-px"
      } ${dim ? "opacity-60" : ""}`}
    />
  );
}
