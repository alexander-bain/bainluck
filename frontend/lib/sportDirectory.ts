// #7015 — how a sport is presented on the top-level `/sport` directory.
//
// This register used to be two hand-typed maps inside `app/sport/page.tsx`.
// They held eight keys while `GET /api/sports/hierarchy` served eleven, and the
// render site fell through silently — `|| { icon: "🏆", description: "" }` — so
// Boxing, Motorsports and Esports were dressed as placeholders: one trophy for
// three sports on one screen, a grey card, and a subtitle of "1 leagues".
//
// Living in `lib/` is the point, not tidiness. `app/sport/page.tsx` is a client
// component that loads through `useEffect`, so a guard test cannot reach the
// mapping where it used to live; here it is a pure function, and
// `__tests__/sportDirectoryNamesEverySport7015.test.ts` reads the authority
// (`backend/app/utils/sport_keys.py`) and proves every sport it serves resolves
// to a real icon. Adding a twelfth sport there fails that test instead of
// shipping a trophy.
//
// The authority does not serve icons or tints, so they are declared here rather
// than derived. That is a deliberate stop: teaching the API to carry display
// copy is a backend contract change, and the test above already catches the
// drift that made this a defect.

export interface SportCardPresentation {
  icon: string;
  /** The grey line under the sport name. Never a bare count for a known sport. */
  subtitle: string;
  tintClass: string;
  /** True only when the sport is unknown to this register. */
  isFallback: boolean;
}

/**
 * Shown for a sport the register has never heard of. It exists so an unknown
 * sport still renders a usable card rather than a blank or a crash — the
 * failure this file documents was not the fallback firing, it was the fallback
 * firing *silently* for three sports that should never have reached it.
 */
export const FALLBACK_SPORT_ICON = "\u{1F3C6}";
export const FALLBACK_SPORT_TINT = "bg-surface-elevated hover:bg-surface-card";

interface SportDirectoryEntry {
  icon: string;
  /** Empty falls through to the league count — pluralized. */
  description: string;
  tint: string;
}

// Every icon here is distinct, and a test pins that. The directory's whole job
// is to tell eleven sports apart, so two sports wearing one glyph is the same
// defect as three wearing the trophy. That constraint is why MMA reads 🥋 and
// not 🥊: the two cards are adjacent at 390px, and the glove belongs to Boxing.
const SPORT_DIRECTORY: Record<string, SportDirectoryEntry> = {
  golf: {
    icon: "⛳",
    description: "PGA Tour, DP World Tour, LPGA, LIV & more",
    tint: "bg-emerald-50 hover:bg-emerald-100",
  },
  basketball: {
    icon: "🏀",
    description: "NBA, WNBA, NCAA Men’s & Women’s",
    tint: "bg-orange-50 hover:bg-orange-100",
  },
  football: {
    icon: "🏈",
    description: "NFL, NCAA Football, CFL, UFL",
    tint: "bg-green-50 hover:bg-green-100",
  },
  hockey: {
    icon: "🏒",
    description: "NHL",
    tint: "bg-sky-50 hover:bg-sky-100",
  },
  baseball: {
    icon: "⚾",
    description: "MLB, College Baseball",
    tint: "bg-red-50 hover:bg-red-100",
  },
  soccer: {
    icon: "⚽",
    description: "Premier League, La Liga, MLS, Champions League & more",
    tint: "bg-purple-50 hover:bg-purple-100",
  },
  tennis: {
    icon: "🎾",
    description: "ATP Tour, WTA Tour",
    tint: "bg-lime-50 hover:bg-lime-100",
  },
  mma: {
    icon: "🥋",
    description: "UFC",
    tint: "bg-rose-50 hover:bg-rose-100",
  },
  boxing: {
    icon: "🥊",
    description: "Title fights & marquee bouts",
    tint: "bg-amber-50 hover:bg-amber-100",
  },
  motorsports: {
    icon: "🏎️",
    description: "Formula 1, NASCAR",
    tint: "bg-blue-50 hover:bg-blue-100",
  },
  esports: {
    icon: "🎮",
    description: "League of Legends, Counter-Strike 2, Valorant",
    tint: "bg-indigo-50 hover:bg-indigo-100",
  },
};

/**
 * "1 league", "2 leagues", "0 leagues". The child route
 * (`app/sport/[sport]/page.tsx`) has pluralized since it was written; the
 * directory above it printed "1 leagues" on the Boxing card.
 */
export function leagueCountLabel(leagueCount: number): string {
  return `${leagueCount} league${leagueCount === 1 ? "" : "s"}`;
}

export function resolveSportCard(
  slug: string,
  leagueCount: number,
): SportCardPresentation {
  const entry = SPORT_DIRECTORY[slug];
  if (!entry) {
    return {
      icon: FALLBACK_SPORT_ICON,
      subtitle: leagueCountLabel(leagueCount),
      tintClass: FALLBACK_SPORT_TINT,
      isFallback: true,
    };
  }
  return {
    icon: entry.icon,
    subtitle: entry.description || leagueCountLabel(leagueCount),
    tintClass: entry.tint,
    isFallback: false,
  };
}

/** Every sport slug this register presents. Test-facing. */
export function directorySportSlugs(): string[] {
  return Object.keys(SPORT_DIRECTORY);
}
