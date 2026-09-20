/**
 * #7446 — By Source's caption may not promise a panel the section does not draw.
 *
 * THE DEFECT, AS A READER MET IT
 *
 * `/calibration` at 390px, default cohort, production 2026-09-20: the By Source
 * section printed
 *
 *     "One panel per data provider, all on the same 0–100% axis."
 *
 * and then drew THREE panels. The payload publishes four providers; DataGolf's
 * rows are all `price_moved: false`, so the default cohort empties it and
 * `buildProviderPanels` drops it — correctly, there is no curve to draw.
 *
 * The sentence naming that absence exists (`withheldSourcesNote`, UX-P128) but
 * #4340 moved it, with every other sentence in the section, one click away into
 * the `How these panels are drawn` fold. That was right under notice 34. What
 * it left behind was a UNIVERSAL in the page body whose only exception was
 * behind a summary — so the page's plain-view claim was false, and the
 * correction was optional reading.
 *
 * WHAT THESE TESTS PIN
 *
 * Not the wording. The PAIRING: the caption qualifies its promise exactly when
 * a provider is withheld, on the same derivation the note and the section's
 * `data-withheld-sources` attribute already use. A future edit can reword the
 * caption freely; it cannot make it promise four panels and draw three.
 *
 * The specimen is production's, carried over from `calibrationSourceRows.test`
 * so both files argue with the same payload.
 */
import {
  bySourceCaption,
  orderSourceRows,
  sourceRowsExcludedFromRollup,
  withheldSourcesNote,
  type SourceRowInput,
} from "@/lib/calibrationSourceRows";
import { buildProviderPanels } from "@/lib/calibrationProviderPanels";
import { providerLabel } from "@/lib/calibrationProviders";

const labelFor = (provider: string) => providerLabel(provider);

/** Two-sided, so nothing here is censored by accident. */
const twoSided = (n: number, winRate: number) => [{ n, winners: Math.round(n * winRate) }];

/**
 * The four providers `/api/calibration` published, as the DEFAULT (traded)
 * cohort leaves them. DataGolf's `n: 0` is the cohort emptying it, not an
 * absent source — the distinction this whole module exists to keep.
 */
const LIVE: SourceRowInput[] = [
  { provider: "kalshi", label: labelFor("kalshi"), sources: ["kalshi"], n: 214622, ece: 0.9, mce: 1.2, brier: 0.1527, buckets: twoSided(214622, 0.375) },
  {
    provider: "odds_api_family",
    label: labelFor("odds_api_family"),
    sources: ["odds_api", "odds_api_bookmaker", "odds_api_spreads", "odds_api_totals"],
    n: 155127, ece: 1.1, mce: 1.5, brier: 0.2206, buckets: twoSided(155127, 0.557),
  },
  { provider: "polymarket", label: labelFor("polymarket"), sources: ["polymarket"], n: 79278, ece: 2.7, mce: 2.6, brier: 0.1539, buckets: twoSided(79278, 0.344) },
  { provider: "datagolf", label: labelFor("datagolf"), sources: ["datagolf"], n: 0, ece: 0, mce: 0, brier: 0, buckets: [] },
];

/** The same rows, as By Source builds its panels from them. */
const panelsFor = (rows: SourceRowInput[]) =>
  buildProviderPanels(
    rows.map(r => ({
      provider: r.provider,
      label: r.label,
      sources: r.sources,
      // A `PanelBucket` is a `SourceRowBucket` plus the curve's `error` (#7411).
      // Supplied as 0 and copied rather than cast: these assertions are about
      // WHICH panels get built, and that decision reads `n` alone — the ECEs
      // the panels publish come from `pooledEce`/`publishedEce` below, not from
      // this field. Nothing here mutates the shared specimen.
      buckets: r.buckets.map(b => ({ ...b, error: 0 })),
      pooledEce: r.ece,
      publishedEce: r.ece,
    }))
  );

const UNQUALIFIED = "One panel per data provider,";

describe("#7446 — the caption cannot outrun the panels", () => {
  it("does not promise one panel per provider when the cohort withheld one", () => {
    // The defect, stated as arithmetic rather than as a string: four providers
    // in, three panels drawn.
    expect(LIVE).toHaveLength(4);
    expect(panelsFor(LIVE)).toHaveLength(3);

    const caption = bySourceCaption(orderSourceRows(LIVE));
    expect(caption.startsWith(UNQUALIFIED)).toBe(false);
    expect(caption).toContain("with outcomes in this cohort");
  });

  it("keeps the plain promise when every provider is drawn", () => {
    const allMeasured = LIVE.filter(r => r.provider !== "datagolf");
    expect(panelsFor(allMeasured)).toHaveLength(allMeasured.length);

    // Byte-exact, so a silent reword of the good case is a failure too — this
    // is the sentence that was correct all along and must survive the fix.
    expect(bySourceCaption(orderSourceRows(allMeasured))).toBe(
      "One panel per data provider, all on the same 0–100% axis. " +
        "Tap any point for example outcomes, or a provider tab for the full-width view."
    );
  });

  it("qualifies exactly when By Source owes a withheld-source sentence", () => {
    // THE PAIRING. Not "both mention DataGolf" — that passes on two unrelated
    // strings. The caption's qualification and the note's existence are driven
    // off one predicate, so they cannot disagree about whether anything is
    // missing.
    for (const rows of [LIVE, LIVE.filter(r => r.provider !== "datagolf")]) {
      const ordered = orderSourceRows(rows);
      const owesNote = withheldSourcesNote(ordered, "Include untraded") !== null;
      const qualified = !bySourceCaption(ordered).startsWith(UNQUALIFIED);
      expect(qualified).toBe(owesNote);
      // …and both agree with what the section actually drew.
      expect(owesNote).toBe(panelsFor(rows).length < rows.length);
    }
  });

  it("keeps the promise for a censored provider, which still gets a panel", () => {
    // #7411: a one-sided population withholds the ECE but still draws a curve.
    // Qualifying the caption for it would be a second, different falsehood —
    // telling a reader a panel is missing when it is on the screen.
    const censored: SourceRowInput = {
      provider: "datagolf", label: labelFor("datagolf"), sources: ["datagolf"],
      n: 36, ece: 36.5, mce: 36.5, brier: 0.4,
      buckets: [{ n: 36, winners: 36 }],
    };
    const rows = [...LIVE.filter(r => r.provider !== "datagolf"), censored];
    const ordered = orderSourceRows(rows);

    expect(ordered.find(r => r.provider === "datagolf")!.state).toBe("censored");
    expect(sourceRowsExcludedFromRollup(ordered)).toHaveLength(0);
    expect(panelsFor(rows)).toHaveLength(rows.length);
    expect(bySourceCaption(ordered).startsWith(UNQUALIFIED)).toBe(true);
  });

  it("qualifies once, not once per withheld provider", () => {
    const rows = [
      ...LIVE,
      { provider: "zzz", label: "Aardvark", sources: ["zzz"], n: 0, ece: 0, mce: 0, brier: 0, buckets: [] },
    ];
    const caption = bySourceCaption(orderSourceRows(rows));
    expect(sourceRowsExcludedFromRollup(orderSourceRows(rows))).toHaveLength(2);
    expect(caption.match(/with outcomes in this cohort/g)).toHaveLength(1);
    // Still one sentence about what the card IS — no count, no provider name.
    // Notice 34 keeps coverage and limitation out of the page body; the fold
    // below carries who and why.
    expect(caption).not.toContain("DataGolf");
    expect(caption).not.toContain("2");
  });

  it("keeps the rest of the caption identical in both arms", () => {
    const tail =
      " all on the same 0–100% axis. Tap any point for example outcomes, " +
      "or a provider tab for the full-width view.";
    for (const rows of [LIVE, LIVE.filter(r => r.provider !== "datagolf")]) {
      expect(bySourceCaption(orderSourceRows(rows)).endsWith(tail)).toBe(true);
    }
  });
});
