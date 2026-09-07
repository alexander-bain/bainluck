import Foundation

// MARK: - The rail a totals map is drawn on

/// Where a totals map's axis starts and ends, and whether the card is worth
/// drawing at all.
///
/// #3503. Both answers used to live inline in `MarketMapView` as expressions
/// on a SwiftUI view, which meant the only way to assert either of them was to
/// rasterise the view and read pixels — and a raster cannot tell you why an
/// axis says `205`. They are pulled out here for the same reason
/// `SportVocab.projectedMarginNote` was pulled out of `ScoreDifferentialChart`
/// in #3465: the rule is a fact about numbers, not about a view.
///
/// What went wrong. A live tennis match (event 15305808, Kasnikowski vs
/// Marrero, `tennis_other`, photographed 2026-09-06) carried exactly one totals
/// row — `outcome_name: "Under"`, `"… Total Sets O/U 2.5"` — and
/// `extractTotalThresholds` only parses an outcome whose name contains
/// `"over"`. So no threshold parsed, and the rail fell back to
/// `max(0, 180 - 10) … 230 + 10`: **`170 · 205 · 240+`, on a card titled
/// "Games map — Projected total games"**, over a sport played in 20–40 games.
/// With no thresholds there was also no density and no marker, so the whole
/// card was a title, a subtitle and a decorative bar carrying three invented
/// numbers.
enum MarketMapRail {

    /// An axis, low end to high end.
    struct Bounds: Equatable {
        let min: Double
        let max: Double
    }

    /// The rail for a totals map.
    ///
    /// Three cases, in strict priority order:
    ///
    /// 1. **A market quoted lines.** They are the data and they alone set the
    ///    rail, padded as before. Unchanged by #3503 on purpose — a fallback
    ///    that starts overriding real values is a worse bug than the one being
    ///    fixed.
    /// 2. **No lines, but the sport has a declared span.** Use it, widened to
    ///    contain any marker we are about to draw. A marker off the end of its
    ///    own rail is worse than a wide rail.
    /// 3. **No lines and no declared span** (an undeclared sport — see
    ///    ``SportVocab/totalRange``). Build the rail around the only numbers
    ///    anybody actually quoted, which are the markers. Nothing here is
    ///    invented.
    ///
    /// - Parameters:
    ///   - thresholds: every full-match line that parsed, in the sport's unit.
    ///   - markerValues: every value the card will plot as a marker.
    ///   - declared: the sport's own span, nil where we have none.
    ///   - pad: breathing room around real lines. Only case 1 uses it.
    static func totalBounds(
        thresholds: [Double],
        markerValues: [Double],
        declared: ClosedRange<Int>?,
        pad: Double
    ) -> Bounds {
        // 1 — real lines win outright.
        if let lo = thresholds.min(), let hi = thresholds.max() {
            // A total cannot be negative; the floor predates #3503.
            return Bounds(min: Swift.max(0, lo - pad), max: hi + pad)
        }

        let declaredBounds = declared.map {
            Bounds(min: Double($0.lowerBound), max: Double($0.upperBound))
        }

        guard let lo = markerValues.min(), let hi = markerValues.max() else {
            // Nothing at all. `totalMapDrawsNothing` is true here, so a caller
            // that honours it never reaches this line. One that does not gets
            // the sport's own span, or a visibly broken `0 … 1` rail rather
            // than a plausible one: a wrong number that looks sourced is the
            // whole defect this file exists to stop, and loud beats silent.
            return declaredBounds ?? Bounds(min: 0, max: 1)
        }

        // 2 — the sport's span, never clipping a marker off the end.
        if let declaredBounds {
            return Bounds(
                min: Swift.max(0, Swift.min(declaredBounds.min, lo)),
                max: Swift.max(declaredBounds.max, hi)
            )
        }

        // 3 — undeclared: the markers are the only scale in evidence.
        let spread = Swift.max(hi - lo, Swift.max(1, hi * 0.25))
        return Bounds(min: Swift.max(0, lo - spread / 2), max: hi + spread / 2)
    }

    /// The rail for a MARGIN map.
    ///
    /// #3533. The margin rail was one inline expression that always widened to
    /// the sport's own ± span:
    ///
    /// ```swift
    /// let rangeMin = min((allMargins.min() ?? Double(-maxMargin)) - 3, Double(-maxMargin))
    /// ```
    ///
    /// which is right for every map drawn in the sport's unit and wrong for the
    /// one that is not. A tennis SET margin map — rungs at ±1.5 and ±2.5 — laid
    /// on tennis's ±6 **games** span puts a two-set handicap a quarter of the
    /// way along a rail that does not measure sets, next to axis labels reading
    /// "by 6+". `declared` is nil there (see
    /// ``SportVocab/marginRange(quotedBy:)``) and the rungs set their own scale.
    ///
    /// - Parameters:
    ///   - margins: every signed rung the map will draw.
    ///   - declared: the sport's ± span, nil where this map is not in its unit.
    ///   - pad: breathing room beyond the outermost rung. Declared case only —
    ///     three points either side of an NFL ladder is room, three SETS either
    ///     side of a set handicap is a rail of empty space.
    static func marginBounds(margins: [Double], declared: Int?, pad: Double) -> Bounds {
        if let declared {
            // Verbatim the pre-#3533 arithmetic, so no map drawn in its own
            // sport's unit moves by a pixel on this change.
            let span = Double(declared)
            return Bounds(
                min: Swift.min((margins.min() ?? -span) - pad, -span),
                max: Swift.max((margins.max() ?? span) + pad, span)
            )
        }
        // Undeclared: the rungs are the only scale in evidence, and a margin
        // rail is symmetric about zero because the two sides of a match are.
        // Rounded UP to a whole unit past the outermost rung, so a ±1.5 set
        // handicap gets a ±2 rail whose end labels ("by 2+") are true, rather
        // than a rung sitting exactly on the end of its own axis.
        guard let widest = margins.map(abs).max(), widest > 0 else {
            return Bounds(min: -1, max: 1)
        }
        let half = (widest + 0.5).rounded(.up)
        return Bounds(min: -half, max: half)
    }

    /// The magnitude each END of a margin axis names — its OWN outer bound.
    ///
    /// #3642. `marginBounds`' declared branch is asymmetric by construction:
    /// `min` is driven by the away rungs and `max` by the home rungs, and the
    /// two sides of a book are not quoted to the same depth. Both call sites in
    /// `MarketMapView` nonetheless derived ONE `axisEnd` from `rangeMax` and
    /// printed it on both ends, so the left label named a bound the rail does
    /// not have.
    ///
    /// THE PHOTOGRAPH. Event 14780138 (Patriots at Seahawks, NFL, `scheduled`),
    /// iPad Pro 11-inch simulator against production, 2026-09-06 —
    /// `artifacts-native-042/ipad-nfl-14780138-top.png`. The axis read
    /// **`NE by 23.5+ · Tie · SEA by 23.5+`**, a symmetric claim, over a rail
    /// whose "Tie" sat at 43% of its width.
    ///
    /// THE MECHANISM, from the event's own `/api/events/14780138/game-markets`:
    /// 31 spread rows, Seattle quoted out to `20.5` and New England only to
    /// `15.0`. With football's `declared` span of 18 and `pad` 3 that is
    /// `min(-15.0 - 3, -18) = -18.0` and `max(20.5 + 3, 18) = 23.5`. The right
    /// label was right; the left overstated New England's end of the rail by
    /// 5.5 points. Zero therefore falls at `18 / 41.5 = 43.4%`, which is where
    /// the word "Tie" was photographed, and the PROJECTION marker (`SEA +1.0`)
    /// at `19 / 41.5 = 45.8%` — 395.7 px along a rail measured at x 61–792,
    /// against 395.5 px measured off the PNG.
    ///
    /// Why it survived #3566, which rewrote this very axis row. Two reasons,
    /// and the second is the instructive one:
    ///
    /// 1. The label measurement behind ``endLabelBandPercent`` was taken off a
    ///    SYMMETRIC card — `artifacts-native-038/nfl-14632820-s900.png`, whose
    ///    axis reads `SF by 18+ … LAR by 18+` because that rail is `[-18, 18]`.
    ///    On a symmetric rail one shared label is indistinguishable from two
    ///    correct ones. That measurement is unaffected by this change.
    /// 2. ``midAxisLabel``'s own documentation already records the asymmetry, in
    ///    this same file: *"full game, margins `[-15.0, 20.5]` → rail
    ///    `[-18.0, 23.5]` → zero at 43.4%"*. The rail was measured, the number
    ///    was written down, and the axis went on printing `23.5` at both ends
    ///    regardless — because #3566 was looking at where the MIDDLE label goes
    ///    and the end labels were not the subject. A recorded measurement is not
    ///    a checked one.
    ///
    /// Returned as magnitudes because that is what the labels print: the axis
    /// says "NE by 18+", never "NE by -18+" — the side already carries the sign.
    static func marginAxisEnds(_ bounds: Bounds) -> (left: Double, right: Double) {
        (left: abs(bounds.min), right: abs(bounds.max))
    }

    /// True when a totals map would draw no ladder, no density and no marker —
    /// a purple bar with an axis under it and nothing on it.
    ///
    /// This mirrors, condition for condition, the marker block it guards; the
    /// mapping is: with no thresholds parsed, the card's over/under line is
    /// exactly ``overUnder``, because the only other source for it is
    /// `thresholds.first(where:)`. The margin map has had this guard since
    /// ux/1034 B5 (`marginMapIsEmptyChrome`); the totals map never got one,
    /// which is why #3410's class — chrome drawn over no data — survived on
    /// this widget.
    static func totalMapDrawsNothing(
        hasThresholds: Bool,
        overUnder: Double?,
        isLive: Bool,
        isDone: Bool,
        hasScoreboardTotal: Bool,
        hasProjectedTotal: Bool
    ) -> Bool {
        if hasThresholds { return false }                      // ladder + density
        if overUnder != nil { return false }                   // PRE-GAME / PROJECTION
        if isDone, hasScoreboardTotal { return false }         // FINAL
        if isLive, hasScoreboardTotal, hasProjectedTotal { return false }  // ACTUAL + PROJECTED
        return true
    }

    // MARK: - Whether a totals card has a distribution to show

    /// True when a totals rail has a real distribution under it.
    ///
    /// #3576. `totalMapDrawsNothing` asks whether the card is worth drawing at
    /// all; this asks the next question down, which nobody was asking: the card
    /// is worth drawing, but is the SHAPE on it data?
    ///
    /// THE PHOTOGRAPH. Event 15292756 (Detroit Lions @ Indianapolis Colts, NFL,
    /// `completed`, DET 25 – IND 16), iPhone 17 simulator against production,
    /// 2026-09-06 — `artifacts-native-038/AFTER-nfl-settled-15292756-s600.png`.
    /// A card headed "Points map / **Final points distribution**", a `FINAL 41
    /// points` tile, an axis `28 · 45 · 62+`, and between them a uniform
    /// pale-purple bar. `GET /api/events/15292756/game-markets` returns **0
    /// totals rows and 0 spreads** — re-measured 2026-09-06, still 0 — so there
    /// is no distribution, and the three facts the card does hold (the final,
    /// the sport's range, and that nobody quoted a line) are all true and none
    /// of them is a distribution.
    ///
    /// This mirrors, condition for condition, the two flat-array exits in
    /// `MarketMapView.buildDensityFromThresholds` — the mapping is: fewer than
    /// two lines, or no pair of lines separated by a positive gap (its `rawPdf`
    /// skips every `dt <= 0`, so lines all quoted at the same number leave it
    /// empty). Either exit returns `Array(repeating: 8, count: 14)`, which the
    /// rail renders as one shade at alpha `0.21` across its whole width: a
    /// placeholder that looks sourced. That is #3503's complaint one notch
    /// smaller, in `marginMapIsEmptyChrome`'s own words, a rail that "looks like
    /// a distribution and is not one".
    ///
    /// Not a reason to hide the card (#2086 — declare, don't delete): the card
    /// keeps its FINAL tile and its correctly-labelled axis, and only stops
    /// claiming a shape it does not have.
    ///
    /// Both of the builder's flat exits fall out of ONE expression, which is
    /// why there is no `count >= 2` guard in front of it: with fewer than two
    /// lines the pairwise zip is empty and `contains` is vacuously false, and
    /// with two or more it applies exactly the `dt > 0` test that the builder's
    /// `rawPdf` loop applies. A guard would restate the first case in a second
    /// place, where it could later disagree with this one.
    ///
    /// - Parameter thresholds: every line that parsed, in any order — this
    ///   sorts for itself rather than trusting the caller to have done it.
    static func totalRailHasDistribution(thresholds: [Double]) -> Bool {
        let sorted = thresholds.sorted()
        return zip(sorted, sorted.dropFirst()).contains { $1 - $0 > 0 }
    }

    /// The subtitle a FULL-GAME totals map may print.
    ///
    /// #3576. Three states, and only the third of them is new:
    ///
    /// 1. **Not settled** — "Projected total <unit>". It promises a projected
    ///    total and delivers one (the PROJECTION marker, drawn off a quoted
    ///    over/under line, not off the density). Unchanged, deliberately: the
    ///    word this issue is about is "distribution", and this string does not
    ///    contain it.
    /// 2. **Settled, with a distribution** — "Final <unit> distribution".
    ///    Unchanged: the card means it.
    /// 3. **Settled, with none** — "Final <unit>". Exactly what the card shows:
    ///    a final, on a rail with no shape on it.
    static func fullTotalSubtitle(isDone: Bool, hasDistribution: Bool, unit: String) -> String {
        guard isDone else { return "Projected total \(unit)" }
        return hasDistribution ? "Final \(unit) distribution" : "Final \(unit)"
    }

    /// The subtitle a HALF totals map may print — the same rule in the half
    /// card's own words.
    ///
    /// #3576 covers this card too because it is the same sentence over the same
    /// flat array: `halfTotalCard` calls the same `buildDensityFromThresholds`
    /// and hard-codes "Half <unit> distribution" regardless of what came back.
    /// One rule, one implementation — #3554's lesson was three copies of a
    /// prefix-stripping rule drifting apart, and a second copy of this one would
    /// start the same way.
    static func halfTotalSubtitle(hasDistribution: Bool, unit: String) -> String {
        hasDistribution ? "Half \(unit) distribution" : "Half \(unit)"
    }

    // MARK: - Whether a margin card has a distribution to show

    /// True when a margin rail has a real distribution on it.
    ///
    /// #3763, the sibling of ``totalRailHasDistribution`` on the card #3576
    /// declared out of scope ("the margin cards do not pass the new flag and are
    /// untouched").
    ///
    /// **It reads the builder's OUTPUT, not its inputs, and that is the whole
    /// design.** `totalRailHasDistribution` has to mirror
    /// `buildDensityFromThresholds`' flat exits condition-for-condition, because
    /// those exits are early returns it cannot see. `buildDensityFromSpreads` has
    /// no early exit worth mirroring — it bins, then normalises — so the honest
    /// question is simply *what did it just draw*, and asking the array removes
    /// the possibility of drift that a second copy of the arithmetic would
    /// reintroduce. #3554's lesson was three copies of one rule disagreeing; this
    /// keeps the count at one.
    ///
    /// **Distinct HEIGHTS, not populated bins** — and that distinction is
    /// measured, not aesthetic. Census of production, 2026-09-06, every event
    /// page across seven leagues that draws a margin map (`census049-margin.json`,
    /// 22 cards): **9 of the 22 have no distribution on them.** Eight are a single
    /// rung — one bin at full height, thirteen at zero, which is the case #3763
    /// was filed on. The ninth is the one that decides this signature:
    ///
    /// (That 9 is measured in the world where #3743 has landed, which is the
    /// world this code ships into. Against the tree #3743 was cut from it is 3:
    /// the six US Open cards still carried the complement as a second rung at a
    /// different price, so they read as two varied bins and this rule would have
    /// left them alone. The two ships are textually independent and compose in
    /// either order — but #3763's reach depends on #3743's, and a later reader
    /// re-running the census on the wrong base would get the smaller number and
    /// think this rule had regressed.)
    ///
    /// ```
    /// MLB 15305475, Twins @ White Sox — 5 rungs, 5 populated bins
    ///   [0, 0, 0, 0, 0, 0, 96, 96, 96, 96, 96, 0, 0, 0]
    /// ```
    ///
    /// Five bins wide and perfectly flat. A `populatedBins >= 2` rule passes
    /// that card and prints "distribution" over a solid uniform block — the
    /// exact overclaim #3576 named on the totals side, "a uniform shape that
    /// looks like a distribution and is not one". Reading heights refuses it and
    /// refuses the single-rung case with the same expression, no special case
    /// for either.
    ///
    /// **And that card is a whole CLASS, not a curiosity.** It is `completed`,
    /// and its five served legs are "Chicago WS wins by over 1.5 / 2.5 / 3.5 /
    /// 4.5 / 5.5 runs" at `p = 0.99, 0.99, 0.99, 0.99, 0.99` — the White Sox won
    /// by six, so every line below the final margin resolved to the same
    /// certainty. A settled game does that BY CONSTRUCTION: the cover lines
    /// inside the final margin all go to ~1 and the ones outside it all go to
    /// ~0, so the rail flattens into one block whose width is the margin. Every
    /// settled game with a spread ladder arrives here, which is why this is
    /// worth a rule rather than a special case.
    ///
    /// The admitted borderline, named so the next reader knows it was decided:
    /// MLB 15298326 draws two bins at `[1.9, 96.0]`. Two bars of very different
    /// height do say where the mass is, so this returns true for it. What this
    /// refuses is a rail that asserts *no* shape, not a rail with a coarse one.
    ///
    /// **What this deliberately does NOT answer, #3772:** whether the shape on a
    /// rail that passes here is the right shape. `buildDensityFromSpreads` bins
    /// CUMULATIVE cover probabilities as though they were densities, so it plots
    /// a survival curve — on live 15305476 the mass between the 1.5 and 2.5 rungs
    /// is `0.58 - 0.12 = 0.46` and the rail draws `0.12`. This rule is about
    /// whether the card asserts a shape at all, and is correct either way; when
    /// #3772 is fixed by differencing (as `buildDensityFromThresholds` already
    /// does) the surviving "distribution" is genuinely earned.
    ///
    /// - Parameter density: the array `buildDensityFromSpreads` just returned —
    ///   the heights that will actually be drawn, post-normalisation.
    static func marginRailHasDistribution(density: [Double]) -> Bool {
        // Exact equality, deliberately. Every height is `(binSum / peak) * 96`
        // evaluated by one expression over sums of the same served prices, so
        // bins that agree agree bit-for-bit — that is why the flat card above
        // reads as five exact `96.0`s. A tolerance here would be a magic number
        // guarding against data no venue produces.
        var firstPositive: Double?
        for height in density where height > 0 {
            guard let first = firstPositive else {
                firstPositive = height
                continue
            }
            if height != first { return true }
        }
        return false
    }

    /// The subtitle a FULL-GAME margin map may print.
    ///
    /// #3763. The same sentence-level rule as ``fullTotalSubtitle`` with one
    /// difference that matters: the totals card overclaims only once settled,
    /// because its unsettled string ("Projected total points") never contained
    /// the word. The margin card says "**Projected** margin distribution" before
    /// the game and "**Final** margin distribution" after, so it overclaims in
    /// both states and both are gated here. The census population is mixed —
    /// the eight single-rung cards include live US Open matches and a completed
    /// MLB game (15305471) — so a settled-only gate would have fixed under half
    /// of them.
    static func fullMarginSubtitle(isDone: Bool, hasDistribution: Bool) -> String {
        let noun = isDone ? "Final margin" : "Projected margin"
        return hasDistribution ? "\(noun) distribution" : noun
    }

    /// The subtitle a HALF margin map may print.
    ///
    /// #3763. `halfMarginCard` hard-codes "Half margin distribution" over the
    /// same `buildDensityFromSpreads` output as the full card, which is how
    /// `halfTotalCard` read before #3576 gave it ``halfTotalSubtitle``.
    static func halfMarginSubtitle(hasDistribution: Bool) -> String {
        hasDistribution ? "Half margin distribution" : "Half margin"
    }

    // MARK: - Where the mid axis label goes

    /// Where a map's middle axis label belongs.
    ///
    /// #3566. A margin map used to print the concept twice: `densityRail` drew
    /// a `"0"` at the real zero, and `mapCard` drew `"Tie"` in an equal-spacer
    /// `HStack`, which is to say always at the geometric centre. On an
    /// asymmetric rail — which is every rail with a favourite on it — the two
    /// are either contradictory or on top of each other, and there is no rail
    /// on which both are right.
    ///
    /// Measured on ONE page, event 14632820 (SF 49ers @ LA Rams, iPhone 17
    /// against production, 2026-09-06, `artifacts-native-038/`):
    ///
    /// - full game, margins `[-15.0, 20.5]` → rail `[-18.0, 23.5]` → zero at
    ///   **43.4%**: `0` and `Tie` crowded 6.6 points apart.
    /// - 1st half, rail `[-52.0, 18.0]` → zero at **74.3%**: `Tie` a quarter of
    ///   the rail from the tie line, while the card's own tile said `LAR +1.0`.
    /// - 2nd half, rail `[-18.0, 18.0]` → zero at **50.0%**: `0` printed on top
    ///   of `Tie`, illegible.
    ///
    /// So the mid label IS the zero label wherever a rail has a zero, and there
    /// is only one of it.
    enum MidAxisLabel: Equatable {
        /// No zero on this rail — the label is the midpoint of the range and
        /// belongs at the middle. Every totals map.
        case centred
        /// A margin rail: the label names zero, so it goes where zero is.
        case at(percent: Double)
        /// Zero is close enough to an end that the label would print on top of
        /// an end label. The end label already says whose territory that is.
        case withheld
    }

    /// How wide a band at each end of the axis row the end labels occupy.
    ///
    /// Measured, not chosen: off `artifacts-native-038/nfl-14632820-s900.png`
    /// (iPhone 17, 402 pt, axis row ~907/920 of the frame), `SF by 18+` runs to
    /// **13.5%** from the left edge and `LAR by 18+` back to **16.2%** from the
    /// right. 20 clears the wider of the two with room for a longer abbreviation.
    ///
    /// Web withholds its own zero label at a much narrower `>5 && <95`
    /// (`frontend/components/MarketMap.tsx:344`) because web moves a 7 px `"0"`
    /// and keeps `"Tie"` centred. iOS moves the word, so it needs the word's
    /// room. The two surfaces are answering different halves of #3566; web owes
    /// the other half.
    static let endLabelBandPercent: Double = 20

    /// - Parameter zeroPercent: where zero falls on the rail, 0–100, or nil on a
    ///   rail that has no zero (a totals map).
    static func midAxisLabel(
        zeroPercent: Double?,
        endLabelBand: Double = endLabelBandPercent
    ) -> MidAxisLabel {
        guard let zero = zeroPercent else { return .centred }
        if zero <= endLabelBand || zero >= 100 - endLabelBand { return .withheld }
        return .at(percent: zero)
    }
}
