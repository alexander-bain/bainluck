import XCTest
@testable import Bain_Luck

/// #7759 — the Accuracy screen's corrections log printed engineer shorthand
/// where the website prints sentences.
///
/// The card is a trust panel: it is the page telling a reader what we got wrong
/// and fixed. It rendered the payload's `title` verbatim, so the app published
///
///     Polymarket hockey sign-flip
///     Malformed-binary exclusion
///     Kalshi player-prop threshold exclusion — corrected discriminator (Queue #186)
///
/// and, under each, the backend auditor's paragraph — `(gotcha #17) … poly MCE
/// 4.68 → 4.01`, `Queue #186 (2026-07-13) corrects the Queue #167 filter`. Web
/// dropped the paragraph in #4067 / CERT-2295 and moved off the raw title in
/// #7729/#7734; the app did neither.
///
/// ## What is actually being asserted
///
/// Not "the helper returns the right string for the string I passed it" — that
/// passes against a helper nobody calls, which is the failure web's own
/// component test was written for. The load-bearing test here is
/// `testEveryTitleProductionServesReachesAReaderInEnglish`: it runs the THIRTEEN
/// titles production served through the render path and requires that none of
/// them reaches a reader carrying a tracker id or as raw shorthand.
///
/// The other half of the coupling — that the view calls this at all, and that it
/// no longer prints `description` — is asserted in
/// `frontend/__tests__/ios/correctionsLogCopyParity7759.test.ts`, because jest is
/// a deploy gate here and the Swift target is not reachable from CI (notice 10's
/// iOS clause). That file also pins this map's key set against web's, so a tenth
/// entry on one surface reddens rather than silently diverging.
final class CorrectionsLogReadsInEnglish7759Tests: XCTestCase {

    // MARK: - The corpus, measured rather than imagined

    /// Every `corrections[].title` production served on 2026-09-21,
    /// `generated_at` 2026-09-15T11:16:10Z, in payload order. Re-measure with:
    ///
    /// ```
    /// curl -s "$BAINLUCK_API/api/calibration" \
    ///   | python3 -c "import json,sys; [print(repr(c['title'])) for c in json.load(sys.stdin)['corrections']]"
    /// ```
    private static let producerTitles = [
        "Polymarket hockey sign-flip",
        "Premature golf resolutions",
        "DataGolf survivorship exclusion",
        "Polymarket no-bid placeholder exclusion",
        "Malformed-binary exclusion",
        "Golf FIELD one-sided-ask placeholder exclusion",
        "Multi-candidate probability normalization",
        "Soccer 2-way (draw-omission) historical exclusion",
        "Esports match-bundle exclusion",
        "Kalshi player-prop threshold exclusion — corrected discriminator (Queue #186)",
        "Prices nobody could have traded at",
        "A price ladder is one forecast, not forty",
        "The one-question markets we were throwing away are now scored",
    ]

    /// The one title on that list whose shorthand also quotes our own tracker.
    private static let trackerSpecimen =
        "Kalshi player-prop threshold exclusion — corrected discriminator (Queue #186)"

    // MARK: - The ship

    /// Nothing production publishes reaches a reader as shorthand or with an id.
    func testEveryTitleProductionServesReachesAReaderInEnglish() {
        for title in Self.producerTitles {
            let rendered = CalibrationCorrections.title(title)

            XCTAssertFalse(
                CalibrationCorrections.carriesInternalReference(rendered),
                "rendered copy still quotes our tracker: \(rendered)"
            )
            XCTAssertFalse(rendered.isEmpty, "a served title rendered as nothing: \(title)")
        }
    }

    /// The nine the map has words for are REPLACED, not merely cleaned up.
    ///
    /// A withhold-only implementation passes the test above on eight of the nine
    /// (they carry no id to strip) while leaving "Malformed-binary exclusion" on
    /// the screen exactly as it was. This is the clause that tells the two apart.
    func testTheMappedTitlesAreReplacedWithTheirSentences() {
        for (producer, reader) in CalibrationCorrections.titleOverrides {
            XCTAssertEqual(CalibrationCorrections.title(producer), reader)
            XCTAssertNotEqual(
                CalibrationCorrections.title(producer), producer,
                "the map returned the producer's own words for \(producer)"
            )
        }
    }

    /// The specimen #7729 named, end to end.
    func testTheKalshiSpecimenLosesBothTheJargonAndTheQueueNumber() {
        let rendered = CalibrationCorrections.title(Self.trackerSpecimen)

        XCTAssertEqual(
            rendered, "Player-prop prices (Kalshi): corrected the test for which prices to drop"
        )
        XCTAssertFalse(rendered.contains("Queue"))
        XCTAssertFalse(rendered.lowercased().contains("discriminator"))
        // And it is the MAP doing this, not the floor: the floor's own answer
        // keeps "corrected discriminator", which is still jargon in a slot the
        // page controls. If these ever agree, the map entry has been lost.
        XCTAssertNotEqual(
            rendered, CalibrationCorrections.withheldInternalReference(Self.trackerSpecimen)
        )
    }

    /// Every served row is running on chosen copy, not on the floor.
    func testNoServedRowIsRunningOnTheFloor() {
        let corrections = Self.producerTitles.map {
            CalibrationCorrection(date: "2026-07-09", title: $0, rows: nil, description: "")
        }
        XCTAssertEqual(CalibrationCorrections.needingCopy(corrections), 0)
    }

    // MARK: - Reading order (#7763)

    /// The one row the served payload has out of place moves, and only it.
    func testTheOutOfPlaceRowMovesToTheTopAndNothingElseMoves() {
        let served = Self.servedCorrections()
        let ordered = CalibrationCorrections.ordered(served)

        // 2026-07-08 is published SECOND and belongs first.
        XCTAssertEqual(served[1].date, "2026-07-08", "the payload corpus no longer holds the defect")
        XCTAssertEqual(ordered.first?.date, "2026-07-08")

        // Exactly one row changed index — the claim an after-screenshot can check.
        let moved = zip(served, ordered).filter { $0.id != $1.id }.count
        XCTAssertEqual(moved, 2, "a one-row insertion shifts that row and the one it displaced")
        XCTAssertEqual(Set(ordered.map(\.id)), Set(served.map(\.id)), "ordering dropped or invented a row")
    }

    /// Dates come out ascending.
    func testTheLogReadsOldestFirst() {
        let dates = CalibrationCorrections.ordered(Self.servedCorrections()).map(\.date)
        XCTAssertEqual(dates, dates.sorted())
        XCTAssertEqual(dates.first, "2026-07-08")
        XCTAssertEqual(dates.last, "2026-09-13")
    }

    /// Rows sharing a date keep the order the backend published them in.
    ///
    /// `Swift.sort` is NOT stable — unlike the `Array.prototype.sort` web's twin
    /// relies on — so this is the clause that fails if the comparator ever drops
    /// its index tie-break and starts trusting the standard library. Five served
    /// rows share `2026-07-09`, which is enough for introsort to actually reorder
    /// them rather than coincidentally not.
    func testRowsSharingADateKeepTheirPublishedOrder() {
        let served = Self.servedCorrections()
        let ordered = CalibrationCorrections.ordered(served)

        for date in ["2026-07-09", "2026-09-12"] {
            let before = served.filter { $0.date == date }.map(\.title)
            let after = ordered.filter { $0.date == date }.map(\.title)
            XCTAssertGreaterThan(before.count, 1, "\(date) is no longer a tie — pick another")
            XCTAssertEqual(after, before, "rows sharing \(date) were reordered")
        }
    }

    /// An empty log stays empty rather than becoming a crash or a phantom row.
    func testOrderingAnEmptyLogIsEmpty() {
        XCTAssertTrue(CalibrationCorrections.ordered([]).isEmpty)
    }

    /// The thirteen rows production served, with their dates, in payload order.
    private static func servedCorrections() -> [CalibrationCorrection] {
        let dates = [
            "2026-07-09", "2026-07-08", "2026-07-09", "2026-07-09", "2026-07-09",
            "2026-07-09", "2026-07-10", "2026-07-11", "2026-07-12", "2026-07-13",
            "2026-09-12", "2026-09-12", "2026-09-13",
        ]
        return zip(dates, producerTitles).map {
            CalibrationCorrection(date: $0, title: $1, rows: nil, description: "")
        }
    }

    // MARK: - The floor under the map

    /// A title nobody mapped loses the fragment written for us — and only that.
    func testAnUnmappedTitleWithATrackerIdLosesTheFragmentAndNothingElse() {
        for (input, expected) in [
            ("Some correction (Queue #999)", "Some correction"),
            ("Some correction (CERT-2295)", "Some correction"),
            ("Some correction (see #4067)", "Some correction"),
            ("Some correction — per L2-74", "Some correction"),
        ] {
            let rendered = CalibrationCorrections.title(input)
            XCTAssertEqual(rendered, expected)
            // WITHHELD, never rewritten (#4113): whatever survives is text the
            // producer actually wrote, not words this client invented.
            XCTAssertTrue(
                input.hasPrefix(rendered),
                "the floor rewrote rather than withheld: \(input) -> \(rendered)"
            )
        }
    }

    /// A title carrying no tracker id passes through untouched.
    ///
    /// The three September entries are already reader sentences and the map has
    /// no words for them; a floor that trimmed on any dash or parenthesis would
    /// silently edit copy that was already right.
    func testATitleWithNoTrackerIdIsUntouched() {
        for title in [
            "Prices nobody could have traded at",
            "A price ladder is one forecast, not forty",
            "The one-question markets we were throwing away are now scored",
            "Premature golf resolutions",
            // Real reader numbers in the shapes the floor must not eat.
            "Markets priced above 80% in 2026",
            "A 50-cent spread is not a price",
        ] {
            XCTAssertEqual(CalibrationCorrections.title(title), title)
        }
    }

    /// An id in the MIDDLE of a sentence is left alone and counted, not mangled.
    ///
    /// Cutting it would change what the sentence says, so the honest answer is to
    /// leave the row and let `needingCopy` report that it needs words.
    func testAMidSentenceIdIsLeftAloneAndCounted() {
        let title = "Queue #186 changed which prices we score"
        XCTAssertEqual(CalibrationCorrections.title(title), title)
        XCTAssertEqual(
            CalibrationCorrections.needingCopy(
                [CalibrationCorrection(date: "2026-07-13", title: title, rows: nil, description: "")]
            ),
            1
        )
    }

    /// The single-letter arms do not match mid-word.
    ///
    /// Without the `\b` in front of `D` and `q`, these are tracker ids and the
    /// floor starts cutting clauses out of titles that carry none.
    func testSingleLetterPrefixesDoNotMatchInsideWords() {
        for title in ["Rendering fixed for 3D2 charts", "Iraq2024 market resolution"] {
            XCTAssertFalse(CalibrationCorrections.carriesInternalReference(title), title)
            XCTAssertEqual(CalibrationCorrections.title(title), title)
        }
    }

    /// An empty or absent title renders as nothing rather than as a crash.
    func testAnAbsentTitleRendersAsNothing() {
        XCTAssertEqual(CalibrationCorrections.title(nil), "")
        XCTAssertEqual(CalibrationCorrections.title(""), "")
    }

    // MARK: - The detector cannot fail open unnoticed

    /// `try?` on the patterns means a bad edit yields nil, and a nil DETECTOR
    /// answers "no tracker id" for everything — the floor would stop existing
    /// with no test failing. This is that test.
    func testThePatternsCompiled() {
        XCTAssertTrue(CalibrationCorrections.patternsCompiled)
        XCTAssertTrue(
            CalibrationCorrections.carriesInternalReference("Some correction (Queue #999)"),
            "the detector answered no on a title that plainly carries one"
        )
    }
}
