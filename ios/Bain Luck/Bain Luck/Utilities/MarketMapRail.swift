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

    // MARK: - The tense the scoring-spectrum card may print

    /// Which tense EVERY string on the scoring-spectrum card is in.
    ///
    /// #3930, and it exists because this card has now been given the same third
    /// state twice, by two fixes, fifteen minutes apart, in two of its three
    /// strings — and they disagreed on screen:
    ///
    /// ```
    /// Projected scoring            <- #3905 gave the headings two states
    /// Projected combined scoring
    ///    3.5+   LAST QUOTE   0%    <- #3929 gave the rungs three
    /// ```
    ///
    /// One card, two tenses, on a match that had been over for hours. Neither
    /// fix was wrong; the card simply had no single place to answer "what tense
    /// am I in?", so the answer was written down three times and the third
    /// rewrite only reached one of them.
    ///
    /// 🔴 **THE TWO FACTS ARE NOT ONE FACT, AND THAT IS THE WHOLE REASON THERE
    /// ARE THREE CASES.** "The event is over" and "this card has a final to
    /// grade against" come apart on any sport whose scoreboard does not count
    /// the widget's unit — tennis reports SETS, so `scoreboardCountsTheUnit` is
    /// false, `actualTotal` is nil, and a `completed` match lands in the middle
    /// case. #3905's doc comment reasoned its way to exactly this and then had
    /// only two cases to put the answer in, which is why it chose the safer
    /// wrong one: heading a settled tennis card "Projected" is a smaller lie
    /// than heading it "Final" over five ungraded rungs.
    ///
    /// - Parameters:
    ///   - finalTotal: the value the rungs are graded against, or nil for none.
    ///   - isSettled: whether the event is over.
    enum SpectrumTense {
        /// Not over. A forecast, and it says so.
        case projected
        /// Over, but this card cannot grade — the prices are frozen last quotes
        /// and there is no final in this unit to state.
        case settled
        /// Over, with a final to grade every rung against.
        case graded

        static func of(finalTotal: Int?, isSettled: Bool) -> SpectrumTense {
            if finalTotal != nil { return .graded }
            return isSettled ? .settled : .projected
        }
    }

    /// The section heading `TotalPointsSpectrumView` may print.
    ///
    /// #3905, and the same sentence-level rule as ``fullTotalSubtitle`` one card
    /// lower on the same page. On event 15306209 (`Reds 3 — Dodgers 6`,
    /// `completed`) the map above read "**Final** runs distribution" — #3763's
    /// doing — while this card, over the same nine runs of the same finished
    /// game, still read "**Projected** scoring" above a value tile saying
    /// `Final total runs / 9` and a ladder grading `7.5+ HIT`. One screen, the
    /// same settled quantity, called "Final" three times and "Projected" twice.
    ///
    /// 🔴 **THE PARAMETER IS THE FINAL ITSELF, NOT `isDone`, AND THAT IS THE
    /// WHOLE FIX.** Every other subtitle on this page keys on `isDone` and is
    /// right to; this one cannot, because "the event is over" and "this card has
    /// a final to grade against" are different facts here. `actualTotal` is nil
    /// on a settled game whose scoreboard does not count the widget's unit —
    /// tennis reports SETS, so `SportVocab.scoreboardCountsTheUnit` is false and
    /// the card has no combined-games total to state. `TotalPointsSpectrumView`
    /// already branches on exactly that: with no final, `finalStrip` does not
    /// render and every rung falls to the `PRE-GAME … 42%` arm of `ladderRow`.
    ///
    /// **Measured on production 2026-09-08, so this is a live card and not a
    /// hypothetical:** event **15305795** (`Zverev def. Darderi`, `completed`)
    /// serves **5** `game_total` thresholds, which is `ladderRowLimit` — enough
    /// that `fullView` draws, with all five rungs captioned `PRE-GAME`. An
    /// `isDone` gate would have headed that card "Final scoring" over five
    /// PRE-GAME rungs: #3905's own defect, re-created by its fix, on a sport it
    /// never looked at. Two more the same night (15305796, 15305728) render the
    /// full card from 3 and 2 rungs, because the minimal card is pre-game-only.
    ///
    /// Passing the final that the rungs are graded with means the heading and
    /// the verdicts beneath it read off ONE value and cannot disagree — the
    /// invariant `TotalPointsSpectrumTenseTests` exists to hold.
    ///
    /// 🟠 **#3930 GAVE THIS ITS THIRD STATE, AND CHOSE THE WORD DELIBERATELY.**
    /// Everything above still holds — `finalTotal` still decides "Final", and a
    /// settled tennis card still must not say it. What changed is that the
    /// remaining case stopped being called "Projected" on a match that had been
    /// over for hours. The word is `SettledQuote`'s own: this same screen prints
    /// ``SettledQuote/sectionNote`` ("**settled** — any percentage is a last
    /// quote") two inches lower, so "Settled scoring" joins the vocabulary the
    /// page already speaks instead of opening a second one (#1650) — the same
    /// reasoning, and the same source string, that ``spectrumRungCaption``
    /// used for `LAST QUOTE`.
    ///
    /// The rejected alternative was a bare "Scoring" — drop the adjective
    /// rather than pick one, on the argument that the rungs now carry the tense
    /// per-row and a heading cannot then be wrong. It loses because the three
    /// headings would read "Projected scoring" / "Scoring" / "Final scoring",
    /// and the bare one does not read as deliberate restraint; it reads as a
    /// string that failed to load. Alex's standing ruling is *settled means
    /// settled* — one settled language across the app — and a card that goes
    /// quiet about its tense is not speaking it.
    ///
    /// - Parameters:
    ///   - finalTotal: what ``totalLadderResult(threshold:finalTotal:)`` is
    ///     being handed for this card's rungs — `nil` when there is none.
    ///   - isSettled: whether the event is over, the card's own lifecycle
    ///     predicate. Only consulted when there is no final.
    static func spectrumSectionTitle(finalTotal: Int?, isSettled: Bool) -> String {
        switch SpectrumTense.of(finalTotal: finalTotal, isSettled: isSettled) {
        case .projected: return "Projected scoring"
        case .settled: return "Settled scoring"
        case .graded: return "Final scoring"
        }
    }

    /// The heading over the scoring spectrum's threshold ladder.
    ///
    /// #3905. The second of the card's two hard-coded strings, under the same
    /// rule and the same parameter as ``spectrumSectionTitle(finalTotal:isSettled:)`` —
    /// "Projected combined runs" sat directly over `7.5+ HIT / 9.5+ MISS`.
    ///
    /// `unit` is the widget's own, read from the markets rather than the sport
    /// (#3509), so this says "combined runs" on baseball and "combined scoring"
    /// where neither the markets nor the sport declare a unit.
    ///
    /// #3930 moved it to three states with its sibling above and for the same
    /// reasons — the two headings are one sentence in two sizes and have never
    /// been allowed to differ in tense
    /// (`testTheCardsTwoHeadingsAreNeverInDifferentTenses`).
    static func spectrumLadderTitle(finalTotal: Int?, unit: String, isSettled: Bool) -> String {
        switch SpectrumTense.of(finalTotal: finalTotal, isSettled: isSettled) {
        case .projected: return "Projected combined \(unit)"
        case .settled: return "Settled combined \(unit)"
        case .graded: return "Final combined \(unit)"
        }
    }

    // MARK: - Reading a totals ladder once the game is over

    /// What a totals line DID, once there is a final to grade it against.
    ///
    /// #3823. `push` is unreachable on today's data and is here anyway, because
    /// the alternative is a rule that is silently wrong the first day it is not.
    /// **Measured 2026-09-07:** of the **95,821** `Over N` legs production serves
    /// on `quantity` markets, **95,821 are half-lines** — not one integer line,
    /// so no served row can land exactly on its own threshold. On a half-line
    /// `>` and `>=` agree, which is precisely why the wrong one survives
    /// unnoticed: `TotalPointsSpectrumView:358` grades with `>=` and would call
    /// a push a HIT the day an integer line arrives.
    ///
    /// 🟠 **SHARED WITH THE MARGIN LADDER SINCE #3852, so the `Total` in these
    /// three names is now a historical prefix rather than a scope.** A margin
    /// card feeds one side's own positive cover lines and the margin that side
    /// won by (``sideFinalMargin(gameMargin:isHome:)``) — the same monotone
    /// ladder in a different unit. The names were left alone deliberately:
    /// renaming the type without renaming the two functions buys nothing, and
    /// renaming all three is a cosmetic diff across shipped #3823 code. Read
    /// `finalTotal` as "the value this ladder is graded against".
    enum TotalLadderResult: Equatable {
        case over
        case under
        case push
    }

    static func totalLadderResult(threshold: Double, finalTotal: Int) -> TotalLadderResult {
        let final = Double(finalTotal)
        if final > threshold { return .over }
        if final < threshold { return .under }
        return .push
    }

    /// The word a graded row prints in the value column.
    ///
    /// All four characters wide, deliberately: the column they share with
    /// `"100%"` is a fixed 32 pt (``MarketMapLadderLayout/valueColumnWidth``) and
    /// the font is monospaced, so a four-character verdict provably fits wherever
    /// a four-character percentage already does. `MarketMapLadderTests` measures
    /// that rather than trusting this sentence.
    static func totalLadderResultLabel(_ result: TotalLadderResult) -> String {
        switch result {
        case .over: return "HIT"
        case .under: return "MISS"
        case .push: return "PUSH"
        }
    }

    /// The caption an **ungraded** rung prints, beside the percentage it is the
    /// tense of — the other half of ``totalLadderResultLabel(_:)`` above, which
    /// is what a rung says once it *can* be graded.
    ///
    /// #3925. THE PHOTOGRAPH: event 15305795 (`Darderi 0 — Zverev 3`,
    /// `completed`), `artifacts-native-061/BEFORE-3925-tennis-15305795-s900-master-02d9979b.png`.
    /// Five rungs of a finished match, every one of them captioned `PRE-GAME`
    /// over a settlement price:
    ///
    /// ```
    ///    3.5+   PRE-GAME   ▬▬▬▬▬▬▬▬   0%
    ///    8.5+   PRE-GAME   ▬▬▬▬▬▬▬▬   0%
    /// ```
    ///
    /// 🔴 **THIS IS #3850's DEFECT ON THE PATH #3850 COULD NOT REACH.** #3850
    /// removed that caption by *replacing* it with a HIT/MISS badge — which only
    /// happens where the card has a final to grade against. `finalTotal` is nil
    /// on a settled game whose scoreboard does not count the widget's unit
    /// (tennis reports SETS), so `result == nil`, the badge never renders, and
    /// the caption #3850 deleted is still on screen. The two facts this card
    /// needs are **different**: "the event is over" and "this card can grade" —
    /// which is why both are parameters and neither is inferred from the other.
    ///
    /// 🟠 **THE NUMBER IS NOT WRONG; ONLY THE WORD OVER IT IS.** Measured on
    /// that specimen: the `3.5` rung's `over_probability` is `0.001`, and the
    /// match went 3 sets, so `Over 3.5` is genuinely false and `0%` is the
    /// correct settled price. Nothing here touches the value — this names its
    /// tense honestly instead of asserting the opposite one.
    ///
    /// 🟢 **THE SETTLED WORDS ARE NOT INVENTED HERE.** They are
    /// ``SettledQuote/prefix``, the string this same event page already prints
    /// two inches lower in its Additional Markets block ("settled — any
    /// percentage is a last quote"), and which is held character-for-character
    /// against `frontend/lib/settledQuote.ts` by the jest parity test. Uppercased
    /// to match the register of the caption slot, exactly as `projectionBar`
    /// uppercases its own label — a NEW constant here would be a second
    /// settlement vocabulary on one screen, which is #1650.
    ///
    /// - Parameters:
    ///   - finalTotal: the value the rungs are graded against, or nil when this
    ///     card has none. Non-nil ⇒ nil caption: the verdict badge owns the row.
    ///   - isSettled: whether the event is over. Callers pass the card's OWN
    ///     lifecycle predicate rather than ``SettledQuote/isSettled(_:)``, so a
    ///     rung cannot say "last quote" on a status for which the same card
    ///     still draws its pre-game strip. Widening all of them together is a
    ///     separate change, not this one.
    ///
    /// 🟢 **#3930 ROUTED THIS THROUGH ``SpectrumTense`` WITHOUT CHANGING WHAT IT
    /// RETURNS.** This function was already the only one of the card's three
    /// strings that knew about all three states; the headings above have caught
    /// up, and the switch is now shared so a fourth state cannot reach one of
    /// them and miss the others — which is precisely how #3930 happened.
    static func spectrumRungCaption(finalTotal: Int?, isSettled: Bool) -> String? {
        switch SpectrumTense.of(finalTotal: finalTotal, isSettled: isSettled) {
        case .projected: return "PRE-GAME"
        case .settled: return SettledQuote.prefix.uppercased()
        case .graded: return nil
        }
    }

    /// Which slice of a settled game's totals ladder is worth printing.
    ///
    /// #3823. THE PHOTOGRAPH: event 15305475 (Minnesota 1 — Chicago WS 10,
    /// `completed`, **11 runs**), `artifacts-native-050/POSTDEPLOY-3763-mlb-15305475-s900.png`.
    /// The Runs map's ladder read
    ///
    /// ```
    /// Over 2.5   99%      Over 5.5   99%
    /// Over 3.5   99%      Over 6.5   99%
    /// Over 4.5   99%      Over 7.5   99%
    /// ```
    ///
    /// — six rows of the same number on a game that finished hours earlier.
    ///
    /// TWO FAULTS, AND THE SECOND IS THE ONE THAT SURVIVES FIXING THE FIRST.
    ///
    /// 1. The number is a *forecast* on a decided event. That is graded away by
    ///    ``totalLadderResult``.
    /// 2. **The window is wrong.** The card takes the LOWEST six lines, and on a
    ///    settled game the lowest lines are the least informative ones — every
    ///    line below the final resolved to the same certainty, so grading alone
    ///    would have traded six identical `99%`s for six identical `HIT`s. The
    ///    reader learns nothing either way.
    ///
    /// What a settled ladder is FOR is the step: the last line the game cleared
    /// and the first it did not. `/api/events/15305475/game-markets`, re-measured
    /// 2026-09-07, serves eleven lines `2.5 … 12.5` at `p = 0.99` up to `10.5`
    /// and `0.01` from `11.5`, so this returns `5 ..< 11` — `7.5 · 8.5 · 9.5 ·
    /// 10.5` HIT, `11.5 · 12.5` MISS. **The reader can read "11" off the step
    /// without the card printing a word**, and 11 is what the game scored.
    ///
    /// The window is CENTRED on the step and then slid back inside the array, so
    /// the two ends behave without a special case for either: a final that
    /// cleared every line shows the top `limit` rows (the lines it came closest
    /// to failing) and one that cleared none shows the bottom `limit`.
    ///
    /// 🔴 THIS IS NOT A HIDING RULE. The pre-game card shows six of eleven rows
    /// too — `prefix(6)` — so nothing here withholds anything a reader could see
    /// before. It moves the same six-row window to where the information is.
    ///
    /// - Parameters:
    ///   - sortedThresholds: the lines, ascending. `extractTotalThresholds` sorts
    ///     for its own reasons; this restates the requirement because the
    ///     `firstIndex` below is only a step-finder on a sorted array.
    ///   - finalTotal: the score this card is allowed to grade against — see the
    ///     `scoreboardCounts` gate at the call site.
    ///   - limit: how many rows the card draws.
    static func settledLadderWindow(
        sortedThresholds: [Double],
        finalTotal: Int,
        limit: Int
    ) -> Range<Int> {
        let count = sortedThresholds.count
        guard limit > 0 else { return 0 ..< 0 }
        guard count > limit else { return 0 ..< count }
        let firstMiss = sortedThresholds.firstIndex {
            totalLadderResult(threshold: $0, finalTotal: finalTotal) != .over
        } ?? count
        let ideal = firstMiss - limit / 2
        let start = Swift.max(0, Swift.min(count - limit, ideal))
        return start ..< (start + limit)
    }

    // MARK: - Which rungs may share ONE combined-scoring ladder (#3925 item 2)

    /// The sub-contest scopes a totals market names in its own title.
    ///
    /// #3925 item 2. The photographed card stacked these five rungs into one
    /// ascending ladder headed "combined scoring" (event 15305795, `completed`):
    ///
    /// ```
    ///  3.5+   Alexander Zverev vs. Luciano Darderi: Total Sets O/U 3.5   <- SETS, whole match
    ///  4.5+   Alexander Zverev vs. Luciano Darderi: Total Sets O/U 4.5   <- SETS, whole match
    ///  8.5+   Zverev vs. Darderi: Set 1 Games O/U 8.5                    <- GAMES, in ONE set
    ///  9.5+   Zverev vs. Darderi: Set 1 Games O/U 9.5                    <- GAMES, in ONE set
    /// 10.5+   Zverev vs. Darderi: Set 1 Games O/U 10.5                   <- GAMES, in ONE set
    /// ```
    ///
    /// `4.5+` and `8.5+` read as neighbouring points on one scale while one
    /// counts sets in a match and the other counts games in a single set.
    ///
    /// 🔴 **THIS IS NOT A SECOND COPY OF THE BACKEND'S RULE, AND THE DIFFERENCE
    /// IS THE WHOLE REASON IT EXISTS HERE.** `events.py` already owns #3161's
    /// `_match_scope_totals`, whose regexes these deliberately echo — and it is
    /// documented FAIL-OPEN: `return match_scope or game_totals`. On this
    /// specimen *both* families are non-match-scope (one wrong scope, one wrong
    /// unit for the map it feeds), so nothing survives the filter, so the
    /// backend serves all five **on purpose** rather than take the card down.
    /// That decision is about WHICH RUNGS TO SERVE and it is right. This answers
    /// the different question the serving side declined to: given two families
    /// in one payload, WHICH ONE DOES A SINGLE AXIS DRAW. Changing the backend
    /// to drop them would empty the card the fail-open exists to protect.
    ///
    /// 🟠 **SPORT-BLIND ON PURPOSE, WHERE THE BACKEND IS NOT.** #3161 warns that
    /// "a sport gets a scope rule only by being NAMED", because `Total Rounds`
    /// is the CORRECT match total for MMA and boxing. That warning guards the
    /// **unit** half of its rule. It does not reach this one: no sport's
    /// whole-contest total is called `Set 1`, `Map 1` or `1st Half`, so an
    /// explicit ordinal sub-contest is safe to read without naming a sport.
    /// The unit half is NOT mirrored here — a `Total Sets` rung is the wrong
    /// unit for the map card, which is fixed in match games, but it is a true
    /// statement about the whole match and this card takes its noun from the
    /// markets (``SportVocab/totalsUnit(quotedBy:)``), so it can simply say
    /// "combined sets".
    ///
    /// **Every pattern below was measured reachable** over linked
    /// `futures_markets` names carrying `O/U` or `total`, production
    /// 2026-09-08: `set N` **18,000** · `1st/2nd half` **36,348** ·
    /// `first 5` **2,053** · `map N` **653** · `Nth quarter/period` **133**.
    /// 🟢 `q1`–`q4` and `inning N` measured **0** and are therefore NOT
    /// implemented — an unreachable pattern is a claim no evidence supports,
    /// and the next reader would trust it.
    static func namesASubContestScope(_ marketName: String?) -> Bool {
        let name = (marketName ?? "").lowercased()
        guard !name.isEmpty else { return false }
        return Self.subContestScopeREs.contains {
            $0.firstMatch(in: name, range: NSRange(name.startIndex..., in: name)) != nil
        }
    }

    /// Compiled once — ``namesASubContestScope(_:)`` runs per rung, per redraw.
    ///
    /// `\bset\s*\d` is what keeps `Total Sets O/U 3.5` OUT of this: "set" does
    /// match inside "sets", but what follows is `s`, not a digit. That is the
    /// same boundary `_TENNIS_SET_SCOPED_TOTAL_RE` relies on, and
    /// `testTheSetsUnitFamilyIsNotMistakenForASetScopedOne` is the guard.
    private static let subContestScopeREs: [NSRegularExpression] = [
        #"\bset\s*\d"#,
        #"\bmap\s*\d"#,
        #"\b(?:1st|first|2nd|second)\s+half\b"#,
        #"\b(?:1st|2nd|3rd|4th|first|second|third|fourth)\s+(?:quarter|period)\b"#,
        #"\bfirst\s+5\b"#,
    ].compactMap { try? NSRegularExpression(pattern: $0) }

    /// The indices of `marketNames` that one combined-scoring ladder may pool.
    ///
    /// #3925 item 2. Whole-contest rungs where there are any, everything
    /// otherwise.
    ///
    /// 🔴 **FAIL-OPEN, AND THE NUMBER IS WHY.** Measured on production
    /// 2026-09-08 over 21,928 tennis events: **3,941** carry both a
    /// `Total Sets` and a `Set N Games` family — those are the pooled ladders
    /// this repairs — but **4,451** carry a set-scoped family and NOTHING else.
    /// An unconditional drop would empty the ladder on all 4,451, which is
    /// `thresholds.isEmpty` and so `EmptyView()`: it would delete a card from
    /// more pages than it fixed. Those keep exactly what they render today.
    /// This is `_match_scope_totals`' own reasoning — "a map with two
    /// wrong-scope rungs is worse than one without them; a map that is gone is
    /// worse than both" — applied one layer out, deliberately, so the two sides
    /// fail the same way rather than compounding.
    ///
    /// (Counts are over market NAMES, an upper bound on the served population:
    /// `game_total` is classified at serve time, and a card also needs enough
    /// rungs to draw. They size the risk, which is what they are for.)
    ///
    /// Order is preserved and no rung is reordered or reweighted — the caller
    /// sorts by threshold, as it always has.
    static func matchScopeLadderIndices(marketNames: [String?]) -> [Int] {
        let all = Array(marketNames.indices)
        let wholeContest = all.filter { !namesASubContestScope(marketNames[$0]) }
        return wholeContest.isEmpty ? all : wholeContest
    }

    // MARK: - Reading a MARGIN ladder once the game is over

    /// The margin a SIDE won by, from the game's home-signed final margin.
    ///
    /// #3852, the margin-side twin of #3823 — and the whole of the new rule,
    /// because of a reduction worth stating plainly:
    ///
    /// 🟢 **A MARGIN LADDER IS TWO TOTALS LADDERS, ONE PER SIDE.** Every
    /// ``SpreadRungs/Rung`` makes exactly one claim — *this side by more than
    /// `abs(margin)`, at this probability* — a sentence written down three times
    /// in `SpreadRungs` (``SpreadRungs/fromHandicap(_:_:home:away:unit:)``,
    /// ``SpreadRungs/namesARange(_:)``) because #3743 and #3788 were both filed
    /// against rows that did not make it. So one side's rungs, taken as POSITIVE
    /// cover lines in ascending order and graded against the margin THAT SIDE
    /// won by, are exactly the monotone `HIT…HIT MISS…MISS` array that
    /// ``totalLadderResult(threshold:finalTotal:)`` and
    /// ``settledLadderWindow(sortedThresholds:finalTotal:limit:)`` were written
    /// for. Nothing else is needed: no second grader, no second window rule, and
    /// therefore no second copy of either to drift out of step — #3554's lesson
    /// was three copies of one rule disagreeing, and this keeps the count at one.
    ///
    /// This function is the ONE thing the reduction needs: the sign flip that
    /// puts the away side on its own number line.
    ///
    /// 🔴 **IT TAKES `isHome`, NOT THE SIGN OF THE RUNG.** A rung at `margin: 0`
    /// — "wins by more than 0", i.e. wins — names a side that its own sign cannot
    /// tell you, and resolving that tie by inspecting the sign would silently
    /// hand every pick'em rung to the home team. That is #3568's defect
    /// (`isHome ? t : -t` quietly resolving an ambiguous side to HOME) one level
    /// down, and `SpreadRungs.Rung` already carries the answer.
    ///
    /// THE PHOTOGRAPH this fixes. Event 15305475 (Minnesota 1 — Chicago WS 10,
    /// `completed`, Sox by 9), `artifacts-native-053/AFTER-3823-mlb-15305475-s1030.png`,
    /// one card above the ladder #3823 had just fixed:
    ///
    /// ```
    /// Run margin map / Final margin     FINAL Sox +9     PRE-GAME Sox +1.5
    ///   Sox +1.5   ████████████████  99%
    ///   Sox +2.5   ████████████████  99%
    ///   Sox +3.5   ████████████████  99%
    /// ```
    ///
    /// Three rows giving a 99% chance the Sox cover +1.5 in a game that ended
    /// nine runs ago, and — the second fault, the one grading alone does not fix
    /// — the three LEAST informative lines on the card, because the ladder takes
    /// the tightest rungs by `abs(margin)` and on a settled game every line
    /// inside the final margin resolved identically.
    ///
    /// **MEASURED, production, 2026-09-07** — 70 settled events fetched, 0 fetch
    /// errors (the count matters: an earlier pass of this census swallowed 429s
    /// in a bare `except` and reported a confident zero):
    ///
    /// - **6** of the 70 carry a full-game margin ladder at all.
    /// - **39 of 39** cover lines across that population and the NFL/NCAAF
    ///   window are HALF-lines. **Zero integer lines**, so ``TotalLadderResult``
    ///   `.push` is unreachable here exactly as #3823 measured it unreachable on
    ///   the totals side — and pinned anyway, below.
    /// - **No settled card in the population has a step**: every quoted line sat
    ///   inside the final margin, so the window's payoff today is "the tightest
    ///   lines the winner actually cleared" rather than a visible step. On
    ///   15305468 (Cubs 3 — Marlins 10, six rungs `1.5 … 6.5`) that moves the
    ///   card from `1.5 · 2.5 · 3.5` to `4.5 · 5.5 · 6.5`.
    /// - Away rungs are rare — **1** of the 6 cards quotes both sides.
    ///
    /// 🟠 **THE READING THE VERDICT COMMITS TO, said out loud because the label
    /// is ambiguous and grading it is not.** `"Sox +1.5"` is a cover line on a
    /// margin axis, not a handicap: the row's bar is already `P(Sox by more than
    /// 1.5)`, the rung sits at `+1.5` on the very rail the `FINAL Sox +9` marker
    /// sits on, and HIT/MISS grades that claim. Under the *other* reading of a
    /// `+` prefix — Sox with 1.5 points given to them — the two verdicts differ
    /// whenever the Sox lose by one, so this is a real fork and it is resolved
    /// the way the card is drawn. The label itself is not touched here; changing
    /// it is a different defect class and would invalidate this ship's
    /// before/after frame.
    ///
    /// **WHAT THIS DELIBERATELY DOES NOT ANSWER.** On the first integer line to
    /// arrive, `>` and `>=` stop agreeing and `threshold` alone cannot tell them
    /// apart — #3788 records the same half-point gap ("`P(M >= 15)` is
    /// `P(M > 14.5)`, not `P(M > 15)` … pre-existing, out of scope"). A tie
    /// therefore grades `.push`, which prints a grey "PUSH" and claims neither a
    /// hit nor a miss; that is the correct amount of confidence for a row whose
    /// operator we cannot read, and it is unreachable on the data above.
    static func sideFinalMargin(gameMargin: Int, isHome: Bool) -> Int {
        isHome ? gameMargin : -gameMargin
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

    // MARK: - Whether a map may say PRE-GAME

    /// Whether a market map may plot the tile captioned `PRE-GAME`.
    ///
    /// #3885, the margin-side twin of #3850 and the same root cause one card
    /// higher on the same page. On event 15305476 (`Nationals 5 — Dodgers 7`,
    /// `FINAL`) the Run margin map read
    ///
    /// ```
    ///   FINAL             PRE-GAME
    ///   Dodgers +2        Nationals +5.5
    ///   Nationals +5.5  |                MISS
    ///   Dodgers   +1.5  ██████████████   HIT
    /// ```
    ///
    /// — the `PRE-GAME` tile naming **the very rung the card grades MISS two
    /// lines below it**.
    ///
    /// 🔴 **NEITHER OF THE TWO NUMBERS THIS TILE CAN REACH IS A PRE-GAME
    /// NUMBER, ONCE THE GAME IS OVER.** The tile draws
    /// `sportSpread ?? closestToEvenMargin(parsed)`, and on a settled event:
    ///
    ///   * `sportSpread` is `event.currentOdds?.homeSpread` at the call site in
    ///     `EventDetailView` — the CURRENT line by construction. On the specimen
    ///     it is `-1.5`, captured `2026-09-07T05:06Z`, which is a settlement
    ///     price wearing a pre-game caption.
    ///   * ``MarketMapView/closestToEvenMargin(_:)`` picks the rung nearest a
    ///     coin flip, which is a real question on a live book and a coin toss on
    ///     a settled ladder where every line has resolved. The specimen's two
    ///     spreads price `0.99` (Dodgers +1.5) and `0.02` (Nationals +5.5), so
    ///     `|0.99 - 0.5| = 0.490` loses to `|0.02 - 0.5| = 0.480` **by a
    ///     thousandth** and the LOSING side's deepest line takes the tile. On
    ///     15305475 the same arithmetic hands it `Sox +1.5`, a line the window
    ///     below no longer even draws.
    ///
    /// 🟠 **AND THERE IS NOTHING HONEST TO SUBSTITUTE — measured, not assumed.**
    /// `events.opening_home_spread` / `opening_over_under` DO exist server-side
    /// and are well populated (1,409 and 1,421 of 1,519 settled events in the
    /// last 14 days, 92.8% / 93.6%; the specimen's are `-1.5` and `8.5`, and
    /// that `8.5` is exactly the pre-game total #3850 went looking for). But
    /// `GET /api/events/{id}` — the endpoint this card is rendered from — does
    /// **not** serve them: its `opening_odds` carries `home_probability`,
    /// `away_probability`, `favorite` and nothing else (re-read from production
    /// 2026-09-08), and `OpeningOdds` in `CommonTypes.swift` has no field for
    /// them either. Only `GET /api/events/{id}/debug` emits them. So the client
    /// cannot draw a true pre-game line today at any price.
    ///
    /// That gap is worth closing and is filed separately — closing it would let
    /// this card tell a genuinely good story (`PRE-GAME Dodgers +1.5` →
    /// `FINAL Dodgers +2`). Until it is, #3823's rule stands: a number whose
    /// tense you cannot vouch for is worse than no number. The `FINAL` tile
    /// beside it already carries the whole story.
    ///
    /// 🟢 **NARROW ON PURPOSE.** Live and pre-game maps are untouched, so the
    /// NFL projection marker pinned by
    /// `SpreadRungTests.testTheNFLProjectionMarkerMovesAndThatIsTheFix`
    /// (event 14780138, unsettled) cannot move. The live-tense cousin — a LIVE
    /// card also captioning `currentOdds` "PRE-GAME" — is the one #3850
    /// deliberately left out, and is left out here too rather than fixed in
    /// passing on a state nobody has photographed.
    static func drawsPregameMarker(isDone: Bool) -> Bool {
        !isDone
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

    // MARK: - Keeping a marker dot on the rail it names

    /// Where a marker dot's CENTRE belongs, so that the whole dot stays inside
    /// the rail.
    ///
    /// #3820. `densityRail` positioned every dot with
    /// `.position(x: railWidth * pct / 100)`, and `.position` places a view by
    /// its centre. A value at either end of its own scale therefore put half a
    /// dot outside the track.
    ///
    /// THE PHOTOGRAPH. Event 15305472 (Cardinals 10 — Rockies 8, final),
    /// iPhone 17 against production, 2026-09-07 —
    /// `artifacts-native-051/mlb-15305472-s700.png`, the **Runs map** card.
    ///
    /// THE MEASUREMENT, read off that frame in pixels at @3x rather than taken
    /// from the code's own account of itself, and confirmed on BOTH dots before
    /// any of it was believed:
    ///
    /// - the rail runs `x = 89.1 … 1115.5` px, so **342.1 pt** wide — which is
    ///   `402 - 2*16` page padding `- 2*14` card padding = 342 pt exactly.
    /// - `PRE-GAME 16.2` on a `4 … 18` rail is 87.14%: predicted centre 983 px,
    ///   **measured 983.5**.
    /// - `FINAL 18` is 100%: predicted centre 1115 px — the rail's own trailing
    ///   edge — **measured 1115.5**.
    /// - a dot is `dotSize` wide plus a 2 pt stroke that SwiftUI centres on the
    ///   edge, so the drawn width is `dotSize + 2` = 24 pt: predicted 72 px,
    ///   **measured 71**.
    ///
    /// So the FINAL dot hung **12 pt — half of itself — past the end of the
    /// track**, and its white ring finished 1 px short of the card's border.
    ///
    /// This is #3237's defect class, which the charts fixed for period chips
    /// ("a marker at or near `x = 0` centres a chip whose left half hangs over
    /// the y-axis gutter"), and which THIS FILE already fixes for the middle
    /// axis LABEL by withholding it inside ``endLabelBandPercent``. A dot cannot
    /// be withheld — it is the value — so it is moved instead.
    ///
    /// 🔴 CLAMPING IS SAFE AGAINST OVERHANG AND UNSAFE AGAINST CROWDING, and a
    /// bound is only ever safe against one of the two. Moving the end dot inward
    /// closes the gap to its neighbour, so that gap was measured too rather than
    /// hoped for: the two centres sit 132 px = **44 pt** apart, the clamp moves
    /// FINAL 12 pt, leaving **32 pt** between centres against a 24 pt drawn
    /// width — 8 pt of visible track still between them. `testFinalAndPreGame…`
    /// pins that number, so a future change to `markerRadius` that would make
    /// the two dots touch fails here rather than in a screenshot.
    ///
    /// - Parameters:
    ///   - idealX: where the value falls on the rail, in points from its leading
    ///     edge. Already clamped to `0 ... railWidth` by `posOnRail`.
    ///   - markerWidth: the dot's full DRAWN width, stroke included — not the
    ///     `frame` width, which excludes the half-stroke that hangs outside it.
    ///   - railWidth: the track's width in points.
    static func clampedMarkerCenterX(
        idealX: Double,
        markerWidth: Double,
        railWidth: Double
    ) -> Double {
        let half = markerWidth / 2
        // A dot wider than its own rail cannot be placed without overhanging on
        // one side or the other. Centre it, so it overhangs evenly rather than
        // picking an end — and so the caller never has to special-case a
        // degenerate layout pass, where SwiftUI hands out a zero width before
        // the first real one.
        guard railWidth > markerWidth else { return railWidth / 2 }
        return Swift.max(half, Swift.min(railWidth - half, idealX))
    }
}
