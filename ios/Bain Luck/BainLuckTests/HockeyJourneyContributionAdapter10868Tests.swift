import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the hockey journey adapter, part three (player points and assists),
/// on REAL served bodies decoded exactly as the app decodes them
/// (`.convertFromSnakeCase`, `APIClient`): `/game-markets` as
/// `GameMarketsResponse`, `/api/events/{id}` as `EventDetail`, and the
/// per-player box as the `[String: [String: Double]]` the props card reads.
/// That box is `/related-futures`' `box_score`, which the server fills from
/// the same `box_score_data["players"]` the detail body serves
/// (`backend/app/routes/events.py`, `box_score_players`); it is decoded here
/// from the detail body's own copy, because `EventBoxScoreData` keeps only the
/// period scores.
///
/// REDUCED VERBATIM SUBSETS. Each kept value — a `player_props` row, a
/// top-level scalar, a box-score player entry, the `espn` block — is the
/// server's bytes, in source order, asserted as a byte-for-byte substring of
/// its source file by `/tmp/cli-10868-h3/make_subsets.py` (run
/// `python3 -I make_subsets.py <design-dir> <out> <manifest>`); only the
/// envelope (which keys, the line breaks between rows) is assembled. Sources
/// under the event-page design directory
/// (`artifacts/discovery-containers-release-plan/event-page-design-20261011/`):
/// - `wildBruinsMarkets` — `atlas-v6/raw/nhl-15169793-game-markets.json`
///   (sha256 3abba0f2…06dc), Minnesota Wild 4–1 Boston Bruins, completed;
///   `player_props` rows 2, 3, 38–42, 47, 48, 59–66 of 83.
/// - `wildBruinsDetail` — `atlas-v6/raw/nhl-15169793-detail.json`
///   (a11c662d…a348); box players Quinn Hughes, Maxim Shabanov, Kirill
///   Kaprizov of 38.
/// - `islandersWildMarkets` — `cli-candidate-20261030/retained-payloads/
///   nhl-15338034-game-markets-20261030T201355Z.json` (0227bebf…29c6), New York
///   Islanders 4–3 Minnesota Wild (Final/OT); rows 0, 1, 10–14, 17, 18,
///   103–105, 108, 109, 118–121, 130, 131 of 140.
/// - `islandersWildDetail` — `…/nhl-15338034-detail-20261030T201355Z.json`
///   (4bd4832c…d6e4); box players Quinn Hughes, Emil Heineman, Maxim Shabanov,
///   Kirill Kaprizov of 38.
/// - `devilsKnightsMarkets` — `…/nhl-15338496-game-markets-20261030T201355Z.json`
///   (8e475781…cd4a), New Jersey Devils at Vegas Golden Knights, scheduled for
///   22:00Z, captured 20:13:55Z; rows 30, 31, 34, 35, 60–65 of 105.
/// - `devilsKnightsDetail` — `…/nhl-15338496-detail-20261030T201355Z.json`
///   (50fbf467…c1da); the served body has no box.
///
/// Census of the FULL retained finals (not only the kept rows): 0 of 83 and 0
/// of 140 player-prop rows serve a null `is_winner` or `resolution_source`, and
/// for every Points/Assists row whose player the box names exactly, the box
/// count agrees with the settlement (0 disagreements). Two subjects are not
/// named exactly by the box ("Max Shabanov" vs "Maxim Shabanov", "William
/// Borgen" vs "Will Borgen") and fail closed.
///
/// CONSTRUCTED here, and only here: the reader's calendar (Pacific, en_US),
/// `now`, the reader's player and milestone choices, and — named in each test
/// that does it — a decoded `status` set to `live` (no live NHL body is
/// retained) or one decoded settlement field cleared or flipped (no retained
/// final row lacks one). Expected clock words come from part one's own
/// formatter, never a hard-coded spelling.
@MainActor
final class HockeyJourneyContributionAdapter10868Tests: XCTestCase {
    private typealias A = HockeyJourneyContributionAdapter10868
    private typealias Page = HockeyJourneyPageAdapter10868
    private typealias Input = PlayerContributionInput10868

    private static let pacific: Calendar = {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "America/Los_Angeles")!
        return calendar
    }()

    private nonisolated struct BoxBody: Decodable {
        nonisolated struct Box: Decodable { let players: [String: [String: Double]]? }
        let boxScoreData: Box?
    }

    private func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    private func detail(_ json: String) throws -> EventDetail {
        try decoder().decode(EventDetail.self, from: Data(json.utf8))
    }

    private func markets(_ json: String) throws -> GameMarketsResponse {
        try decoder().decode(GameMarketsResponse.self, from: Data(json.utf8))
    }

    private func box(_ json: String) throws -> [String: [String: Double]]? {
        try decoder().decode(BoxBody.self, from: Data(json.utf8)).boxScoreData?.players
    }

    private func host(box: [String: [String: Double]]?, now: String) -> A.Host {
        A.Host(boxScore: box, now: now.asDate!, calendar: Self.pacific, locale: Locale(identifier: "en_US"))
    }

    private func clock(_ iso: String, _ host: A.Host) -> String {
        Page.clockWords(iso.asDate!, host: host.page)
    }

    private func milestone(_ input: Input?, _ target: String) throws -> PlayerContributionMilestone10868 {
        try XCTUnwrap(input?.player?.milestones.first { $0.target == target }, "milestone \(target)")
    }

    private func row(_ markets: GameMarketsResponse, _ market: String, _ outcome: String) throws -> GameMarketPlayerProp {
        try XCTUnwrap(markets.playerProps?.first { $0.marketName == market && $0.outcomeName == outcome })
    }

    private func index(_ markets: GameMarketsResponse, _ market: String, _ outcome: String) throws -> Int {
        try XCTUnwrap(markets.playerProps?.firstIndex { $0.marketName == market && $0.outcomeName == outcome })
    }

    private static let bosMinPoints = "Boston vs Minnesota: Points"
    private static let bosMinAssists = "Boston vs Minnesota: Assists"
    private static let nyiMinPoints = "New York Islanders vs Minnesota: Points"
    private static let nyiMinAssists = "New York Islanders vs Minnesota: Assists"
    private static let njVegPoints = "New Jersey vs Vegas: Points"

    // MARK: Ladders and identity

    func testPointsMilestonesGroupPerPlayerUnderStableSourceRecordIdsAndGoalsRowsStayOut() throws {
        let event = try detail(Self.wildBruinsDetail)
        let served = try markets(Self.wildBruinsMarkets)
        let host = host(box: try box(Self.wildBruinsDetail), now: "2026-10-11T04:56:41Z")
        let names = TeamShortName.shortPair(away: event.awayTeam, home: event.homeTeam, sportKey: event.sport)

        let points = try XCTUnwrap(A.points(event, markets: served, host: host))
        XCTAssertEqual(points.orientation, .columns)
        XCTAssertEqual(points.phase, .final)
        XCTAssertEqual(points.eyebrow, "PLAYER POINTS")
        XCTAssertEqual(points.chartTitle, "Pregame chances · at least this many")
        // No printed pregame chance anywhere on this body, so #4857's key falls through to the name.
        XCTAssertEqual(points.chooser?.title, "Choose player · 3")
        XCTAssertEqual(points.chooser?.choices.map(\.id), ["player:kirill kaprizov", "player:max shabanov", "player:quinn hughes"])
        XCTAssertEqual(points.chooser?.choices.map(\.detail), [names.home, nil, names.home],
                       "the served side, or nothing: the rescue rows name no team")
        XCTAssertEqual(points.player?.id, "player:kirill kaprizov")
        XCTAssertNil(points.selectedMilestoneID, "no printed chance, so `defaultTarget` selects nothing")

        let hughes = try XCTUnwrap(A.points(event, markets: served, host: host, selectedPlayerID: "player:quinn hughes"))
        XCTAssertEqual(hughes.player?.name, "Quinn Hughes")
        XCTAssertEqual(hughes.player?.milestones.map(\.id), [
            "kalshi|Boston vs Minnesota: Points-Quinn Hughes: 1+",
            "kalshi|Boston vs Minnesota: Points-Quinn Hughes: 2+",
            "kalshi|Boston vs Minnesota: Points-Quinn Hughes: 3+",
        ])
        XCTAssertEqual(hughes.player?.milestones.map(\.id),
                       try ["1+", "2+", "3+"].map { "kalshi|" + (try row(served, Self.bosMinPoints, "Quinn Hughes: \($0)")).id })
        XCTAssertEqual(hughes.player?.milestones.map(\.target), ["1+", "2+", "3+"])
        XCTAssertEqual(hughes.player?.milestones.map(\.title), ["1+ points", "2+ points", "3+ points"])
        // The Goals 1+ rows kept in the subset reach neither card.
        let assists = try XCTUnwrap(A.assists(event, markets: served, host: host, selectedPlayerID: "player:quinn hughes"))
        XCTAssertEqual(assists.orientation, .bars)
        for input in [hughes, assists] {
            XCTAssertFalse(input.milestones.contains { $0.id.contains(": Goals-") })
        }
        XCTAssertEqual(assists.player?.milestones.map(\.id).first, "kalshi|Boston vs Minnesota: Assists-Quinn Hughes: 1+")
    }

    // MARK: Final

    func testAtTheFinalNoSettledRowIsAChanceTheResultIsTheSettlementAndTheCountIsTheBox() throws {
        let event = try detail(Self.wildBruinsDetail)
        let served = try markets(Self.wildBruinsMarkets)
        let host = host(box: try box(Self.wildBruinsDetail), now: "2026-10-11T04:56:41Z")
        let second = "kalshi|Boston vs Minnesota: Points-Quinn Hughes: 2+"
        let points = try XCTUnwrap(A.points(event, markets: served, host: host,
                                            selectedPlayerID: "player:quinn hughes", selectedMilestoneID: second))
        let milestones = try XCTUnwrap(points.player?.milestones)
        // Every row serves over_probability 1.0 / 0.0 and pregame_mark null: no milestone prints a chance.
        for m in milestones {
            XCTAssertNil(m.before, m.id)
            XCTAssertEqual(m.beforeMissing, "Unavailable")
            XCTAssertEqual(points.beforeReading(m), .missing("Unavailable"))
            XCTAssertNil(points.currentReading(m), "no in-game slot after the final")
            XCTAssertNil(points.progress(m), "no in-game progress after the final")
            XCTAssertNil(m.progress)
        }
        XCTAssertEqual(milestones.map(\.result), [.reached("Reached"), .reached("Reached"), .missed("Missed")])
        XCTAssertEqual(points.player?.actual, .count(PlayerContributionCount10868(
            count: "2", unit: "points", breakdown: "1 goal + 1 assist", accessibilityDetail: "box score after the final")))
        XCTAssertEqual(points.timing, PlayerContributionTiming10868(
            milestoneID: second, title: "Quinn Hughes 2+ points · probability timing",
            lines: ["Pregame chance: Unavailable", "Final count: box score after the final",
                    "Final result: Reached · settled by Kalshi"]))

        let kaprizov = try XCTUnwrap(A.points(event, markets: served, host: host))
        XCTAssertEqual(kaprizov.player?.actual, .count(PlayerContributionCount10868(
            count: "2", unit: "points", breakdown: "2 goals + 0 assists", accessibilityDetail: "box score after the final")))

        let assists = try XCTUnwrap(A.assists(event, markets: served, host: host, selectedPlayerID: "player:quinn hughes"))
        XCTAssertEqual(assists.player?.milestones.map(\.result), [.reached("Reached"), .missed("Missed"), .missed("Missed")])
        XCTAssertEqual(assists.player?.actual, .count(PlayerContributionCount10868(
            count: "1", unit: "assist", breakdown: nil, accessibilityDetail: "box score after the final")))
    }

    func testServedPregameMarksLeadAfterTheFinalAndAMilestoneWithoutOneSaysUnavailable() throws {
        let event = try detail(Self.islandersWildDetail)
        let served = try markets(Self.islandersWildMarkets)
        let host = host(box: try box(Self.islandersWildDetail), now: "2026-10-30T20:13:55Z")
        let assists = try XCTUnwrap(A.assists(event, markets: served, host: host))
        XCTAssertEqual(assists.phase, .final)
        // #4857 over the printed marks: three marked rungs, then two (top 0.5 before 0.31), then one.
        XCTAssertEqual(assists.chooser?.choices.map(\.name), ["Quinn Hughes", "Kirill Kaprizov", "Max Shabanov", "Emil Heineman"])
        XCTAssertEqual(assists.selectedMilestoneID, "kalshi|New York Islanders vs Minnesota: Assists-Quinn Hughes: 1+",
                       "nearest even odds over the marks 0.6 / 0.215 / 0.055")

        for target in ["1+", "2+", "3+"] {
            let m = try milestone(assists, target)
            let source = try row(served, Self.nyiMinAssists, "Quinn Hughes: \(target)")
            let mark = try XCTUnwrap(source.pregameMark)
            XCTAssertEqual(m.before?.probability, mark, "the served mark, not the settled over_probability \(source.overProbability ?? -1)")
            XCTAssertEqual(m.before?.text, formatProbability(mark))
            XCTAssertEqual(m.before?.accessibilityDetail, "saved before the start · Kalshi", "the mark carries no clock")
        }

        // Emil Heineman: 1+ has a mark, 2+ is served with none — it borrows neither 1+'s nor its own 0%.
        let heineman = try XCTUnwrap(A.assists(event, markets: served, host: host, selectedPlayerID: "player:emil heineman"))
        let one = try milestone(heineman, "1+"), two = try milestone(heineman, "2+")
        XCTAssertEqual(one.before?.probability, 0.165)
        XCTAssertNil(try row(served, Self.nyiMinAssists, "Emil Heineman: 2+").pregameMark)
        XCTAssertNil(two.before)
        XCTAssertEqual(heineman.beforeReading(two), .missing("Unavailable"))
        XCTAssertEqual([one.result, two.result], [.reached("Reached"), .missed("Missed")])
        XCTAssertEqual(heineman.player?.actual, .count(PlayerContributionCount10868(
            count: "1", unit: "assist", breakdown: nil, accessibilityDetail: "box score after the final")))

        // "Max Shabanov" is not the box's "Maxim Shabanov": no count, and the settlement still grades.
        let shabanov = try XCTUnwrap(A.assists(event, markets: served, host: host, selectedPlayerID: "player:max shabanov"))
        XCTAssertEqual(shabanov.player?.actual, .unavailable("Final count unavailable"))
        XCTAssertNil(shabanov.player?.team)
        XCTAssertEqual(shabanov.player?.milestones.map(\.result), [.missed("Missed"), .missed("Missed")])
    }

    func testUnknownIsNotLossAndADisagreementWithTheBoxIsNeverPickedOneWay() throws {
        let event = try detail(Self.wildBruinsDetail)
        let host = host(box: try box(Self.wildBruinsDetail), now: "2026-10-11T04:56:41Z")
        // Every kept row of both finals carries a served settlement (the full files: 0 of 223 without one).
        for json in [Self.wildBruinsMarkets, Self.islandersWildMarkets] {
            for served in try markets(json).playerProps ?? [] {
                XCTAssertNotNil(A.settlement(served), served.id)
            }
        }
        // A rescue row with no box line (Max Shabanov, `actual` null) is graded by its settlement alone.
        let base = try markets(Self.wildBruinsMarkets)
        let rescue = try XCTUnwrap(A.assists(event, markets: base, host: host, selectedPlayerID: "player:max shabanov"))
        XCTAssertEqual(rescue.player?.milestones.map(\.result), [.reached("Reached"), .missed("Missed")])

        func hughesPoints(_ target: String, _ edit: (inout GameMarketPlayerProp) -> Void) throws -> PlayerContributionResult10868 {
            var served = base
            let i = try index(served, Self.bosMinPoints, "Quinn Hughes: \(target)")
            edit(&served.playerProps![i])
            let input = try XCTUnwrap(A.points(event, markets: served, host: host, selectedPlayerID: "player:quinn hughes"))
            return try milestone(input, target).result
        }
        XCTAssertEqual(try hughesPoints("3+") { _ in }, .missed("Missed"), "the served settlement grades it")
        // CONSTRUCTED: the same missed 3+ row with its settlement cleared, three ways. None reads "Missed".
        XCTAssertEqual(try hughesPoints("3+") { $0.isWinner = nil }, .unconfirmed("Result unconfirmed"))
        XCTAssertEqual(try hughesPoints("3+") { $0.resolutionSource = nil }, .unconfirmed("Result unconfirmed"))
        XCTAssertEqual(try hughesPoints("3+") { $0.resolutionSource = "ungradeable_result" }, .unconfirmed("Result unconfirmed"))
        // CONSTRUCTED: 1+ flipped to a served loss while the box says 2 points and `hit` says true — no pick.
        XCTAssertEqual(try hughesPoints("1+") { $0.isWinner = false }, .unconfirmed("Result unconfirmed"))
        // A box count at or above the target never grades on its own.
        XCTAssertEqual(try hughesPoints("1+") { $0.isWinner = nil }, .unconfirmed("Result unconfirmed"))
    }

    // MARK: Before

    func testBeforeTheStartThePregameChanceIsTheQuotesOwnPriceOnItsOwnClockAndNoInGameSlotIsRead() throws {
        let event = try detail(Self.devilsKnightsDetail)
        let served = try markets(Self.devilsKnightsMarkets)
        let host = host(box: try box(Self.devilsKnightsDetail), now: "2026-10-30T20:13:55Z")
        XCTAssertNil(host.boxScore)
        let names = TeamShortName.shortPair(away: event.awayTeam, home: event.homeTeam, sportKey: event.sport)

        let points = try XCTUnwrap(A.points(event, markets: served, host: host))
        XCTAssertEqual(points.phase, .before)
        XCTAssertEqual(points.chooser?.choices.map(\.name), ["Jack Eichel", "Jack Hughes"], "three printed rungs each; 69% leads 65%")
        XCTAssertEqual(points.player?.team, names.home)
        let eichel = try row(served, Self.njVegPoints, "Jack Eichel: 1+")
        let observed = try XCTUnwrap(eichel.observedAt)
        let first = try milestone(points, "1+")
        XCTAssertEqual(first.before?.probability, eichel.overProbability)
        XCTAssertNotEqual(first.before?.probability, eichel.pregameMark, "the opening-line mark is not the pregame chance before the start")
        XCTAssertEqual(first.before?.text, formatProbability(try XCTUnwrap(eichel.overProbability)))
        XCTAssertEqual(first.before?.accessibilityDetail, "recorded \(clock(observed, host)) · Kalshi")
        for m in try XCTUnwrap(points.player?.milestones) {
            XCTAssertNil(points.currentReading(m), "no current reading before the start")
            XCTAssertNil(points.progress(m))
        }
        XCTAssertEqual(points.player?.actual, .unavailable("Count unavailable"))
        // Nearest even odds over 0.685 / 0.345 / 0.125.
        let second = "kalshi|New Jersey vs Vegas: Points-Jack Eichel: 2+"
        XCTAssertEqual(points.selectedMilestoneID, second)
        XCTAssertEqual(points.timing, PlayerContributionTiming10868(
            milestoneID: second, title: "Jack Eichel 2+ points · probability timing",
            lines: ["Pregame chance: recorded \(clock(observed, host)) · Kalshi"]))

        // Still before the 22:00Z start, but the quotes' own clock is past the live bound.
        let late = try XCTUnwrap(observed.asDate).addingTimeInterval(SourceAge.liveStaleAfter + 61)
        let stale = A.Host(boxScore: nil, now: late, calendar: Self.pacific, locale: Locale(identifier: "en_US"))
        let aged = try XCTUnwrap(A.points(event, markets: served, host: stale))
        XCTAssertEqual(aged.phase, .before)
        for m in try XCTUnwrap(aged.player?.milestones) {
            XCTAssertNil(m.before, "a quote no longer observed is not a pregame chance")
            XCTAssertEqual(m.beforeMissing, "No recent probability update")
        }
        XCTAssertNil(aged.selectedMilestoneID)
        XCTAssertEqual(A.Words.noRecentUpdate, AllMarketsCatalogView9483.noRecentPrice)
    }

    // MARK: During play

    func testOncePlayStartsThePregameChanceIsTheServedMarkAndAPreStartQuoteIsNoInGameReading() throws {
        // CONSTRUCTED: the pregame body with its decoded status set to `live`, read after the listed start.
        var event = try detail(Self.devilsKnightsDetail)
        event.status = "live"
        let served = try markets(Self.devilsKnightsMarkets)
        let host = host(box: nil, now: "2026-10-30T22:30:00Z")
        let first = "kalshi|New Jersey vs Vegas: Points-Jack Eichel: 1+"
        let points = try XCTUnwrap(A.points(event, markets: served, host: host, selectedMilestoneID: first))
        XCTAssertEqual(points.phase, .during)
        let eichel = try row(served, Self.njVegPoints, "Jack Eichel: 1+")
        let m = try milestone(points, "1+")
        XCTAssertEqual(m.before?.probability, eichel.pregameMark)
        XCTAssertEqual(m.before?.text, formatProbability(try XCTUnwrap(eichel.pregameMark)))
        XCTAssertEqual(m.before?.accessibilityDetail, "saved before the start · Kalshi")
        // The served quote was observed at 20:12Z, before the 22:00Z start: not an in-game reading.
        XCTAssertEqual(m.current, .unavailable("No in-game reading"))
        XCTAssertEqual(points.currentReading(m), .chanceStatus("No in-game reading"))
        XCTAssertNil(points.movement(m))
        XCTAssertNil(points.progress(m), "no box, no progress")
        XCTAssertEqual(points.player?.actual, .unavailable("Count unavailable"))
        XCTAssertEqual(m.result, .unconfirmed("Result unconfirmed"))
        XCTAssertEqual(points.timing?.lines, ["Pregame chance: saved before the start · Kalshi",
                                              "In-game chance: No in-game reading", "Count so far: Count unavailable"])
    }

    func testDuringPlayABoxCountAtTheTargetReadsReachedSoFarAndASettledRowIsNeverAChance() throws {
        // CONSTRUCTED: the final's own rows and box with the decoded status set to `live`.
        var event = try detail(Self.wildBruinsDetail)
        event.status = "live"
        let served = try markets(Self.wildBruinsMarkets)
        let host = host(box: try box(Self.wildBruinsDetail), now: "2026-10-04T02:00:00Z")
        let points = try XCTUnwrap(A.points(event, markets: served, host: host,
                                            selectedMilestoneID: "kalshi|Boston vs Minnesota: Points-Kirill Kaprizov: 3+"))
        XCTAssertEqual(points.phase, .during)
        XCTAssertEqual(points.player?.name, "Kirill Kaprizov")
        let one = try milestone(points, "1+"), two = try milestone(points, "2+"), three = try milestone(points, "3+")
        XCTAssertEqual(one.current, .reached("Reached so far"))
        XCTAssertEqual(points.currentReading(one), .actual("Reached so far"), "performance, not a chance")
        XCTAssertEqual(two.progress, PlayerContributionProgress10868(status: "Milestone reached so far", fraction: 1))
        // 3+ serves over_probability 0.0 with is_winner false: a settlement, never shown as 0%.
        XCTAssertEqual(three.current, .unavailable("No in-game reading"))
        XCTAssertEqual(points.progress(three), PlayerContributionProgress10868(status: "1 more for 3+", fraction: 2.0 / 3.0))
        for m in [one, two, three] {
            if case .recorded = m.current { XCTFail("no settled price is an in-game chance: \(m.id)") }
            XCTAssertEqual(m.result, .unconfirmed("Result unconfirmed"), "no grade before the final")
        }
        XCTAssertEqual(points.player?.actual, .count(PlayerContributionCount10868(
            count: "2", unit: "points so far", breakdown: "2 goals + 0 assists",
            accessibilityDetail: "box score · update time not recorded")))
        XCTAssertEqual(points.timing?.lines, ["Pregame chance: Unavailable", "In-game chance: No in-game reading",
                                              "Count so far: box score · update time not recorded"])
    }

    // MARK: Chooser and selection

    func testTheChooserListsEveryLadderedPlayerAndAChosenIdIsNeverSubstituted() throws {
        let event = try detail(Self.islandersWildDetail)
        let served = try markets(Self.islandersWildMarkets)
        let host = host(box: try box(Self.islandersWildDetail), now: "2026-10-30T20:13:55Z")
        let points = try XCTUnwrap(A.points(event, markets: served, host: host))
        // Four marked rungs, three, then two each (top 0.435 before 0.295).
        XCTAssertEqual(points.chooser?.title, "Choose player · 4")
        XCTAssertEqual(points.chooser?.choices.map(\.id),
                       ["player:kirill kaprizov", "player:quinn hughes", "player:max shabanov", "player:emil heineman"])
        XCTAssertEqual(Set(points.chooser?.choices.map(\.id) ?? []).count, 4)
        let kaprizov = try XCTUnwrap(points.player?.milestones)
        XCTAssertEqual(kaprizov.map(\.target), ["1+", "2+", "3+", "4+"])
        let index = try XCTUnwrap(PlayerPropsFamily.defaultTarget(probabilities: kaprizov.map { $0.before?.probability }))
        XCTAssertEqual(points.selectedMilestoneID, kaprizov[index].id, "the production default, over printed chances only")
        XCTAssertEqual(points.player?.actual, .count(PlayerContributionCount10868(
            count: "1", unit: "point", breakdown: "0 goals + 1 assist", accessibilityDetail: "box score after the final")))

        let hughes = try XCTUnwrap(A.points(event, markets: served, host: host, selectedPlayerID: "player:quinn hughes"))
        XCTAssertEqual(hughes.selectedMilestoneID, "kalshi|New York Islanders vs Minnesota: Points-Quinn Hughes: 1+")
        XCTAssertEqual(hughes.player?.milestones.map(\.result), [.reached("Reached"), .reached("Reached"), .missed("Missed")])
        XCTAssertEqual(hughes.chooser, points.chooser, "the chooser does not move with the choice")

        let gone = try XCTUnwrap(A.points(event, markets: served, host: host, selectedPlayerID: "player:nobody"))
        XCTAssertNil(gone.player)
        XCTAssertEqual(gone.selectionNotice, Input.playerUnavailable)

        let foreign = "kalshi|New York Islanders vs Minnesota: Points-Quinn Hughes: 2+"
        let mismatched = try XCTUnwrap(A.points(event, markets: served, host: host, selectedMilestoneID: foreign))
        XCTAssertEqual(mismatched.player?.name, "Kirill Kaprizov")
        XCTAssertEqual(mismatched.selection, .missing(foreign), "another player's milestone is passed through, never replaced")
        XCTAssertNil(mismatched.timing)

        XCTAssertNil(A.points(event, markets: nil, host: host), "no ladder, no card")
    }

    // MARK: Retained payloads (reduced verbatim subsets)

    /// `atlas-v6/raw/nhl-15169793-game-markets.json` · sha256 3abba0f2f3c0a4875a394e3f82d7bf14cea76c2dfd690d6b61490b477a7806dc
    static let wildBruinsMarkets = ##"""
{"event_id":15169793,
"home_team":"Minnesota Wild",
"away_team":"Boston Bruins",
"home_score":4,
"away_score":1,
"status":"completed",
"player_props":[
{"market_name":"Boston vs Minnesota: Goals","outcome_name":"Kirill Kaprizov: 1+","observed_at":null,"contributor_outcome_ids":[243943074],"threshold":1.0,"over_probability":1.0,"opening_over_probability":null,"pregame_mark":null,"_inverted":false,"source":"kalshi","movement":null,"_market_id":64870965,"actual":2.0,"hit":true,"is_winner":true,"resolution_source":"api_settlement","player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/3942335.png","player_team":"home"},
{"market_name":"Boston vs Minnesota: Goals","outcome_name":"Quinn Hughes: 1+","observed_at":null,"contributor_outcome_ids":[243943087],"threshold":1.0,"over_probability":1.0,"opening_over_probability":null,"pregame_mark":null,"_inverted":false,"source":"kalshi","movement":null,"_market_id":64870965,"actual":1.0,"hit":true,"is_winner":true,"resolution_source":"api_settlement","player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/4320548.png","player_team":"home"},
{"market_name":"Boston vs Minnesota: Assists","outcome_name":"Max Shabanov: 1+","observed_at":null,"contributor_outcome_ids":[243939182],"threshold":1.0,"over_probability":1.0,"opening_over_probability":null,"pregame_mark":null,"_inverted":false,"source":"kalshi","movement":null,"_market_id":64870807,"actual":null,"hit":true,"is_winner":true,"resolution_source":"api_settlement"},
{"market_name":"Boston vs Minnesota: Assists","outcome_name":"Max Shabanov: 2+","observed_at":null,"contributor_outcome_ids":[243939183],"threshold":2.0,"over_probability":0.0,"opening_over_probability":null,"pregame_mark":null,"_inverted":false,"source":"kalshi","movement":null,"_market_id":64870807,"actual":null,"hit":false,"is_winner":false,"resolution_source":"api_settlement"},
{"market_name":"Boston vs Minnesota: Assists","outcome_name":"Quinn Hughes: 1+","observed_at":null,"contributor_outcome_ids":[243939187],"threshold":1.0,"over_probability":1.0,"opening_over_probability":null,"pregame_mark":null,"_inverted":false,"source":"kalshi","movement":null,"_market_id":64870807,"actual":1.0,"hit":true,"is_winner":true,"resolution_source":"api_settlement","player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/4320548.png","player_team":"home"},
{"market_name":"Boston vs Minnesota: Assists","outcome_name":"Quinn Hughes: 2+","observed_at":null,"contributor_outcome_ids":[243939188],"threshold":2.0,"over_probability":0.0,"opening_over_probability":null,"pregame_mark":null,"_inverted":false,"source":"kalshi","movement":null,"_market_id":64870807,"actual":1.0,"hit":false,"is_winner":false,"resolution_source":"api_settlement","player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/4320548.png","player_team":"home"},
{"market_name":"Boston vs Minnesota: Assists","outcome_name":"Quinn Hughes: 3+","observed_at":null,"contributor_outcome_ids":[243939189],"threshold":3.0,"over_probability":0.0,"opening_over_probability":null,"pregame_mark":null,"_inverted":false,"source":"kalshi","movement":null,"_market_id":64870807,"actual":1.0,"hit":false,"is_winner":false,"resolution_source":"api_settlement","player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/4320548.png","player_team":"home"},
{"market_name":"Boston vs Minnesota: Assists","outcome_name":"Kirill Kaprizov: 1+","observed_at":null,"contributor_outcome_ids":[243939178],"threshold":1.0,"over_probability":0.0,"opening_over_probability":null,"pregame_mark":null,"_inverted":false,"source":"kalshi","movement":null,"_market_id":64870807,"actual":0.0,"hit":false,"is_winner":false,"resolution_source":"api_settlement","player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/3942335.png","player_team":"home"},
{"market_name":"Boston vs Minnesota: Assists","outcome_name":"Kirill Kaprizov: 2+","observed_at":null,"contributor_outcome_ids":[243939179],"threshold":2.0,"over_probability":0.0,"opening_over_probability":null,"pregame_mark":null,"_inverted":false,"source":"kalshi","movement":null,"_market_id":64870807,"actual":0.0,"hit":false,"is_winner":false,"resolution_source":"api_settlement","player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/3942335.png","player_team":"home"},
{"market_name":"Boston vs Minnesota: Points","outcome_name":"Kirill Kaprizov: 1+","observed_at":null,"contributor_outcome_ids":[243945028],"threshold":1.0,"over_probability":1.0,"opening_over_probability":null,"pregame_mark":null,"_inverted":false,"source":"kalshi","movement":null,"_market_id":64871068,"actual":2.0,"hit":true,"is_winner":true,"resolution_source":"api_settlement","player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/3942335.png","player_team":"home"},
{"market_name":"Boston vs Minnesota: Points","outcome_name":"Kirill Kaprizov: 2+","observed_at":null,"contributor_outcome_ids":[243945029],"threshold":2.0,"over_probability":1.0,"opening_over_probability":null,"pregame_mark":null,"_inverted":false,"source":"kalshi","movement":null,"_market_id":64871068,"actual":2.0,"hit":true,"is_winner":true,"resolution_source":"api_settlement","player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/3942335.png","player_team":"home"},
{"market_name":"Boston vs Minnesota: Points","outcome_name":"Kirill Kaprizov: 3+","observed_at":null,"contributor_outcome_ids":[243945030],"threshold":3.0,"over_probability":0.0,"opening_over_probability":null,"pregame_mark":null,"_inverted":false,"source":"kalshi","movement":null,"_market_id":64871068,"actual":2.0,"hit":false,"is_winner":false,"resolution_source":"api_settlement","player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/3942335.png","player_team":"home"},
{"market_name":"Boston vs Minnesota: Points","outcome_name":"Max Shabanov: 1+","observed_at":null,"contributor_outcome_ids":[243945034],"threshold":1.0,"over_probability":1.0,"opening_over_probability":null,"pregame_mark":null,"_inverted":false,"source":"kalshi","movement":null,"_market_id":64871068,"actual":null,"hit":true,"is_winner":true,"resolution_source":"api_settlement"},
{"market_name":"Boston vs Minnesota: Points","outcome_name":"Max Shabanov: 2+","observed_at":null,"contributor_outcome_ids":[243945035],"threshold":2.0,"over_probability":0.0,"opening_over_probability":null,"pregame_mark":null,"_inverted":false,"source":"kalshi","movement":null,"_market_id":64871068,"actual":null,"hit":false,"is_winner":false,"resolution_source":"api_settlement"},
{"market_name":"Boston vs Minnesota: Points","outcome_name":"Quinn Hughes: 1+","observed_at":null,"contributor_outcome_ids":[243945040],"threshold":1.0,"over_probability":1.0,"opening_over_probability":null,"pregame_mark":null,"_inverted":false,"source":"kalshi","movement":null,"_market_id":64871068,"actual":2.0,"hit":true,"is_winner":true,"resolution_source":"api_settlement","player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/4320548.png","player_team":"home"},
{"market_name":"Boston vs Minnesota: Points","outcome_name":"Quinn Hughes: 2+","observed_at":null,"contributor_outcome_ids":[243945041],"threshold":2.0,"over_probability":1.0,"opening_over_probability":null,"pregame_mark":null,"_inverted":false,"source":"kalshi","movement":null,"_market_id":64871068,"actual":2.0,"hit":true,"is_winner":true,"resolution_source":"api_settlement","player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/4320548.png","player_team":"home"},
{"market_name":"Boston vs Minnesota: Points","outcome_name":"Quinn Hughes: 3+","observed_at":null,"contributor_outcome_ids":[243945042],"threshold":3.0,"over_probability":0.0,"opening_over_probability":null,"pregame_mark":null,"_inverted":false,"source":"kalshi","movement":null,"_market_id":64871068,"actual":2.0,"hit":false,"is_winner":false,"resolution_source":"api_settlement","player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/4320548.png","player_team":"home"}
],
"during_player_props":null,
"after_player_props":null}
"""##

    /// `atlas-v6/raw/nhl-15169793-detail.json` · sha256 a11c662df1fd7c94c080cf0c7455c6771da9f8f38de3a44517a0a633f03ea348
    static let wildBruinsDetail = ##"""
{"id":15169793,
"external_id":"3a9af73961ea2f2322255a6fca4d421e",
"sport":"icehockey_nhl",
"sport_name":"NHL",
"home_team":"Minnesota Wild",
"away_team":"Boston Bruins",
"commence_time":"2026-10-04T00:00:00+00:00",
"start_is_tbd":false,
"completed_at":"2026-10-04T02:48:56.423990+00:00",
"status":"completed",
"home_score":4,
"away_score":1,
"score_source":"espn",
"score_observed_at":"2026-10-04T05:59:38.451734+00:00",
"espn":{"espn_id":"401891814","game_clock":"0:00","period":"Final","broadcast":"ESPN+, MINNHL, KSTC","probability_sources":{"stat_model":0.999,"betting_book_count":2.0}},
"box_score_data":{"players":{
"Quinn Hughes":{"hits":0.0,"goals":1.0,"shots":4.0,"assists":1.0,"giveaways":1.0,"takeaways":1.0,"plus minus":1.0,"faceoffs won":0.0,"blocked shots":1.0,"shootout goals":0.0,"penalty minutes":0.0},
"Maxim Shabanov":{"hits":1.0,"goals":0.0,"shots":0.0,"assists":1.0,"giveaways":1.0,"takeaways":0.0,"plus minus":0.0,"faceoffs won":0.0,"blocked shots":1.0,"shootout goals":0.0,"penalty minutes":0.0},
"Kirill Kaprizov":{"hits":0.0,"goals":2.0,"shots":3.0,"assists":0.0,"giveaways":1.0,"takeaways":0.0,"plus minus":1.0,"faceoffs won":1.0,"blocked shots":0.0,"shootout goals":0.0,"penalty minutes":0.0}
},"home_period_scores":[0,2,2],"away_period_scores":[1,0,0]}}
"""##

    /// `shipping-adoption-20261027/cli-candidate-20261030/retained-payloads/nhl-15338034-game-markets-20261030T201355Z.json` · sha256 0227bebf7912f86eea5db0f62244702f776f26761daca6afba691ad1a89e29c6
    static let islandersWildMarkets = ##"""
{"event_id":15338034,
"home_team":"Minnesota Wild",
"away_team":"New York Islanders",
"home_score":3,
"away_score":4,
"status":"completed",
"player_props":[
{"market_name":"New York Islanders vs Minnesota: Assists","outcome_name":"Kirill Kaprizov: 1+","observed_at":"2026-10-30T02:42:35.327617+00:00","contributor_outcome_ids":[255782405],"threshold":1.0,"over_probability":1.0,"opening_over_probability":0.5,"pregame_mark":0.5,"_inverted":false,"source":"kalshi","movement":0.5,"_market_id":68152126,"actual":1.0,"hit":true,"is_winner":true,"resolution_source":"api_settlement","player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/3942335.png","player_team":"home"},
{"market_name":"New York Islanders vs Minnesota: Assists","outcome_name":"Kirill Kaprizov: 2+","observed_at":"2026-10-30T02:42:35.327617+00:00","contributor_outcome_ids":[255782418],"threshold":2.0,"over_probability":0.0,"opening_over_probability":0.105,"pregame_mark":0.105,"_inverted":false,"source":"kalshi","movement":-0.105,"_market_id":68152126,"actual":1.0,"hit":false,"is_winner":false,"resolution_source":"api_settlement","player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/3942335.png","player_team":"home"},
{"market_name":"New York Islanders vs Minnesota: Assists","outcome_name":"Quinn Hughes: 1+","observed_at":"2026-10-30T02:42:35.327617+00:00","contributor_outcome_ids":[255782403],"threshold":1.0,"over_probability":1.0,"opening_over_probability":0.6,"pregame_mark":0.6,"_inverted":false,"source":"kalshi","movement":0.4,"_market_id":68152126,"actual":1.0,"hit":true,"is_winner":true,"resolution_source":"api_settlement","player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/4320548.png","player_team":"home"},
{"market_name":"New York Islanders vs Minnesota: Assists","outcome_name":"Quinn Hughes: 2+","observed_at":"2026-10-30T02:39:20.624453+00:00","contributor_outcome_ids":[255782414],"threshold":2.0,"over_probability":0.0,"opening_over_probability":0.215,"pregame_mark":0.215,"_inverted":false,"source":"kalshi","movement":-0.215,"_market_id":68152126,"actual":1.0,"hit":false,"is_winner":false,"resolution_source":"api_settlement","player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/4320548.png","player_team":"home"},
{"market_name":"New York Islanders vs Minnesota: Assists","outcome_name":"Quinn Hughes: 3+","observed_at":"2026-10-30T02:42:35.327617+00:00","contributor_outcome_ids":[255782422],"threshold":3.0,"over_probability":0.0,"opening_over_probability":0.055,"pregame_mark":0.055,"_inverted":false,"source":"kalshi","movement":-0.055,"_market_id":68152126,"actual":1.0,"hit":false,"is_winner":false,"resolution_source":"api_settlement","player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/4320548.png","player_team":"home"},
{"market_name":"New York Islanders vs Minnesota: Assists","outcome_name":"Emil Heineman: 1+","observed_at":"2026-10-30T02:42:35.327617+00:00","contributor_outcome_ids":[255782416],"threshold":1.0,"over_probability":1.0,"opening_over_probability":0.165,"pregame_mark":0.165,"_inverted":false,"source":"kalshi","movement":0.835,"_market_id":68152126,"actual":1.0,"hit":true,"is_winner":true,"resolution_source":"api_settlement","player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/4697447.png","player_team":"away"},
{"market_name":"New York Islanders vs Minnesota: Assists","outcome_name":"Emil Heineman: 2+","observed_at":null,"contributor_outcome_ids":[256051725],"threshold":2.0,"over_probability":0.0,"opening_over_probability":null,"pregame_mark":null,"_inverted":false,"source":"kalshi","movement":null,"_market_id":68152126,"actual":1.0,"hit":false,"is_winner":false,"resolution_source":"api_settlement","player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/4697447.png","player_team":"away"},
{"market_name":"New York Islanders vs Minnesota: Assists","outcome_name":"Max Shabanov: 1+","observed_at":"2026-10-30T02:42:35.327617+00:00","contributor_outcome_ids":[255782411],"threshold":1.0,"over_probability":0.0,"opening_over_probability":0.31,"pregame_mark":0.31,"_inverted":false,"source":"kalshi","movement":-0.31,"_market_id":68152126,"actual":null,"hit":false,"is_winner":false,"resolution_source":"api_settlement"},
{"market_name":"New York Islanders vs Minnesota: Assists","outcome_name":"Max Shabanov: 2+","observed_at":"2026-10-30T02:42:35.327617+00:00","contributor_outcome_ids":[255782425],"threshold":2.0,"over_probability":0.0,"opening_over_probability":0.05,"pregame_mark":0.05,"_inverted":false,"source":"kalshi","movement":-0.05,"_market_id":68152126,"actual":null,"hit":false,"is_winner":false,"resolution_source":"api_settlement"},
{"market_name":"New York Islanders vs Minnesota: Points","outcome_name":"Quinn Hughes: 1+","observed_at":"2026-10-30T02:42:35.327617+00:00","contributor_outcome_ids":[255781663],"threshold":1.0,"over_probability":1.0,"opening_over_probability":0.655,"pregame_mark":0.655,"_inverted":false,"source":"kalshi","movement":0.345,"_market_id":68152110,"actual":2.0,"hit":true,"is_winner":true,"resolution_source":"api_settlement","player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/4320548.png","player_team":"home"},
{"market_name":"New York Islanders vs Minnesota: Points","outcome_name":"Quinn Hughes: 2+","observed_at":"2026-10-30T02:42:35.327617+00:00","contributor_outcome_ids":[255781677],"threshold":2.0,"over_probability":1.0,"opening_over_probability":0.18,"pregame_mark":0.18,"_inverted":false,"source":"kalshi","movement":0.82,"_market_id":68152110,"actual":2.0,"hit":true,"is_winner":true,"resolution_source":"api_settlement","player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/4320548.png","player_team":"home"},
{"market_name":"New York Islanders vs Minnesota: Points","outcome_name":"Quinn Hughes: 3+","observed_at":"2026-10-30T02:42:35.327617+00:00","contributor_outcome_ids":[255781688],"threshold":3.0,"over_probability":0.0,"opening_over_probability":0.075,"pregame_mark":0.075,"_inverted":false,"source":"kalshi","movement":-0.075,"_market_id":68152110,"actual":2.0,"hit":false,"is_winner":false,"resolution_source":"api_settlement","player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/4320548.png","player_team":"home"},
{"market_name":"New York Islanders vs Minnesota: Points","outcome_name":"Emil Heineman: 1+","observed_at":"2026-10-30T02:42:35.327617+00:00","contributor_outcome_ids":[255818344],"threshold":1.0,"over_probability":1.0,"opening_over_probability":0.295,"pregame_mark":0.295,"_inverted":false,"source":"kalshi","movement":0.705,"_market_id":68152110,"actual":1.0,"hit":true,"is_winner":true,"resolution_source":"api_settlement","player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/4697447.png","player_team":"away"},
{"market_name":"New York Islanders vs Minnesota: Points","outcome_name":"Emil Heineman: 2+","observed_at":"2026-10-29T23:53:25.239915+00:00","contributor_outcome_ids":[255818362],"threshold":2.0,"over_probability":0.0,"opening_over_probability":0.055,"pregame_mark":0.055,"_inverted":false,"source":"kalshi","movement":-0.055,"_market_id":68152110,"actual":1.0,"hit":false,"is_winner":false,"resolution_source":"api_settlement","player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/4697447.png","player_team":"away"},
{"market_name":"New York Islanders vs Minnesota: Points","outcome_name":"Kirill Kaprizov: 1+","observed_at":"2026-10-30T02:42:35.327617+00:00","contributor_outcome_ids":[255781664],"threshold":1.0,"over_probability":1.0,"opening_over_probability":0.61,"pregame_mark":0.61,"_inverted":false,"source":"kalshi","movement":0.39,"_market_id":68152110,"actual":1.0,"hit":true,"is_winner":true,"resolution_source":"api_settlement","player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/3942335.png","player_team":"home"},
{"market_name":"New York Islanders vs Minnesota: Points","outcome_name":"Kirill Kaprizov: 2+","observed_at":"2026-10-30T02:42:35.327617+00:00","contributor_outcome_ids":[255781674],"threshold":2.0,"over_probability":0.0,"opening_over_probability":0.39,"pregame_mark":0.39,"_inverted":false,"source":"kalshi","movement":-0.39,"_market_id":68152110,"actual":1.0,"hit":false,"is_winner":false,"resolution_source":"api_settlement","player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/3942335.png","player_team":"home"},
{"market_name":"New York Islanders vs Minnesota: Points","outcome_name":"Kirill Kaprizov: 3+","observed_at":"2026-10-30T02:42:35.327617+00:00","contributor_outcome_ids":[255781680],"threshold":3.0,"over_probability":0.0,"opening_over_probability":0.15,"pregame_mark":0.15,"_inverted":false,"source":"kalshi","movement":-0.15,"_market_id":68152110,"actual":1.0,"hit":false,"is_winner":false,"resolution_source":"api_settlement","player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/3942335.png","player_team":"home"},
{"market_name":"New York Islanders vs Minnesota: Points","outcome_name":"Kirill Kaprizov: 4+","observed_at":"2026-10-30T02:42:35.327617+00:00","contributor_outcome_ids":[255781690],"threshold":4.0,"over_probability":0.0,"opening_over_probability":0.055,"pregame_mark":0.055,"_inverted":false,"source":"kalshi","movement":-0.055,"_market_id":68152110,"actual":1.0,"hit":false,"is_winner":false,"resolution_source":"api_settlement","player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/3942335.png","player_team":"home"},
{"market_name":"New York Islanders vs Minnesota: Points","outcome_name":"Max Shabanov: 1+","observed_at":"2026-10-30T02:42:35.327617+00:00","contributor_outcome_ids":[255781672],"threshold":1.0,"over_probability":0.0,"opening_over_probability":0.435,"pregame_mark":0.435,"_inverted":false,"source":"kalshi","movement":-0.435,"_market_id":68152110,"actual":null,"hit":false,"is_winner":false,"resolution_source":"api_settlement"},
{"market_name":"New York Islanders vs Minnesota: Points","outcome_name":"Max Shabanov: 2+","observed_at":"2026-10-30T02:42:35.327617+00:00","contributor_outcome_ids":[255781687],"threshold":2.0,"over_probability":0.0,"opening_over_probability":0.08,"pregame_mark":0.08,"_inverted":false,"source":"kalshi","movement":-0.08,"_market_id":68152110,"actual":null,"hit":false,"is_winner":false,"resolution_source":"api_settlement"}
],
"during_player_props":null,
"after_player_props":null}
"""##

    /// `shipping-adoption-20261027/cli-candidate-20261030/retained-payloads/nhl-15338034-detail-20261030T201355Z.json` · sha256 4bd4832c10c7f31626a9cd31df415ef806db1f5a8c9ac1934aba3386d7fbd6e4
    static let islandersWildDetail = ##"""
{"id":15338034,
"external_id":"5020318cfd7098bd38fae6c907029f0f",
"sport":"icehockey_nhl",
"sport_name":"NHL",
"home_team":"Minnesota Wild",
"away_team":"New York Islanders",
"commence_time":"2026-10-30T00:00:00+00:00",
"start_is_tbd":false,
"completed_at":"2026-10-30T02:43:40.379936+00:00",
"status":"completed",
"home_score":3,
"away_score":4,
"score_source":"espn",
"score_observed_at":"2026-10-30T05:59:37.684442+00:00",
"espn":{"espn_id":"401892607","game_clock":"0:00","period":"Final/OT","broadcast":"ESPN+, MSGSN, MINNHL","probability_sources":{"betting":0.5416,"stat_model":0.001,"betting_book_count":13.0}},
"box_score_data":{"players":{
"Quinn Hughes":{"hits":1.0,"goals":1.0,"shots":4.0,"assists":1.0,"giveaways":2.0,"takeaways":0.0,"plus minus":0.0,"faceoffs won":0.0,"blocked shots":1.0,"shootout goals":0.0,"penalty minutes":0.0},
"Emil Heineman":{"hits":4.0,"goals":0.0,"shots":2.0,"assists":1.0,"giveaways":0.0,"takeaways":0.0,"plus minus":1.0,"faceoffs won":0.0,"blocked shots":0.0,"shootout goals":0.0,"penalty minutes":0.0},
"Maxim Shabanov":{"hits":1.0,"goals":0.0,"shots":0.0,"assists":0.0,"giveaways":3.0,"takeaways":1.0,"plus minus":-1.0,"faceoffs won":0.0,"blocked shots":1.0,"shootout goals":0.0,"penalty minutes":0.0},
"Kirill Kaprizov":{"hits":2.0,"goals":0.0,"shots":3.0,"assists":1.0,"giveaways":2.0,"takeaways":0.0,"plus minus":0.0,"faceoffs won":0.0,"blocked shots":0.0,"shootout goals":0.0,"penalty minutes":0.0}
},"home_period_scores":[1,1,1,0],"away_period_scores":[1,1,1,1]}}
"""##

    /// `shipping-adoption-20261027/cli-candidate-20261030/retained-payloads/nhl-15338496-game-markets-20261030T201355Z.json` · sha256 8e475781f15a79de89253a56485a4da4a303e2f219d503208267aedd77fecd4a
    static let devilsKnightsMarkets = ##"""
{"event_id":15338496,
"home_team":"Vegas Golden Knights",
"away_team":"New Jersey Devils",
"home_score":null,
"away_score":null,
"status":"scheduled",
"player_props":[
{"market_name":"New Jersey vs Vegas: Assists","outcome_name":"Jack Eichel: 1+","observed_at":"2026-10-30T20:12:00.557237+00:00","contributor_outcome_ids":[256284873],"threshold":1.0,"over_probability":0.545,"opening_over_probability":0.565,"pregame_mark":0.565,"_inverted":false,"source":"kalshi","movement":-0.02,"_market_id":68282130,"player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/3648002.png","player_team":"home"},
{"market_name":"New Jersey vs Vegas: Assists","outcome_name":"Jack Eichel: 2+","observed_at":"2026-10-30T20:12:00.557237+00:00","contributor_outcome_ids":[256284890],"threshold":2.0,"over_probability":0.18,"opening_over_probability":0.16,"pregame_mark":0.16,"_inverted":false,"source":"kalshi","movement":0.02,"_market_id":68282130,"player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/3648002.png","player_team":"home"},
{"market_name":"New Jersey vs Vegas: Assists","outcome_name":"Jack Hughes: 1+","observed_at":"2026-10-30T20:12:00.557237+00:00","contributor_outcome_ids":[256284875],"threshold":1.0,"over_probability":0.455,"opening_over_probability":0.47,"pregame_mark":0.47,"_inverted":false,"source":"kalshi","movement":-0.015,"_market_id":68282130,"player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/4565222.png","player_team":"away"},
{"market_name":"New Jersey vs Vegas: Assists","outcome_name":"Jack Hughes: 2+","observed_at":"2026-10-30T20:12:00.557237+00:00","contributor_outcome_ids":[256284892],"threshold":2.0,"over_probability":0.14,"opening_over_probability":0.11,"pregame_mark":0.11,"_inverted":false,"source":"kalshi","movement":0.03,"_market_id":68282130,"player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/4565222.png","player_team":"away"},
{"market_name":"New Jersey vs Vegas: Points","outcome_name":"Jack Eichel: 1+","observed_at":"2026-10-30T20:12:00.557237+00:00","contributor_outcome_ids":[256284771],"threshold":1.0,"over_probability":0.685,"opening_over_probability":0.645,"pregame_mark":0.645,"_inverted":false,"source":"kalshi","movement":0.04,"_market_id":68282128,"player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/3648002.png","player_team":"home"},
{"market_name":"New Jersey vs Vegas: Points","outcome_name":"Jack Eichel: 2+","observed_at":"2026-10-30T20:12:00.557237+00:00","contributor_outcome_ids":[256284786],"threshold":2.0,"over_probability":0.345,"opening_over_probability":0.355,"pregame_mark":0.355,"_inverted":false,"source":"kalshi","movement":-0.01,"_market_id":68282128,"player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/3648002.png","player_team":"home"},
{"market_name":"New Jersey vs Vegas: Points","outcome_name":"Jack Eichel: 3+","observed_at":"2026-10-30T20:12:00.557237+00:00","contributor_outcome_ids":[256284793],"threshold":3.0,"over_probability":0.125,"opening_over_probability":0.135,"pregame_mark":0.135,"_inverted":false,"source":"kalshi","movement":-0.01,"_market_id":68282128,"player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/3648002.png","player_team":"home"},
{"market_name":"New Jersey vs Vegas: Points","outcome_name":"Jack Hughes: 1+","observed_at":"2026-10-30T20:12:00.557237+00:00","contributor_outcome_ids":[256284772],"threshold":1.0,"over_probability":0.645,"opening_over_probability":0.645,"pregame_mark":0.645,"_inverted":false,"source":"kalshi","movement":0.0,"_market_id":68282128,"player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/4565222.png","player_team":"away"},
{"market_name":"New Jersey vs Vegas: Points","outcome_name":"Jack Hughes: 2+","observed_at":"2026-10-30T20:12:00.557237+00:00","contributor_outcome_ids":[256284789],"threshold":2.0,"over_probability":0.28,"opening_over_probability":0.27,"pregame_mark":0.27,"_inverted":false,"source":"kalshi","movement":0.01,"_market_id":68282128,"player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/4565222.png","player_team":"away"},
{"market_name":"New Jersey vs Vegas: Points","outcome_name":"Jack Hughes: 3+","observed_at":"2026-10-30T20:12:00.557237+00:00","contributor_outcome_ids":[256284799],"threshold":3.0,"over_probability":0.095,"opening_over_probability":0.105,"pregame_mark":0.105,"_inverted":false,"source":"kalshi","movement":-0.01,"_market_id":68282128,"player_headshot":"https://a.espncdn.com/i/headshots/nhl/players/full/4565222.png","player_team":"away"}
],
"during_player_props":null,
"after_player_props":null}
"""##

    /// `shipping-adoption-20261027/cli-candidate-20261030/retained-payloads/nhl-15338496-detail-20261030T201355Z.json` · sha256 50fbf4678a308e40481340e9b998a2a0870795dd8b04dfdfb05e31caf3dcc1da
    static let devilsKnightsDetail = ##"""
{"id":15338496,
"external_id":"5c712e15e1cd4b9283b4bf410fb334f4",
"sport":"icehockey_nhl",
"sport_name":"NHL",
"home_team":"Vegas Golden Knights",
"away_team":"New Jersey Devils",
"commence_time":"2026-10-30T22:00:00+00:00",
"start_is_tbd":false,
"completed_at":null,
"status":"scheduled",
"home_score":null,
"away_score":null,
"espn":{"espn_id":"401892611","broadcast":"NHL Net, MSGSN, Scripps Sports","probability_sources":{"kalshi":0.505,"betting":0.5052,"polymarket":0.505,"betting_book_count":19.0}}}
"""##
}
