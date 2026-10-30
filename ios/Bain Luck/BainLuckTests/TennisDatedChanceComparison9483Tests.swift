import XCTest
@testable import Bain_Luck

/// #9483 tennis — **a tennis history reader shows the inspected and the
/// earlier recorded chances equally readable, each with its own date, and
/// keeps gaps and missing values explicit.**
///
/// The comparison only presents what `TennisChartReading9483` already
/// resolved, so these tests drive it with resolved readings and check it
/// prints exactly that: the helper's labels, headings, times and row order,
/// never a re-resolved, borrowed or rounded value.
///
/// Readings are CONSTRUCTED controls. The 97.72 / 2.27 and 55.99 / 44.01
/// pairs are the numeric reference values of captured event 15310688
/// (Zverev–Shelton, v457/v462 design reference), used as numbers only — not a
/// production capture. The 60 / 35 consensus pair is the existing contract of
/// `TennisRecordedChanceBeforeScheduledStart9483Tests`. Unexecuted until
/// Native's Apple run.
@MainActor
final class TennisDatedChanceComparison9483Tests: XCTestCase {
    private typealias R = TennisChartReading9483
    private typealias C = TennisDatedChanceComparison9483

    /// 2026-09-13T18:00:00Z — the scheduled start.
    private let start = Date(timeIntervalSince1970: 1_789_322_400)
    private let utc = TimeZone(identifier: "UTC")!
    private let us = Locale(identifier: "en_US")
    private let event = 15_310_688

    private func at(_ minutes: Double) -> Date { start.addingTimeInterval(minutes * 60) }

    private func reading(_ minutes: Double, _ home: Double, _ away: Double?,
                         source: String = "consensus", eventId: Int? = nil) -> R.Reading {
        R.Reading(eventId: eventId ?? event, source: source, date: at(minutes), home: home, away: away)
    }

    /// Numeric reference controls: the inspected 97.72 / 2.27 and the earlier
    /// 55.99 / 44.01, each at its own time.
    private var inspected: R.Reading { reading(190, 0.9772, 0.0227) }
    private var earlier: R.Reading { reading(-60, 0.5599, 0.4401) }

    private func parts(_ shown: R.Shown, baseline: R.Reading?, offersLatest: Bool = false,
                       canShowLatest: Bool = true, now: Date? = nil) -> [C.Part] {
        C.parts(shown: shown, baseline: baseline, scheduledStart: start, offersLatest: offersLatest,
                canShowLatest: canShowLatest, now: now ?? start, timeZone: utc, locale: us)
    }

    private func pairs(_ parts: [C.Part]) -> [C.Pair] {
        parts.compactMap { if case .pair(let pair) = $0 { return pair } else { return nil } }
    }

    private func notes(_ parts: [C.Part]) -> [String] {
        parts.compactMap { if case .note(let text) = $0 { return plain(text) } else { return nil } }
    }

    private func plain(_ s: String) -> String {
        s.replacingOccurrences(of: "\u{202F}", with: " ").replacingOccurrences(of: "\u{00A0}", with: " ")
    }

    // MARK: - Both dated pairs, exact values and times

    func testTheInspectedAndEarlierPairsPrintTheirOwnValuesAndTimes() throws {
        let laid = parts(.reading(inspected, held: true), baseline: earlier)
        XCTAssertEqual(laid.count, 3)
        XCTAssertEqual(laid.first, .names, "the names head both pairs, once")
        let printed = pairs(laid)
        XCTAssertEqual(printed.map(\.key), [.solid, .hollow], "inspected first and solid, earlier under it and hollow")
        let now = try XCTUnwrap(printed.first)
        let then = try XCTUnwrap(printed.last)
        XCTAssertEqual(plain(now.heading), "Recorded chance · 9:10 PM")
        XCTAssertEqual(plain(then.heading), "Before scheduled start · 5:00 PM")
        XCTAssertEqual(now.heading, R.heading(for: inspected, scheduledStart: start, now: start,
                                              timeZone: utc, locale: us))
        XCTAssertEqual(then.heading, R.baselineHeading(for: earlier, now: start, timeZone: utc, locale: us))
        // The figures are the helper's own labels, unrounded further.
        XCTAssertEqual(now.home, R.labels(for: inspected).home)
        XCTAssertEqual(now.away, R.labels(for: inspected).away)
        XCTAssertEqual(then.home, R.labels(for: earlier).home)
        XCTAssertEqual(then.away, "44%", "the earlier side it supplied, not a complement")
        // Each pair keeps the resolved reading it shows: event, source, time.
        XCTAssertEqual(now.reading, inspected)
        XCTAssertEqual(then.reading, earlier)
        XCTAssertNotEqual(now.reading.date, then.reading.date)
    }

    /// An archived match's pairs are dated, not just timed. The date helper
    /// prints month and day without a year (owner obligation, unchanged here).
    func testAnArchivedPairCarriesItsDate() throws {
        let later = start.addingTimeInterval(3 * 86_400)
        let printed = pairs(parts(.reading(inspected, held: true), baseline: earlier, now: later))
        XCTAssertTrue(plain(try XCTUnwrap(printed.first).heading).hasPrefix("Recorded chance · Sep 13"))
        XCTAssertTrue(plain(try XCTUnwrap(printed.last).heading).hasPrefix("Before scheduled start · Sep 13"))
    }

    // MARK: - The same pair once; equal values at another time twice

    func testTheBaselineShownAsTheReadingPrintsOnce() throws {
        let laid = parts(.reading(earlier, held: true), baseline: earlier)
        XCTAssertEqual(laid.count, 2, "\(laid)")
        let only = try XCTUnwrap(pairs(laid).first)
        XCTAssertEqual(only.key, .solid)
        XCTAssertEqual(plain(only.heading), "Recorded chance before scheduled start · 5:00 PM")
        XCTAssertTrue(notes(laid).isEmpty, "a baseline exists, so no 'unavailable' note")
    }

    func testEqualValuesAtAnotherTimeStayTwoPairs() {
        let same = reading(10, earlier.home, earlier.away)
        let printed = pairs(parts(.reading(same, held: true), baseline: earlier))
        XCTAssertEqual(printed.count, 2, "two observations at two times are two pairs")
        XCTAssertEqual(printed.map { $0.reading.date }, [at(10), at(-60)])
        XCTAssertEqual(printed[0].home, printed[1].home)
        XCTAssertNotEqual(printed[0].heading, printed[1].heading)
    }

    // MARK: - Each side by its source's contract

    func testTheConsensusPairStaysIndependent() throws {
        let pair = try XCTUnwrap(pairs(parts(.reading(reading(0, 0.60, 0.35), held: true), baseline: earlier)).first)
        XCTAssertEqual(pair.home, "60%")
        XCTAssertEqual(pair.away, "35%", "the away side was rewritten as 1 − home")
    }

    func testAMissingSuppliedAwayStaysUnavailable() throws {
        let missing = reading(21, 0.63, nil)
        let pair = try XCTUnwrap(pairs(parts(.reading(missing, held: true), baseline: earlier)).first)
        XCTAssertEqual(pair.home, "63%")
        XCTAssertNil(pair.away, "a missing side printed a number")
        let words = C.spoken(pair, homeName: "Alexander Zverev", awayName: "Ben Shelton")
        XCTAssertTrue(words.hasSuffix("Ben Shelton Unavailable"), words)
        XCTAssertFalse(words.contains("37%"), "1 − home was borrowed")
        XCTAssertFalse(words.contains("0%"), words)
        // CONTROL — the blend prints its complement, by the helper's rule.
        let blend = try XCTUnwrap(pairs(parts(.reading(reading(21, 0.63, nil, source: "aggregate"), held: true),
                                              baseline: earlier)).first)
        XCTAssertEqual(blend.away, "37%")
        XCTAssertEqual(blend.away, R.labels(for: blend.reading).away)
    }

    // MARK: - A gap or a gone reading keeps the earlier pair

    func testAGapPrintsNoRecordedChanceAndKeepsTheBaseline() {
        let laid = parts(.gap(at(100)), baseline: earlier)
        XCTAssertEqual(laid.first, .names)
        XCTAssertEqual(notes(laid), ["No recorded chance at 7:40 PM"])
        XCTAssertEqual(pairs(laid).map(\.key), [.hollow], "no neighbour across the break was printed")
        XCTAssertEqual(pairs(laid).first?.reading, earlier)
    }

    func testAnUnavailableReadingKeepsTheBaselineAndNeverTheLatest() {
        let laid = parts(.unavailable, baseline: earlier, offersLatest: true)
        XCTAssertEqual(notes(laid), [R.unavailableText])
        XCTAssertEqual(pairs(laid).map(\.reading), [earlier], "only the earlier pair prints")
        XCTAssertEqual(laid.last, .showLatest, "the latest is the reader's choice, never filled in")
    }

    // MARK: - No baseline

    func testNoBaselineSaysTheEarlierComparisonIsUnavailable() {
        let laid = parts(.reading(inspected, held: true), baseline: nil)
        XCTAssertEqual(pairs(laid).map(\.key), [.solid])
        XCTAssertEqual(notes(laid), [C.earlierUnavailableText])
        for note in notes(laid) {
            XCTAssertFalse(note.localizedCaseInsensitiveContains("pre-match"), note)
            XCTAssertFalse(note.localizedCaseInsensitiveContains("before"), "it claimed a pre-start reading")
        }
    }

    func testWithNoNumbersTheAbsenceIsReadable() {
        XCTAssertEqual(parts(.unavailable, baseline: nil),
                       [.note(R.unavailableText), .note(C.earlierUnavailableText)],
                       "no names head an empty comparison")
        XCTAssertEqual(notes(parts(.gap(at(100)), baseline: nil)),
                       ["No recorded chance at 7:40 PM", C.earlierUnavailableText])
    }

    // MARK: - Show latest: the owner offers it and supplies the action

    func testShowLatestNeedsTheOwnersOfferAndAnAction() {
        let offered = parts(.reading(inspected, held: true), baseline: earlier, offersLatest: true)
        XCTAssertEqual(offered.last, .showLatest)
        XCTAssertEqual(offered.filter { $0 == .showLatest }.count, 1)
        XCTAssertEqual(offered.dropLast().compactMap { if case .pair = $0 { return 1 } else { return nil } }.count, 2,
                       "Show latest sits after both pairs")
        XCTAssertFalse(parts(.reading(inspected, held: true), baseline: earlier, offersLatest: true,
                             canShowLatest: false).contains(.showLatest), "no action, no control")
        XCTAssertFalse(parts(.reading(inspected, held: true), baseline: earlier, offersLatest: false)
                        .contains(.showLatest), "the owner did not offer it")
    }

    func testTheViewCallsTheOwnersAction() {
        var calls = 0
        let view = TennisDatedChanceComparisonView9483(
            shown: .reading(inspected, held: true), baseline: earlier, scheduledStart: start,
            homeName: "Zverev", awayName: "Shelton", homeColor: .blue, awayColor: .green,
            offersLatest: true, onShowLatest: { calls += 1 }, now: start)
        view.onShowLatest?()
        XCTAssertEqual(calls, 1)
        let silent = TennisDatedChanceComparisonView9483(
            shown: .reading(inspected, held: true), baseline: earlier, scheduledStart: start,
            homeName: "Zverev", awayName: "Shelton", homeColor: .blue, awayColor: .green, now: start)
        XCTAssertNil(silent.onShowLatest)
        XCTAssertFalse(silent.offersLatest)
    }

    // MARK: - What a screen reader hears

    func testEachPairIsSpokenWithItsMeaningTimeAndBothNamedValues() throws {
        let printed = pairs(parts(.reading(inspected, held: true), baseline: earlier))
        let now = try XCTUnwrap(printed.first)
        let then = try XCTUnwrap(printed.last)
        let labels = R.labels(for: inspected)
        XCTAssertEqual(plain(C.spoken(now, homeName: "Alexander Zverev", awayName: "Ben Shelton")),
                       "Recorded chance · 9:10 PM, Alexander Zverev \(labels.home), Ben Shelton \(labels.away)")
        XCTAssertEqual(plain(C.spoken(then, homeName: "Alexander Zverev", awayName: "Ben Shelton")),
                       "Before scheduled start · 5:00 PM, Alexander Zverev \(R.labels(for: earlier).home), Ben Shelton 44%")
        for words in [now, then].map({ C.spoken($0, homeName: "Alexander Zverev", awayName: "Ben Shelton") }) {
            for retired in ["In game", "in game", "pre-match", "Pre-match", "Last"] {
                XCTAssertFalse(words.contains(retired), "\(retired) in \(words)")
            }
        }
    }
}
