/**
 * #5603 / #2602 (Brief18, codex 2026-09-17 19:07Z) — A CONCEPT CARD STOPS
 * NAMING A PROMOTION THE EVENT HAS NOTHING TO DO WITH.
 *
 * ═══ THE DEFECT, MEASURED ON PRODUCTION 2026-09-17 19:52Z ═══
 *
 * `GET /api/feed?limit=150` (and `&mode=sports`, the same eight):
 *
 *   domain   sport_label   name
 *   'ufc'    absent        331: Van vs Pantoja
 *   'ufc'    absent        **Power Slap 23**
 *   'ufc'    absent        Natalia Silva vs Wang Cong
 *   'ufc'    absent        Darren Till vs Yoel Romero
 *   'ufc'    absent        Paddy Pimblett vs Conor McGregor
 *   'ufc'    absent        Islam Makhachev vs Kamaru Usman
 *   'ufc'    absent        Benoit Saint-Denis vs Paddy Pimblett
 *   'ufc'    absent        Alex Volkanovski vs Movsar Evloev
 *
 * 8 of 8 concept cards on the wire carry `domain: "ufc"` and no `sport_label`,
 * and both renderers printed `data.domain.toUpperCase()`. So a SLAP-FIGHTING
 * card wore a `UFC` chip, and "known other combat promotion must not be
 * mislabeled UFC/MMA just because it uses this adapter" (codex) was being
 * violated by the one line that decides the chip.
 *
 * `domain` is not a claim about the sport, it is the event-key namespace we
 * ROUTE on, and `UFC_CONFIG` (`backend/app/utils/event_ufc.py`) states its
 * width: schedule keys `mma_ufc` AND `mma_mixed_martial_arts`, plus every
 * `KXUFC*` Kalshi ticker. The adapter is named after its biggest tenant.
 *
 * ═══ WHY THE CAMERA CANNOT SEE THIS AND A RENDER CAN ═══
 *
 * These cards sit at feed indices 115-144. A whole-page `look.sh` of
 * `/discover` at 390px grows to 16,373px — about 39 cards — and the capture is
 * bounded at two growths by design, so the chip is structurally out of camera
 * reach on production. `/sport/mma` is a league index and renders no concept
 * card at all (shot this session). The evidence for this ship is therefore the
 * rendered output of both real components fed the REAL production payloads
 * below — not a screenshot, and the reason is measured rather than shrugged.
 *
 * ═══ THE FALLBACK IS THE FIX, WHICH IS WHY IT HAS ITS OWN ARMS ═══
 *
 * The obvious consumer shape, `sport_label || domain`, is the defect again for
 * every payload that lacks the field — i.e. every card served today, plus every
 * envelope already sitting in a CDN or a client cache after the backend half
 * ships. Codex named this exact trap. So the arms below pin the SILENCE, not
 * just the happy path, and `blank` is tested separately from `absent` because
 * `||` treats them differently and a chip of spaces is worse than either label.
 *
 * TWO RENDERERS, ONE RULE. `discover/ConceptCard` (Discover) and `FeedCard`'s
 * concept branch (Sports) both printed the token and both now call the one
 * helper — the arrangement `formatConceptMovement` is already in, for the
 * reason its own header gives. A rule fixed on one of these two surfaces is
 * #1935, #1939 and #1951 in turn.
 */
import { renderToStaticMarkup } from "react-dom/server";
import { ConceptCard } from "@/components/discover/ConceptCard";
import FeedCard from "@/components/FeedCard";
import { AnalyticsProvider } from "@/components/Analytics";
import { conceptDomainLabel } from "@/components/discover/utils";
import type { FeedConceptData, FeedItem } from "@/lib/types";

/**
 * What a READER sees: tags dropped, and every attribute value dropped with
 * them. Asserting a bare word against raw markup is how ux/1301 passed a chip
 * for a CSS width — here the trap is live and specific, because `data.domain`
 * reaches `category: data.domain` on FeedCard's analytics props and the card's
 * own `href` is `/event/ufc/...`. Both legitimately contain "ufc" after the
 * fix; neither is the chip.
 */
function visibleText(html: string): string {
  return html
    .replace(/<[^>]*>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** The Power Slap card exactly as production served it, 2026-09-17 19:52Z. */
const POWER_SLAP: FeedConceptData = {
  key: "event:ufc:26sep18powerslap23",
  name: "Power Slap 23",
  domain: "ufc",
  status: "upcoming",
  is_major: false,
  fight_count: 6,
  leader: { name: "Vasilii Kamotskii", probability: 0.62, field_size: 2 },
};

const conceptItem = (data: FeedConceptData): FeedItem =>
  ({ type: "concept", data }) as unknown as FeedItem;

const renderDiscover = (data: FeedConceptData) =>
  visibleText(
    renderToStaticMarkup(
      <ConceptCard data={data} liked={false} setLiked={() => {}} />,
    ),
  );

/**
 * The REAL `AnalyticsProvider` — the one `app/layout.tsx` wraps the page in —
 * rather than a stubbed hook, so what renders is what ships. `FeedCard`'s
 * concept branch calls `useAnalyticsContext`, which throws outside it.
 */
const renderSports = (data: FeedConceptData) =>
  visibleText(
    renderToStaticMarkup(
      <AnalyticsProvider>
        <FeedCard item={conceptItem(data)} />
      </AnalyticsProvider>,
    ),
  );

describe("#5603 — the rule", () => {
  it("withholds UFC from the mixed combat namespace when the server sent no evidence", () => {
    expect(conceptDomainLabel(undefined, "ufc")).toBe("COMBAT");
    expect(conceptDomainLabel(null, "ufc")).toBe("COMBAT");
  });

  it("withholds it for a BLANK label too — the cached-envelope case, and never renders an empty chip", () => {
    // `""` and `"  "` part company under `||`; both are "the server said
    // nothing" and neither may print a chip with no word in it.
    expect(conceptDomainLabel("", "ufc")).toBe("COMBAT");
    expect(conceptDomainLabel("   ", "ufc")).toBe("COMBAT");
    expect(conceptDomainLabel("   ", "cycling")).toBe("CYCLING");
  });

  it("prints the server's label verbatim when there IS evidence — including UFC", () => {
    // The ship withholds an unevidenced claim; it does not refuse a true one.
    expect(conceptDomainLabel("UFC", "ufc")).toBe("UFC");
    expect(conceptDomainLabel("MMA", "ufc")).toBe("MMA");
    expect(conceptDomainLabel("Power Slap", "ufc")).toBe("POWER SLAP");
    // A label trailing whitespace is still evidence.
    expect(conceptDomainLabel(" ufc ", "ufc")).toBe("UFC");
  });

  it("is SCOPED to the one mixed namespace — every other domain keeps its own name", () => {
    // Widening the set would spend truthful labels to fix an untruthful one.
    // `boxing` is its own adapter (`event_boxing.py`, domain="boxing") and its
    // own sport, so BOXING is a fact, not a routing artefact.
    expect(conceptDomainLabel(undefined, "boxing")).toBe("BOXING");
    expect(conceptDomainLabel(undefined, "cycling")).toBe("CYCLING");
    expect(conceptDomainLabel(undefined, "f1")).toBe("F1");
    expect(conceptDomainLabel(undefined, "motorsports")).toBe("MOTORSPORTS");
    // The pre-existing empty-domain fallback is unchanged.
    expect(conceptDomainLabel(undefined, "")).toBe("EVENT");
    expect(conceptDomainLabel(undefined, undefined)).toBe("EVENT");
  });

  it("is case-insensitive about the routing token, which is not normalised anywhere upstream", () => {
    expect(conceptDomainLabel(undefined, "UFC")).toBe("COMBAT");
    expect(conceptDomainLabel(undefined, " Ufc ")).toBe("COMBAT");
  });
});

describe("#5603 — the wiring, on both concept renderers", () => {
  // Wiring needs its own arms: the rule above stays green under a revert of
  // either call site, and there are two of them (ux/1315's mutant C — a
  // presentation decision the value arm cannot see).

  it("Discover: Power Slap 23 no longer says UFC", () => {
    const text = renderDiscover(POWER_SLAP);
    expect(text).toContain("COMBAT");
    expect(text).not.toContain("UFC");
    // The chip is the only thing that changed — the card still names the event.
    expect(text).toContain("Power Slap 23");
  });

  it("Sports: Power Slap 23 no longer says UFC", () => {
    const text = renderSports(POWER_SLAP);
    expect(text).toContain("COMBAT");
    expect(text).not.toContain("UFC");
    expect(text).toContain("Power Slap 23");
  });

  it("both renderers print the server's label once the backend half ships", () => {
    const evidenced = { ...POWER_SLAP, sport_label: "Power Slap" };
    for (const text of [renderDiscover(evidenced), renderSports(evidenced)]) {
      expect(text).toContain("POWER SLAP");
      expect(text).not.toContain("COMBAT");
    }
  });

  it("a real UFC card gets UFC back the instant the server says so", () => {
    // The control that fails a fix written as "never print UFC".
    const ufc: FeedConceptData = {
      ...POWER_SLAP,
      key: "event:ufc:26sep19",
      name: "331: Van vs Pantoja",
      sport_label: "UFC",
    };
    for (const text of [renderDiscover(ufc), renderSports(ufc)]) {
      expect(text).toContain("UFC");
      expect(text).not.toContain("COMBAT");
    }
  });

  it("a non-combat concept is untouched on both surfaces", () => {
    // The blast-radius control. `cycling` is the domain the OTHER concept
    // defect on this card (UX-1052 item 1) was measured on.
    const vuelta: FeedConceptData = {
      ...POWER_SLAP,
      key: "event:cycling:vuelta-2026",
      name: "Vuelta a España 2026",
      domain: "cycling",
      leader: { name: "Jonas Vingegaard", probability: 0.44, field_size: 30 },
    };
    for (const text of [renderDiscover(vuelta), renderSports(vuelta)]) {
      expect(text).toContain("CYCLING");
      expect(text).not.toContain("COMBAT");
    }
  });
});
