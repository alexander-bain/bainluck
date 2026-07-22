# CLAUDE DESIGN PROMPT — Bain Luck Team Page v2 (paste everything below into Claude Design)

Design a TEAM PAGE for Bain Luck, a probability-first sports/prediction discovery site (bainluck.com). Light mode only. Clean, Kalshi-minimal chrome. The design system: white cards on #fafafa, near-black text, one accent. Reference feel: the polish of Kalshi, the data density of DataGolf, the warmth of a team's identity.

THE THESIS (governs everything): probability IS the content. Never show a bare score or time where a probability can add meaning. No betting odds formats ever (no -150/+130) — percentages only.

PAGE: Boston Red Sox (use as the concrete example; design generalizes to any MLB/NBA/NFL/NHL team).

STRUCTURE (top to bottom):
1. TEAM HERO — logo, name, record (13-15), with the TEAM'S PRIMARY COLOR as the page accent (left border rail, section markers, chart line color). Alongside: the team's headline number — World Series odds (4%) with 24h delta — because the team's "price" is its identity here.
2. TODAY/NEXT — if a game is live: a live strip (score + live win probability, prominent). Doubleheaders show BOTH games distinctly (G1/G2 chips). Upcoming games as probability-first cards: opponent logo, date/time, AND the current win probability split (e.g. 62/38) — the number is the star, the time is metadata.
3. RECENT RESULTS as "expected vs happened": each card = result + what the market expected ("W 6-1 — we had them at 72%"). Upsets get a subtle flag ("beat 78% odds"). This grammar (expectation → outcome) is the site's signature.
4. SEASON JOURNEY — one chart: the team's championship (or playoff) probability over the season as a single line in team color, fixed 0-100% axis, NO smoothing (straight segments), key moments optionally annotated (trade deadline, streaks). This is the team's year as one picture.
5. DIVISION RACE — a compact grid: the 4-5 division rivals × (Division %, Playoffs %, Championship %), sortable, this team's row highlighted in team color. At-a-glance "where do we stand."
6. SEASON FUTURES — the existing list (division/conference/championship/props with rank-in-league chips) but visually grouped: Championship path (division→pennant→WS) as a connected progression, props separate.

MOBILE-FIRST: design the phone layout primarily (this is a phone product), desktop as the enhancement. Cards stack; the division grid scrolls horizontally if needed; the live strip is sticky-adjacent.

DO NOT: dark mode, betting odds formats, smoothed/curved chart lines, auto-scaled probability axes, internal taxonomy chips (no "Tier 1", "EI", "competitive"), infinite sections — the page should END cleanly.

Deliver: full page mockup (mobile + desktop), the probability-first game card as a reusable component spec, the division-race grid component, and the season-journey chart treatment.
