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
}
