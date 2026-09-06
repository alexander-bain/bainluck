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
