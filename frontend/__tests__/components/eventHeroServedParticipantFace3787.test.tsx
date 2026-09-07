/**
 * #3787 — THE HERO IS THE FOURTH RENDERER OF ONE RULE, AND IT WAS ANSWERING A
 * NARROWER QUESTION THAN THE OTHER THREE.
 *
 * ## What a reader saw
 *
 * `https://bainluck.com/events/15304939` at 390px, production `f1b36c81`,
 * 2026-09-07, during the US Open: the hero drew two grey squares reading `DM`
 * and `FT` for Medvedev and Tiafoe — both of them censused players with real
 * headshots.
 *
 * ## The issue's stated cause was wrong, and the difference matters
 *
 * #3787 was filed saying the hero "has no served-face rung". It has had one
 * since #2447. Measured rather than assumed, live on 2026-09-07:
 *
 *     GET /api/tournaments/by-event/15304939
 *     -> { event_id, tournament, reason: "NOT_IN_REGISTER" }
 *
 * No `result`, no `advancement`. The rung fired and found nothing, because that
 * register is keyed to the BRACKET and this match is not on it. Replaying the
 * NAME-keyed register for the same two strings returns both Wikipedia
 * headshots and both ESPN country flags.
 *
 * So the fix is not a new rung — it is putting the pair the payload ALREADY
 * carries (since #3784 gave `_format_event` the four #2919 keys) in FRONT of
 * the bracket lookup. `NO_REGISTER_BUT_SERVED` below is that exact production
 * shape, and it is the case that would have caught this.
 *
 * ## Both arms, and precedence pinned as an ORDER
 *
 * A hero that drew BOTH the served face and the register face would satisfy two
 * separate presence checks, so the precedence cases assert WHICH src is drawn
 * when the two disagree, not merely that something was drawn.
 */

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

import {
  TournamentPlayerFace,
  servedParticipantImage,
} from "@/components/event/TournamentExtensions";
import type { EventTournamentResponse } from "@/lib/types";

let swrAnswer: { data?: EventTournamentResponse } = {};

jest.mock("swr", () => ({
  __esModule: true,
  default: (key: unknown) => (key === null ? { data: undefined } : swrAnswer),
}));

jest.mock("next/link", () => {
  const ReactLib = require("react");
  return {
    __esModule: true,
    default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) =>
      ReactLib.createElement("a", { href, ...props }, children),
  };
});

/** The two real strings and the two real URLs, replayed from the register. */
const MEDVEDEV = "Daniil Medvedev";
const TIAFOE = "Frances Tiafoe";
const MEDVEDEV_FACE =
  "https://upload.wikimedia.org/wikipedia/commons/thumb/3/30/Danill_Medvedev_Miami_2019_%28cropped%29.jpg/330px-Danill_Medvedev_Miami_2019_%28cropped%29.jpg";
const RUS_FLAG = "https://a.espncdn.com/i/teamlogos/countries/500/rus.png";
const USA_FLAG = "https://a.espncdn.com/i/teamlogos/countries/500/usa.png";
/** A DIFFERENT url, so "which rung won" is decidable rather than inferred. */
const BRACKET_FACE = "https://example.invalid/bracket-photo-not-the-served-one.jpg";

/** The hero's real fallback: the team-logo-then-initials markup it already had. */
const FALLBACK = <span data-testid="hero-fallback">DM</span>;

function renderHero(props: {
  servedImage?: ReturnType<typeof servedParticipantImage>;
  side?: "home" | "away";
  sportKey?: string | null;
}) {
  return renderToStaticMarkup(
    <TournamentPlayerFace
      eventId={15304939}
      sportKey={props.sportKey === undefined ? "tennis_atp_us_open" : props.sportKey}
      homeName={MEDVEDEV}
      awayName={TIAFOE}
      side={props.side ?? "home"}
      size={56}
      servedImage={props.servedImage}
      fallback={FALLBACK}
    />
  );
}

/** The bracket register DOES hold this match — the #2447 shape. */
function withBracket(): EventTournamentResponse {
  return {
    event_id: 15304939,
    result: {
      players: [
        { display_name: MEDVEDEV, image: { url: BRACKET_FACE, flag_url: null } },
      ],
    },
  } as unknown as EventTournamentResponse;
}

beforeEach(() => {
  swrAnswer = {};
});

describe("servedParticipantImage — the pure packer", () => {
  it("returns null when the payload carries neither key (team sport)", () => {
    expect(servedParticipantImage(undefined, undefined)).toBeNull();
  });

  it("returns null when both keys are present and null (looked, no photo)", () => {
    expect(servedParticipantImage(null, null)).toBeNull();
  });

  it("packs a face, leaving flag_url null rather than absent", () => {
    expect(servedParticipantImage(MEDVEDEV_FACE, null)).toEqual({
      url: MEDVEDEV_FACE,
      flag_url: null,
    });
  });

  it("packs a flag-only player — the 5% the census leaves without a face", () => {
    expect(servedParticipantImage(null, RUS_FLAG)).toEqual({
      url: null,
      flag_url: RUS_FLAG,
    });
  });
});

describe("#3787 — the hero draws the served face", () => {
  it("NO_REGISTER_BUT_SERVED: the live 15304939 shape draws a face, not initials", () => {
    // The bracket answers NOT_IN_REGISTER, exactly as production does.
    swrAnswer = { data: { event_id: 15304939, reason: "NOT_IN_REGISTER" } as never };

    const html = renderHero({
      servedImage: servedParticipantImage(MEDVEDEV_FACE, RUS_FLAG),
    });

    expect(html).toContain('data-kind="face"');
    expect(html).toContain(MEDVEDEV_FACE);
    expect(html).not.toContain("hero-fallback");
  });

  it("draws the AWAY side's own pair, not the home side's", () => {
    swrAnswer = { data: { event_id: 15304939, reason: "NOT_IN_REGISTER" } as never };

    const html = renderHero({
      side: "away",
      servedImage: servedParticipantImage(null, USA_FLAG),
    });

    expect(html).toContain(`data-entity-name="${TIAFOE}"`);
    expect(html).toContain(USA_FLAG);
    expect(html).not.toContain(RUS_FLAG);
  });

  it("a served flag with no face draws the FLAG rung", () => {
    swrAnswer = { data: { event_id: 15304939, reason: "NOT_IN_REGISTER" } as never };

    const html = renderHero({ servedImage: servedParticipantImage(null, RUS_FLAG) });

    expect(html).toContain('data-kind="flag"');
    expect(html).toContain(RUS_FLAG);
  });
});

describe("#3787 — precedence is an ORDER, not two presence checks", () => {
  it("the served face WINS over a bracket face that disagrees", () => {
    swrAnswer = { data: withBracket() };

    const html = renderHero({
      servedImage: servedParticipantImage(MEDVEDEV_FACE, null),
    });

    expect(html).toContain(MEDVEDEV_FACE);
    // The whole point: the hero renders ONE avatar, and it is the served one.
    expect(html).not.toContain(BRACKET_FACE);
    expect(html.match(/data-testid="player-avatar"/g)).toHaveLength(1);
  });

  it("#2447 is NOT broken: with no served pair, the bracket register still wins", () => {
    swrAnswer = { data: withBracket() };

    const html = renderHero({ servedImage: null });

    expect(html).toContain(BRACKET_FACE);
    expect(html).not.toContain("hero-fallback");
  });

  it("a served flag still outranks a bracket FACE — one register, one answer", () => {
    // Deliberate and worth pinning: mixing the two registers per-rung is how the
    // hero would end up showing this player's flag and that player's photo.
    swrAnswer = { data: withBracket() };

    const html = renderHero({ servedImage: servedParticipantImage(null, RUS_FLAG) });

    expect(html).toContain('data-kind="flag"');
    expect(html).not.toContain(BRACKET_FACE);
  });
});

describe("#3787 — the fallback ladder is untouched", () => {
  it("a team sport (no served keys, gate closed) renders the existing markup", () => {
    const html = renderHero({ sportKey: "baseball_mlb", servedImage: null });

    expect(html).toContain("hero-fallback");
    expect(html).not.toContain('data-testid="player-avatar"');
  });

  it("a player neither register holds falls through to the fallback", () => {
    swrAnswer = { data: { event_id: 15304939, reason: "NOT_IN_REGISTER" } as never };

    const html = renderHero({ servedImage: servedParticipantImage(null, null) });

    expect(html).toContain("hero-fallback");
  });
});

describe("#3787 — geometry is decided by what is drawn, at the hero's size", () => {
  it("a face is object-cover and a flag is object-contain, both at 56px", () => {
    swrAnswer = { data: { event_id: 15304939, reason: "NOT_IN_REGISTER" } as never };

    const face = renderHero({ servedImage: servedParticipantImage(MEDVEDEV_FACE, null) });
    const flag = renderHero({ servedImage: servedParticipantImage(null, RUS_FLAG) });

    expect(face).toContain("object-cover");
    // A headshot letterboxed into a flag's box is a worse card than initials.
    expect(face).not.toContain("object-contain");
    expect(flag).toContain("object-contain");

    for (const html of [face, flag]) {
      expect(html).toContain("width:56px");
      expect(html).toContain("height:56px");
    }
  });
});
