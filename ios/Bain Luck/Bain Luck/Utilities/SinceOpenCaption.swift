import Foundation

/// The event hero's "since open" caption: WHO moved, and the journey they moved
/// along.
///
/// ═══ #3051 — THE CAPTION DISAGREED WITH THE TWO NUMBERS IT SITS BETWEEN ═══
///
/// Photographed on production (event `15301214`, 2026-09-04, iPhone 17). One
/// frame, three lines, in this order:
///
///          5%  –  95%
///     Sabalenka +3% since open
///      Opened  9%  –  91%
///
/// 91 → 95 is **+4**. The caption said **+3**, because `homeDelta` was computed
/// on the RAW probabilities (0.945 − 0.9129 = 0.0321 → 3) while the two numbers
/// the caption sits between are the RENDERED ones. Rounding twice, on two
/// different quantities, makes a caption disagree with its own screen — the same
/// class as #2951 and #3033, and here it is on the most-looked-at element of the
/// page, inviting a subtraction that gives the reader a different answer.
///
/// ═══ WHY THE ARITHMETIC IS REMOVED RATHER THAN CORRECTED ═══
///
/// #3051's own repair was "subtract the two printed INTEGERS, and say `pp`". The
/// web twin shipped exactly that (#5719) and then withdrew the unit word
/// (#5995), for a reason that transfers to Swift unchanged: on a scoring sport
/// `pts` is the SCORE's unit. `+49 pts Giants since open` printed directly above
/// a 21–14 scoreline, where 49 is larger than either team's points and reads as
/// a running total. `pp` is jargon (D102), and a hero-only unit word would split
/// the caption off the family the rest of the app's deltas belong to.
///
/// So the caption states the two LEVELS and no delta at all:
///
///     Sabalenka 91% → 95% since open
///
/// This is the same invariant with the arithmetic deleted. "The caption must
/// equal the difference of the printed levels" existed so that
/// `shown − caption = opened` held on screen; printing the levels themselves
/// makes it true **by construction**. There is no subtraction left to get wrong,
/// so #3051's primary defect cannot recur on this line at all, and no unit word
/// is owed because no unit is named.
///
/// ═══ EACH END MATCHES THE LINE IT SITS NEXT TO, NOT THE OTHER END ═══
///
/// The two levels are drawn by two different lines of the hero — the duel pair
/// above and the `Opened` pair below — and a caption that quoted one formatter
/// for both would be the original defect wearing new words. ux/1248 flagged the
/// live form of that on the web arm, where the hero prints a bare `100%` while
/// its own opened line prints `>99%` (#6064). Native cannot reproduce it: both
/// lines call ``formatProbability(_:renderedPercent:)``, whose `<1%` / `>99%`
/// guards run on the PROBABILITY and so fire identically at both ends. That is a
/// property of this app today rather than a law, so
/// `SinceOpenCaptionTests.testTheTwoLevelsUseTheSameMarkerRuleTheHeroDoes`
/// pins it and reddens if a second formatter ever reaches one end.
enum SinceOpenCaption {

    /// The caption a hero should draw, and the side it names, or `nil` where it
    /// draws none.
    ///
    /// Takes the same raw inputs as the two lines it quotes, and re-derives the
    /// printed integers through the shared contracts rather than receiving
    /// them, so the caption cannot be handed a pair the hero did not print.
    ///
    /// - Parameters:
    ///   - away: `current_odds.away_probability`, served. Ignored on a
    ///     draw-priced sport — see ``DrawPricedWinner/printablePair(away:home:sport:)``.
    ///   - servedAwayPercent: `current_odds.away_rendered_percent`.
    ///   - servedHomePercent: `current_odds.home_rendered_percent`. The served
    ///     pair describes `current_odds` and nothing else, so the opening pair
    ///     below passes `nil` for both and falls to the local contract — the
    ///     trap ``duelPercents(away:home:servedAway:servedHome:)`` documents.
    ///   - names: the compact pair, taken TOGETHER (#3430) — a label the other
    ///     side shares un-names the subject #1830 exists to name.
    /// - Returns: the sentence, and `isHome` so the caller can colour it to
    ///   match its subject.
    static func caption(
        away: Double?,
        home: Double?,
        servedAwayPercent: Int?,
        servedHomePercent: Int?,
        openingAway: Double?,
        openingHome: Double?,
        sport: String?,
        names: (away: String, home: String)
    ) -> (text: String, isHome: Bool)? {
        guard let pair = DrawPricedWinner.printablePair(
            away: away, home: home, sport: sport),
            let openingHome else { return nil }

        // The draw gate is unchanged and stays on the RAW move. It answers "did
        // this line move at all", which is a question about the market rather
        // than about what got printed, and #1830's caption has always asked it.
        guard abs(pair.home - openingHome) > 0.02 else { return nil }

        // The opened pair is built the way the `Opened` line builds it, and a
        // pair that line could not print is one this caption cannot quote. On a
        // two-way sport that means a served `opening_odds.away_probability`:
        // deriving `1 − home` here instead would be the re-derivation
        // `printablePair` documents as the trap, and it would put a number on
        // screen that no other line on the hero agrees with. Absent it, the
        // hero draws no caption rather than half of one.
        guard let opened = DrawPricedWinner.printablePair(
            away: openingAway, home: openingHome, sport: sport) else { return nil }

        let trend = DrawPricedWinner.trendSubject(
            homeDelta: pair.home - openingHome, sport: sport)

        let nowPcts = duelPercents(
            away: pair.away, home: pair.home,
            servedAway: servedAwayPercent, servedHome: servedHomePercent)
        let openPcts = duelPercents(
            away: opened.away, home: opened.home,
            servedAway: nil, servedHome: nil)

        let from: String
        let to: String
        if trend.isHome {
            // #5271 — a withheld away slot withholds the rendered PAIR with it.
            // The duel contract's answer for one side can be `100 − other`, and
            // the hero's draw-priced branch refuses that number for the same
            // reason it refuses the away price, so it rounds home alone. Both
            // lines this caption quotes do that; so does this.
            to = pair.away == nil
                ? formatProbability(pair.home)
                : formatProbability(pair.home, renderedPercent: nowPcts[1])
            from = opened.away == nil
                ? formatProbability(opened.home)
                : formatProbability(opened.home, renderedPercent: openPcts[1])
        } else {
            // Unreachable on a draw-priced sport: `trendSubject` names HOME
            // there precisely because home's loss is not away's gain, so an
            // away subject is a two-way sport, where `printablePair` returning
            // non-nil guarantees both away values. Written as a `guard` rather
            // than a force-unwrap because that is an argument about two other
            // types, and a caption is not worth a crash.
            guard let awayNow = pair.away, let awayOpen = opened.away else { return nil }
            to = formatProbability(awayNow, renderedPercent: nowPcts[0])
            from = formatProbability(awayOpen, renderedPercent: openPcts[0])
        }

        let subject = trend.isHome ? names.home : names.away
        return (text: "\(subject) \(from) \u{2192} \(to) since open", isHome: trend.isHome)
    }
}
