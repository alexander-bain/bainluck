import XCTest

@testable import Bain_Luck

/// #3051 — the live event hero's "since open" caption disagreed with the two
/// numbers it sits between.
///
/// Photographed on production (event `15301214`, 2026-09-04, iPhone 17 / iOS
/// 26.5, `artifacts-native-011/P1-event-15301214.png`). One frame:
///
///          5%  –  95%
///     Sabalenka +3% since open
///      Opened  9%  –  91%
///
/// 91 → 95 is **+4**. The delta was computed on the RAW probabilities
/// (0.945 − 0.9129 = 0.0321 → 3) while the numbers above and below it are the
/// RENDERED ones, so a reader doing the subtraction the hero invites got a
/// different answer from the hero.
///
/// The repair is #5995's, routed from the web arm by ux/1248: print the two
/// LEVELS and no delta at all. Every specimen below is therefore an assertion
/// about strings the hero itself draws, and the arithmetic that used to be here
/// is asserted ABSENT rather than asserted correct.
///
/// WHAT THESE PIN, each one a mutant:
///
/// 1. the filed specimen renders `Sabalenka 91% → 95% since open` — the two
///    integers on screen, in order, with no `3` and no `4` anywhere;
/// 2. no delta in any unit, and no unit word (`pts` / `pt` / `pp` / `%` as a
///    difference) — #5995's whole objection;
/// 3. the CURRENT end takes the served rendered pair and the OPENED end does
///    NOT — the trap `duelPercents` documents, which no sum guard can see;
/// 4. an away subject quotes AWAY's journey, not home's — #1830 is intact and
///    the caption is still a gain;
/// 5. a draw-priced sport names home and rounds home ALONE — #5271's withheld
///    slot withholds the rendered pair with it;
/// 6. the `<1%` / `>99%` markers fire per END, on that end's own probability —
///    the web arm's #6064 arriving in Swift;
/// 7. the ≤2pp gate, and the three absences that draw no caption at all.
final class SinceOpenCaptionTests: XCTestCase {

    /// A two-way sport. `tennis_wta_us_open` is the filed specimen's own key and
    /// `SportVocab` matches it on "tennis" (`winnerMarketPricesADraw: false`).
    private let twoWay = "tennis_wta_us_open"
    /// The draw-priced arm, the same key `DrawPricedWinnerTests` uses.
    private let drawPriced = "soccer_epl"

    private let names = (away: "Rakhimova", home: "Sabalenka")

    /// The filed frame's four probabilities, and nothing else in this file
    /// re-derives them: these are what event `15301214` served.
    private func filedSpecimen(
        servedAwayPercent: Int? = nil,
        servedHomePercent: Int? = nil
    ) -> (text: String, isHome: Bool)? {
        SinceOpenCaption.caption(
            away: 0.055, home: 0.945,
            servedAwayPercent: servedAwayPercent,
            servedHomePercent: servedHomePercent,
            openingAway: 0.0871, openingHome: 0.9129,
            sport: twoWay, names: names)
    }

    // MARK: - 1 + 2: the specimen, and the arithmetic that is gone

    func testTheFiledSpecimenQuotesTheTwoIntegersTheHeroPrints() throws {
        let caption = try XCTUnwrap(filedSpecimen())

        // 95 and 91 are the strings the hero and its `Opened` line printed in
        // the photographed frame. Asserted as a literal, because a test that
        // recomputed them through the same contracts would pass on any
        // arithmetic at all.
        XCTAssertEqual(caption.text, "Sabalenka 91% \u{2192} 95% since open")
        XCTAssertTrue(caption.isHome, "Sabalenka is the home side and rose")
    }

    func testTheShippedDefectsExactSpellingIsRefused() throws {
        let caption = try XCTUnwrap(filedSpecimen())

        // What production printed.
        XCTAssertFalse(caption.text.contains("+3"), "the raw-derived delta")
        // And the repair #3051 originally asked for, which #5995 withdrew: the
        // integer-derived delta is just as wrong to print now, because the
        // caption is no longer a difference.
        XCTAssertFalse(caption.text.contains("+4"), "the integer-derived delta")
    }

    func testNoDeltaAndNoUnitWordInAnySpelling() throws {
        let caption = try XCTUnwrap(filedSpecimen())

        // A signed figure in ANY unit or none. The two `%` that remain are
        // attached to the LEVELS, which is the correct use of the sign and the
        // thing #5995 was never objecting to — so this is aimed at the sign,
        // not at the percent.
        XCTAssertNil(
            caption.text.range(of: "[+\u{2212}-]\\s*\\d", options: .regularExpression),
            "a difference, signed, in \(caption.text)")
        // The score's own word, both spellings — "+1 pt" was a real branch of
        // the line this replaces — and the jargon D102 rules out.
        XCTAssertNil(
            caption.text.range(of: "\\b(pts?|pp)\\b", options: .regularExpression),
            "a unit word in \(caption.text)")
        // Not vacuous: the sentence this replaces trips both guards.
        let shipped = "Sabalenka +3% since open"
        XCTAssertNotNil(
            shipped.range(of: "[+\u{2212}-]\\s*\\d", options: .regularExpression),
            "the control must trip the guard, or the guard proves nothing")
    }

    // MARK: - 3: the served pair describes `current_odds` and nothing else

    func testTheCurrentEndTakesTheServedPairAndTheOpenedEndDoesNot() throws {
        // 0.845 rounds LOCALLY to 85 and the server says 84 — so the two
        // arithmetics are separable on this specimen, which is what makes the
        // assertion mean something.
        let caption = try XCTUnwrap(SinceOpenCaption.caption(
            away: 0.155, home: 0.845,
            servedAwayPercent: 16, servedHomePercent: 84,
            openingAway: 0.40, openingHome: 0.60,
            sport: twoWay, names: names))

        XCTAssertEqual(caption.text, "Sabalenka 60% \u{2192} 84% since open")
        // The current end is the SERVER's integer, not this client's.
        XCTAssertFalse(caption.text.contains("85%"), "the locally derived now")
        // And the opening end never sees it. `opening_odds` carries no served
        // percents at any deploy; handing `current_odds`' rounding to another
        // source's probability prints a mismatched pair that still sums to 100.
        XCTAssertFalse(caption.text.contains("84% \u{2192}"), "served leaked to open")
        XCTAssertFalse(caption.text.contains("16%"), "served away leaked")
    }

    // MARK: - 4: #1830 — the caption names the RISER, and quotes THEIR journey

    func testAnAwaySubjectQuotesAwaysJourneyNotHomes() throws {
        // Home 62 → 35. Away therefore 38 → 65, and #1830's fix is that the
        // caption reports the gain rather than a bare unlabelled fall.
        let caption = try XCTUnwrap(SinceOpenCaption.caption(
            away: 0.65, home: 0.35,
            servedAwayPercent: nil, servedHomePercent: nil,
            openingAway: 0.38, openingHome: 0.62,
            sport: twoWay, names: names))

        XCTAssertEqual(caption.text, "Rakhimova 38% \u{2192} 65% since open")
        XCTAssertFalse(caption.isHome, "colour must follow the subject")
        // The mutation this kills: quoting home's levels under away's name,
        // which would print a FALL beside a name that rose — #1830 exactly.
        XCTAssertFalse(caption.text.contains("62%"), "home's open under away's name")
        XCTAssertFalse(caption.text.contains("35%"), "home's now under away's name")
    }

    // MARK: - 5: #5271 — a withheld away slot withholds the rendered pair too

    func testADrawPricedSportNamesHomeAndRoundsHomeAlone() throws {
        // The served pair is present and describes a two-way reading of this
        // market: 84 is `100 − 16`, a number about a complement the hero's
        // draw-priced branch refuses to print. `duelPercents` returns it
        // whenever both served values exist, so a caption that used it would
        // print 84% for a 0.72 probability.
        let caption = try XCTUnwrap(SinceOpenCaption.caption(
            away: 0.28, home: 0.72,
            servedAwayPercent: 16, servedHomePercent: 84,
            openingAway: 0.40, openingHome: 0.60,
            sport: drawPriced, names: names))

        XCTAssertEqual(caption.text, "Sabalenka 60% \u{2192} 72% since open")
        XCTAssertTrue(caption.isHome, "a draw-priced sport always names home")
        XCTAssertFalse(caption.text.contains("84%"), "the complement's rounding")
    }

    func testADrawPricedFallKeepsItsSubjectAndDoesNotBecomeAnAwayGain() throws {
        // Home shedding five points does not hand them to the away side; the
        // draw can take any part of them. So the fall stays home's, stated as
        // home's own journey — which is the one wording where a DOWNWARD
        // journey is correct, and it needs no minus sign to say so.
        let caption = try XCTUnwrap(SinceOpenCaption.caption(
            away: 0.30, home: 0.70,
            servedAwayPercent: nil, servedHomePercent: nil,
            openingAway: 0.10, openingHome: 0.90,
            sport: drawPriced, names: names))

        XCTAssertEqual(caption.text, "Sabalenka 90% \u{2192} 70% since open")
        XCTAssertTrue(caption.isHome)
        XCTAssertFalse(caption.text.contains("Rakhimova"), "the complement's gain")
    }

    // MARK: - 6: the markers fire per END, on that end's own probability

    func testTheTwoLevelsUseTheSameMarkerRuleTheHeroDoes() throws {
        // ux/1248: on the web arm the hero prints a bare `100%` where its own
        // opened line prints `>99%` (#6064), so the two ends of one caption can
        // be rendered by two different formatters. Native cannot reproduce it —
        // both lines call `formatProbability`, whose guards run on the
        // PROBABILITY — and this is the test that keeps it that way.
        let high = try XCTUnwrap(SinceOpenCaption.caption(
            away: 0.004, home: 0.996,
            servedAwayPercent: nil, servedHomePercent: nil,
            openingAway: 0.04, openingHome: 0.96,
            sport: twoWay, names: names))

        // 99.6 is capped; 96 is not. Each end answers for its own value.
        XCTAssertEqual(high.text, "Sabalenka 96% \u{2192} >99% since open")
        XCTAssertFalse(high.text.contains("100%"), "an uncapped now")
        XCTAssertFalse(high.text.contains(">99% \u{2192} >99%"), "one end copied")
    }

    func testAPricedOutcomeNeverOpensAtZeroPercent() throws {
        // The away side opened at 0.005. Its rendered integer is 0 — the
        // complement contract gives the whole point to the leader — and `0%` on
        // a priced outcome is a false claim, so `formatProbability`'s `<1%`
        // guard overrides the integer at this end while the other end keeps its
        // own. Home fell 99.5 → 94, so the subject is away and this level is
        // the one the caption OPENS on.
        let low = try XCTUnwrap(SinceOpenCaption.caption(
            away: 0.06, home: 0.94,
            servedAwayPercent: nil, servedHomePercent: nil,
            openingAway: 0.005, openingHome: 0.995,
            sport: twoWay, names: names))

        XCTAssertEqual(low.text, "Rakhimova <1% \u{2192} 6% since open")
        XCTAssertFalse(low.text.contains("0%"), "a priced outcome called impossible")
    }

    func testTheOpeningEndKeepsItsOwnMarkerUnderAHomeSubject() throws {
        // THE SURVIVOR. The battery's M9 — the opening end interpolating its
        // integer raw instead of going through `formatProbability` — lived
        // through the first eleven specimens, because in every one of them the
        // two spellings agree: a home subject ROSE, so its opening level is the
        // low one, and none of those opened low enough to need a marker. The
        // marker on the opening end was therefore asserted nowhere for the
        // branch that draws most captions.
        //
        // A longshot that came in is the missing shape. The away side is the
        // complement's leader at 99, so the derived home integer is 1 — and 1%
        // is a claim this app does not make about a 0.8% price.
        let longshot = try XCTUnwrap(SinceOpenCaption.caption(
            away: 0.70, home: 0.30,
            servedAwayPercent: nil, servedHomePercent: nil,
            openingAway: 0.992, openingHome: 0.008,
            sport: twoWay, names: names))

        XCTAssertEqual(longshot.text, "Sabalenka <1% \u{2192} 30% since open")
        // Stated as a PREFIX, not as `!contains("1%")`: the correct sentence
        // contains "1%" inside "<1%", so the negative form fails on the right
        // answer. The mutant's output differs from it by the marker alone.
        XCTAssertTrue(
            longshot.text.hasPrefix("Sabalenka <1%"),
            "the marker, not the derived integer 1")

        // The same end's OTHER arm: #5271 withholds the pair, so the opening
        // level is rounded bare — and the marker has to survive that route too.
        let drawLongshot = try XCTUnwrap(SinceOpenCaption.caption(
            away: nil, home: 0.30,
            servedAwayPercent: nil, servedHomePercent: nil,
            openingAway: nil, openingHome: 0.008,
            sport: drawPriced, names: names))

        XCTAssertEqual(drawLongshot.text, "Sabalenka <1% \u{2192} 30% since open")
    }

    // MARK: - 7: the gate, and the three absences

    func testTheTwoPointGateIsUnchanged() {
        // Unchanged from #1830: it asks "did this line move at all", a question
        // about the market rather than about what got printed.
        XCTAssertNil(SinceOpenCaption.caption(
            away: 0.49, home: 0.51,
            servedAwayPercent: nil, servedHomePercent: nil,
            openingAway: 0.50, openingHome: 0.50,
            sport: twoWay, names: names), "a 1pp move draws nothing")

        XCTAssertNotNil(SinceOpenCaption.caption(
            away: 0.47, home: 0.53,
            servedAwayPercent: nil, servedHomePercent: nil,
            openingAway: 0.50, openingHome: 0.50,
            sport: twoWay, names: names), "a 3pp move draws the caption")
    }

    func testTheAbsencesDrawNoCaption() {
        // No opening at all — the caption has nothing to open on.
        XCTAssertNil(SinceOpenCaption.caption(
            away: 0.055, home: 0.945,
            servedAwayPercent: nil, servedHomePercent: nil,
            openingAway: nil, openingHome: nil,
            sport: twoWay, names: names))

        // No current price.
        XCTAssertNil(SinceOpenCaption.caption(
            away: nil, home: nil,
            servedAwayPercent: nil, servedHomePercent: nil,
            openingAway: 0.0871, openingHome: 0.9129,
            sport: twoWay, names: names))

        // DELIBERATE, and pinned so nobody restores it by accident: a two-way
        // sport with a home opening and no away opening. The `Opened` line
        // itself draws nothing here, and deriving `1 − home` for the caption
        // would put a number on screen no other line agrees with — the
        // re-derivation `printablePair` documents as the trap. Half a caption
        // is worse than none.
        XCTAssertNil(SinceOpenCaption.caption(
            away: 0.055, home: 0.945,
            servedAwayPercent: nil, servedHomePercent: nil,
            openingAway: nil, openingHome: 0.9129,
            sport: twoWay, names: names))
    }

    func testADrawPricedSportStillCaptionsWithoutAnAwayOpening() throws {
        // The same absence is NOT an absence on a draw-priced sport: the away
        // slot is withheld by design at both ends, so the subject is home and
        // both its levels are present. The guard above must not have taken this
        // population with it.
        let caption = try XCTUnwrap(SinceOpenCaption.caption(
            away: nil, home: 0.72,
            servedAwayPercent: nil, servedHomePercent: nil,
            openingAway: nil, openingHome: 0.60,
            sport: drawPriced, names: names))

        XCTAssertEqual(caption.text, "Sabalenka 60% \u{2192} 72% since open")
    }
}
