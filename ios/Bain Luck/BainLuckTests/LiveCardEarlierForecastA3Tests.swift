import SwiftUI
import XCTest
@testable import Bain_Luck

/// #9483 A3 + #11296 caption hierarchy (Design disposition, 2026-10-22).
///
/// PILLARS: TRUTH / FORMATTING. SHIP: the current forecast stays visually
/// primary, and the live native card names a historical fallback without
/// claiming unproved pregame timing.
///
/// What these pin, and the mutation each kills:
/// - a live card on the history point saying "pregame projection" / "before
///   kickoff" (the floor is the first OBSERVED game state, not kickoff) →
///   `testALiveHistoryCardIsNamedEarlierForecastEverywhere`
/// - "still" from a level earlier pair, or a flip from one →
///   `testTheLiveSentenceFollowsDesignsTableOnTheHistoryPoint`
/// - the old pair read as current when no current projection prints →
///   `testTheLiveSentenceFollowsDesignsTableOnTheHistoryPoint`,
///   `testTheSpokenCardSaysTheMissingCurrentProjection`
/// - the live card ignoring the headline's admitted retained pair →
///   `testALiveCardComparesWithTheHeadlinesAdmittedPair`,
///   `testThePageHandsTheCardTheHeadlinesOwnLiveDecision`
/// - a live baseline leaking into a pregame or finished card →
///   `testTheLiveBaselineIsReadOnlyWhileLive`
/// - the retained pair drawn larger than the current caption above it (AX2–AX5,
///   Design's 393 renders) → `testTheRetainedPairNeverOutgrowsTheCurrentCaption`,
///   `testThePairedRowGivesTheRetainedPairTheCaptionsFontAndCeiling`
@MainActor
final class LiveCardEarlierForecastA3Tests: XCTestCase {

    private static let start = Date(timeIntervalSince1970: 1_792_000_000)

    private func pair(_ minutes: Double, home: Double, away: Double) -> ProjectedFinalPointsSeries.Pair {
        .init(at: Self.start.addingTimeInterval(minutes * 60), home: home, away: away, homeProbability: nil,
              kind: .recorded)
    }

    /// Home GB, away DAL: the last point before the first observed state is
    /// GB 27.5–26.5; live at +65 min the newest is GB 25–17 unless `stale`.
    private func input(phase: NFLFinishCard9483.Phase, stale: Bool = false,
                       sport: String = "americanfootball_nfl") -> ProjectedFinalPointsSeries.Input {
        let final = phase == .after
        let pairs = phase == .before ? [pair(-30, home: 27.5, away: 26.5)]
            : [pair(-30, home: 27.5, away: 26.5), pair(60, home: 25, away: 17)]
        let asOf: Double = phase == .before ? -10 : final ? 200 : stale ? 60 + 61 : 65
        return .init(sportKey: sport, sourceKey: "draftkings", basis: .sameBookSameCaptureFullGameSpreadAndTotal,
                     pairs: pairs,
                     actuals: final ? [.init(at: Self.start.addingTimeInterval(200 * 60), home: 23, away: 13)] : [],
                     kickoffAt: nil, scoreObservationStartAt: phase == .before ? nil : Self.start,
                     finalAt: final ? Self.start.addingTimeInterval(200 * 60) : nil,
                     asOf: Self.start.addingTimeInterval(asOf * 60), windowStartAt: nil, requestCutoffAt: nil)
    }

    /// The live headline's admitted retained pair: away 27.6 / home 26.5.
    private let admitted = (away: 27.6, home: 26.5)

    private func card(_ phase: NFLFinishCard9483.Phase, pregame: (away: Double, home: Double),
                      now: (away: Double, home: Double)?,
                      basis: NFLFinishCard9483.PregameBasis = .history) -> NFLFinishCard9483 {
        NFLFinishCard9483(phase: phase, pregame: .init(away: pregame.away, home: pregame.home, at: nil),
                          projectedNow: now.map { .init(away: $0.away, home: $0.home, at: nil) }, final: nil,
                          pregameBasis: basis)
    }

    // MARK: - History fallback

    func testALiveHistoryCardIsNamedEarlierForecastEverywhere() throws {
        let live = try XCTUnwrap(NFLFinishCard9483.build(input(phase: .during)))
        XCTAssertEqual(live.phase, .during, "control: live")
        XCTAssertNotNil(live.projectedNow, "control: a current projection")
        XCTAssertEqual(live.pregameBasis, .history)
        XCTAssertEqual(live.pregame.home, 27.5, "the history point is kept unchanged")
        XCTAssertEqual(live.pregame.at, Self.start.addingTimeInterval(-30 * 60), "its own clock, unedited")
        XCTAssertTrue(live.namesDistinctBasis)
        XCTAssertEqual(live.pregameName, "Earlier forecast")
        XCTAssertEqual(live.pregameLabel, "earlier forecast")
        XCTAssertEqual(live.key, "Points · outline = earlier forecast · filled = projected now")
        XCTAssertNil(live.missingCurrentNote)
        XCTAssertNil(live.ladderPregame, "no history pair reaches the NBA ladders' \"Pregame projection\"")
        for claim in ["pregame", "kickoff", "before"] {
            XCTAssertFalse(live.key.lowercased().contains(claim), "the key claims \"\(claim)\"")
            XCTAssertFalse(live.headline(awayName: "Cowboys", homeName: "Packers").lowercased().contains(claim))
        }
        // Before the game the latest IS the pregame projection: unchanged.
        let before = try XCTUnwrap(NFLFinishCard9483.build(input(phase: .before)))
        XCTAssertEqual(before.phase, .before, "control: before")
        XCTAssertEqual(before.pregameLabel, "pregame projection")
        XCTAssertEqual(before.key, "Projected points")
        XCTAssertNil(before.missingCurrentNote)
        XCTAssertEqual(before.ladderPregame?.home, 27.5)
    }

    func testTheLiveSentenceFollowsDesignsTableOnTheHistoryPoint() {
        let a = "Cowboys", h = "Packers"
        // Current projection unavailable: the earlier pair is named, never current.
        let missing = card(.during, pregame: (away: 20, home: 24), now: nil)
        XCTAssertEqual(missing.headline(awayName: a, homeName: h), "Packers led the earlier forecast")
        XCTAssertEqual(missing.missingCurrentNote, "No recent projection update")
        XCTAssertEqual(missing.key, "Points · outline = earlier forecast")
        XCTAssertEqual(card(.during, pregame: (away: 21, home: 21), now: nil).headline(awayName: a, homeName: h),
                       "Earlier forecast was level")
        // Current tied.
        XCTAssertEqual(card(.during, pregame: (away: 20, home: 24), now: (away: 23, home: 23))
                        .headline(awayName: a, homeName: h), "The projected finish is level")
        // Opposite strict leaders: the two forecasts, not the actual score.
        XCTAssertEqual(card(.during, pregame: (away: 20, home: 24), now: (away: 27, home: 23))
                        .headline(awayName: a, homeName: h), "The projected finish has flipped")
        // Same strict leader.
        XCTAssertEqual(card(.during, pregame: (away: 20, home: 24), now: (away: 17, home: 25))
                        .headline(awayName: a, homeName: h), "Packers still projected ahead")
        // Level earlier pair, current has a leader: "now", never "still" or a flip.
        for now in [(away: 27.0, home: 23.0), (away: 17.0, home: 25.0)] {
            let line = card(.during, pregame: (away: 21, home: 21), now: now).headline(awayName: a, homeName: h)
            XCTAssertEqual(line, "\(now.home > now.away ? h : a) now projected ahead")
        }
    }

    func testTheSpokenCardSaysTheMissingCurrentProjection() throws {
        let stale = try XCTUnwrap(NFLFinishCard9483.build(input(phase: .during, stale: true)))
        XCTAssertNil(stale.projectedNow, "control: the newest capture is past its gap")
        XCTAssertEqual(stale.missingCurrentNote, NFLFinishCard9483.noRecentProjectionUpdate)
        XCTAssertNil(stale.withoutProjectedNow.projectedNow)
        XCTAssertEqual(card(.during, pregame: (away: 20, home: 24), now: (away: 17, home: 25))
                        .withoutProjectedNow.missingCurrentNote, "No recent projection update",
                       "an expired live projection leaves the note in its place")
        let view = try source("Components/NFLEventCards9483.swift")
        XCTAssertTrue(view.contains("ifletnote=card.missingCurrentNote{parts.append(note)}"), "spoken")
        XCTAssertTrue(view.contains("ifletnote=card.missingCurrentNote{Text(note)"), "drawn")
        XCTAssertTrue(view.contains("\"\\(card.pregameName)\""), "the spoken intro is the card's own name")
    }

    // MARK: - The headline's admitted retained pair

    func testALiveCardComparesWithTheHeadlinesAdmittedPair() throws {
        let live = try XCTUnwrap(NFLFinishCard9483.build(input(phase: .during), liveBaseline: admitted))
        XCTAssertEqual(live.phase, .during)
        XCTAssertEqual(live.pregameBasis, .scheduledStart)
        XCTAssertEqual(live.pregame.away, 27.6, "keyed by team, never by value")
        XCTAssertEqual(live.pregame.home, 26.5)
        XCTAssertNil(live.pregame.at, "a capture range claims no single clock")
        XCTAssertEqual(live.projectedNow?.home, 25, "the current projection is the history's own, unedited")
        XCTAssertFalse(live.namesDistinctBasis)
        XCTAssertEqual(live.pregameName, FinalForecastComparison11296.label, "the headline's qualified words")
        XCTAssertEqual(live.pregameLabel, "projection before scheduled start")
        XCTAssertEqual(live.key, "Points · outline = projection before scheduled start · filled = projected now")
        XCTAssertEqual(live.ladderPregame?.away, 27.6, "the NBA companions read the same admitted pair")
        XCTAssertEqual(live.ladderPregame?.home, 26.5)
        // DAL ahead before the start, GB ahead now.
        XCTAssertEqual(live.headline(awayName: "Cowboys", homeName: "Packers"), "The projected finish has flipped")
        XCTAssertEqual(live.withoutProjectedNow.pregameBasis, .scheduledStart, "expiry keeps the basis")

        let a = "Cowboys", h = "Packers"
        let missing = card(.during, pregame: (away: 27.6, home: 26.5), now: nil, basis: .scheduledStart)
        XCTAssertEqual(missing.headline(awayName: a, homeName: h), "Cowboys led the forecast before scheduled start")
        XCTAssertEqual(missing.missingCurrentNote, "No recent projection update")
        XCTAssertEqual(card(.during, pregame: (away: 24, home: 24), now: nil, basis: .scheduledStart)
                        .headline(awayName: a, homeName: h), "Forecast before scheduled start was level")
        XCTAssertEqual(card(.during, pregame: (away: 24, home: 24), now: (away: 17, home: 25), basis: .scheduledStart)
                        .headline(awayName: a, homeName: h), "Packers now projected ahead")
        XCTAssertEqual(card(.during, pregame: (away: 20, home: 24), now: (away: 17, home: 25), basis: .scheduledStart)
                        .headline(awayName: a, homeName: h), "Packers still projected ahead")

        // A refused pair keeps the history point, named for what it is.
        let refused = try XCTUnwrap(NFLFinishCard9483.build(input(phase: .during), liveBaseline: (away: .nan, home: 26.5)))
        XCTAssertEqual(refused.pregameBasis, .history)
        XCTAssertEqual(refused.pregameLabel, "earlier forecast")
        // The pair never creates a card the history refuses.
        var noHistory = input(phase: .during)
        noHistory = .init(sportKey: noHistory.sportKey, sourceKey: noHistory.sourceKey, basis: noHistory.basis,
                          pairs: [pair(60, home: 25, away: 17)], actuals: [], kickoffAt: nil,
                          scoreObservationStartAt: Self.start, finalAt: nil, asOf: noHistory.asOf,
                          windowStartAt: nil, requestCutoffAt: nil)
        XCTAssertNil(NFLFinishCard9483.build(noHistory, liveBaseline: admitted))
    }

    func testTheLiveBaselineIsReadOnlyWhileLive() throws {
        let before = try XCTUnwrap(NFLFinishCard9483.build(input(phase: .before), liveBaseline: admitted))
        XCTAssertEqual(before, try XCTUnwrap(NFLFinishCard9483.build(input(phase: .before))))
        let after = try XCTUnwrap(NFLFinishCard9483.build(input(phase: .after), liveBaseline: admitted))
        XCTAssertEqual(after.phase, .after, "control: final")
        XCTAssertEqual(after, try XCTUnwrap(NFLFinishCard9483.build(input(phase: .after))))
        XCTAssertEqual(after.pregameLabel, "earlier forecast", "the finished fallback is unchanged")
        XCTAssertEqual(after.key, "Points · outline = earlier forecast · cross = final")
        let qualified = try XCTUnwrap(NFLFinishCard9483.build(input(phase: .after), finalBaseline: admitted))
        XCTAssertEqual(qualified.pregameLabel, "pregame projection", "the finished qualified card keeps its words")
        XCTAssertEqual(qualified.key, "Points · outline = pregame · cross = final")
        XCTAssertNil(qualified.missingCurrentNote, "a final is not a missing projection")
    }

    func testThePageHandsTheCardTheHeadlinesOwnLiveDecision() throws {
        let page = try source("Views/EventDetailView.swift")
        let body = try XCTUnwrap(page.range(
            of: "privatefuncliveCardBaseline11296(_served:EventDetail)->(away:Double,home:Double)?{"))
        XCTAssertTrue(page[body.upperBound...].hasPrefix(
            "letevent=vm.headline(served)"
            + "lethasScore=EventDetailView.showsScore(status:event.status,away:event.awayScore,home:event.homeScore)"
            + "guardliveForecast11296(event,hasScore:hasScore)?.baseline!=nil,"
            + "letaway=event.pregameProjection?.projectedAwayScore,"
            + "lethome=event.pregameProjection?.projectedHomeScoreelse{returnnil}"
            + "return(away:away,home:home)}"),
                      "exactly when the headline prints its admitted pair, that pair's served halves")
        XCTAssertEqual(page.components(separatedBy: "liveCardBaseline11296(").count - 1, 2, "defined once, read once")
        XCTAssertTrue(page.contains("liveBaseline:liveCardBaseline11296(event))"))
    }

    // MARK: - Caption hierarchy

    func testThePairedRowGivesTheRetainedPairTheCaptionsFontAndCeiling() throws {
        let page = try source("Views/EventDetailView.swift")
        XCTAssertTrue(page.contains(
            "LivePregameBaselineLine11296(comparison:liveBaseline,awayName:names.away,homeName:names.home,font:.caption2)"
            + ".dynamicTypeSize(...Self.nflPairedCaptionTypeCeiling).padding(.top,4)"))
        // The current caption it matches: the same font and ceiling.
        XCTAssertTrue(page.contains("label.font(.caption2).foregroundStyle(.secondary).lineLimit(1).minimumScaleFactor(0.5)"
                                    + ".dynamicTypeSize(...Self.nflPairedCaptionTypeCeiling)"))
        let helper = try source("Utilities/LivePregameComparison11296.swift")
        let start = try XCTUnwrap(helper.range(of: "structLivePregameBaselineLine11296:View{"))
        let view = String(helper[start.upperBound...].prefix(900))
        XCTAssertTrue(view.contains("varfont:Font=.caption"), "the generic hero keeps its caption")
        XCTAssertTrue(view.contains(".font(font)"))
        XCTAssertFalse(view.contains("minimumScaleFactor"), "wraps, never shrinks")
        XCTAssertFalse(view.contains("lineLimit"), "wraps, never truncates")
    }

    /// Measured, not read: at every size the retained pair's two lines are each
    /// no taller than the current caption, and it still grows with the reader's
    /// text up to that caption's ceiling.
    func testTheRetainedPairNeverOutgrowsTheCurrentCaption() {
        let comparison = LivePregameComparison11296.Comparison(
            label: FinalForecastComparison11296.label, away: 116, home: 118, bookmakerCount: 19,
            earliestCapturedAt: Self.start, latestCapturedAt: Self.start, scheduledStart: Self.start)
        let ceiling = EventDetailView.nflPairedCaptionTypeCeiling
        let paired = LivePregameBaselineLine11296(comparison: comparison, awayName: "Hawks", homeName: "Magic",
                                                  font: .caption2)
            .dynamicTypeSize(...ceiling)
        let caption = Text("Projected final").font(.caption2).lineLimit(1).dynamicTypeSize(...ceiling)
        let spacing: CGFloat = 2
        for size in [DynamicTypeSize.large, .xxxLarge, .accessibility1, .accessibility2, .accessibility3,
                     .accessibility4, .accessibility5] {
            XCTAssertLessThanOrEqual(height(paired, at: size), 2 * height(caption, at: size) + spacing + 0.5,
                                     "\(size): the retained pair outgrew the current caption")
        }
        XCTAssertGreaterThan(height(paired, at: .accessibility1), height(paired, at: .large),
                             "it still grows with the reader's text")
        // Strawman: the shape the row drew before — the generic caption, uncapped.
        let uncapped = LivePregameBaselineLine11296(comparison: comparison, awayName: "Hawks", homeName: "Magic")
        XCTAssertGreaterThan(height(uncapped, at: .accessibility5),
                             2 * height(caption, at: .accessibility5) + spacing + 0.5,
                             "control: the uncapped line IS larger at AX5, so the bound above bites")
    }

    // MARK: - Helpers

    private func height<V: View>(_ view: V, at size: DynamicTypeSize) -> CGFloat {
        let host = hostForMeasurement(view, at: size)
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        return host.sizeThatFits(in: CGSize(width: 2000, height: CGFloat.greatestFiniteMagnitude)).height
    }

    /// App source with `//` comments and all whitespace removed.
    private func source(_ path: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck")
            .appendingPathComponent(path)
        return try String(contentsOf: url, encoding: .utf8)
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { line -> String in
                guard let slashes = line.range(of: "//") else { return String(line) }
                return String(line[line.startIndex..<slashes.lowerBound])
            }
            .joined(separator: "\n")
            .filter { !$0.isWhitespace }
    }
}
