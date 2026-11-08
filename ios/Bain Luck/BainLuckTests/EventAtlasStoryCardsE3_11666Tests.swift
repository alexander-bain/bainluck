import SwiftUI
import XCTest
@testable import Bain_Luck

/// #11666 (Step E3) — Unit tests for native event-page atlas story cards:
/// mark-grammar keys (`EventAtlasStoryCards11666`), settled winner/verdict
/// badges (`✓ Won`, `✓ HIT` / `✗ MISS`), `"No recent probability"` staleness
/// copy, and shared `EventAtlasDetailsSheetModel11666` wiring across finish,
/// player milestone, and NBA ladder cards.
final class EventAtlasStoryCardsE3_11666Tests: XCTestCase {

    // MARK: - 1. Finish card mark key and winner badge

    func testFinishCardMarkKeyAndWinnerBadge() {
        let pregameOnly = NFLFinishCard9483(
            phase: .before,
            pregame: .init(away: 21.0, home: 24.5, at: Date(timeIntervalSince1970: 1_762_000_000)),
            projectedNow: nil,
            final: nil
        )
        XCTAssertEqual(
            EventAtlasStoryCards11666.finishMarkKey(for: pregameOnly).map(\.label),
            ["Pregame"]
        )
        XCTAssertNil(EventAtlasStoryCards11666.finishWinnerBadge(for: pregameOnly, isHome: true))
        XCTAssertNil(EventAtlasStoryCards11666.finishWinnerBadge(for: pregameOnly, isHome: false))

        let liveCard = NFLFinishCard9483(
            phase: .during,
            pregame: .init(away: 21.0, home: 24.5, at: nil),
            projectedNow: .init(away: 27.5, home: 20.5, at: Date(timeIntervalSince1970: 1_762_003_600)),
            final: nil
        )
        XCTAssertEqual(
            EventAtlasStoryCards11666.finishMarkKey(for: liveCard).map(\.label),
            ["Earlier forecast", "Recorded", "Change"]
        )

        let liveScheduledStartCard = NFLFinishCard9483(
            phase: .during,
            pregame: .init(away: 21.0, home: 24.5, at: nil),
            projectedNow: .init(away: 27.5, home: 20.5, at: Date(timeIntervalSince1970: 1_762_003_600)),
            final: nil,
            pregameBasis: .scheduledStart
        )
        XCTAssertEqual(
            EventAtlasStoryCards11666.finishMarkKey(for: liveScheduledStartCard).map(\.label),
            ["Pregame", "Recorded", "Change"]
        )

        let finishedCard = NFLFinishCard9483(
            phase: .after,
            pregame: .init(away: 21.0, home: 24.5, at: nil),
            projectedNow: nil,
            final: .init(away: 28, home: 21, at: Date(timeIntervalSince1970: 1_762_010_800)),
            pregameBasis: .scheduledStart
        )
        XCTAssertEqual(
            EventAtlasStoryCards11666.finishMarkKey(for: finishedCard).map(\.label),
            ["Pregame", "Final", "✓ Won"]
        )
        XCTAssertEqual(EventAtlasStoryCards11666.finishWinnerBadge(for: finishedCard, isHome: false), "✓ Won")
        XCTAssertNil(EventAtlasStoryCards11666.finishWinnerBadge(for: finishedCard, isHome: true))

        let tiedFinal = NFLFinishCard9483(
            phase: .after,
            pregame: .init(away: 21.0, home: 24.5, at: nil),
            projectedNow: nil,
            final: .init(away: 24, home: 24, at: nil)
        )
        XCTAssertEqual(
            EventAtlasStoryCards11666.finishMarkKey(for: tiedFinal).map(\.label),
            ["Earlier forecast", "Final"]
        )
        XCTAssertNil(EventAtlasStoryCards11666.finishWinnerBadge(for: tiedFinal, isHome: true))
        XCTAssertNil(EventAtlasStoryCards11666.finishWinnerBadge(for: tiedFinal, isHome: false))
    }

    // MARK: - 2. Milestone card mark key, verdict, and staleness copy

    func testMilestoneCardMarkKeyVerdictAndStalenessCopy() {
        let rungs: [NFLMilestoneCard9483.Rung] = [
            .init(threshold: 50, chance: 0.72, observedAt: "2026-11-06T20:00:00Z", rowID: "r1", hit: true),
            .init(threshold: 75, chance: 0.41, observedAt: "2026-11-06T20:00:00Z", rowID: "r2", hit: false),
            .init(threshold: 100, chance: nil, observedAt: nil, rowID: "r3", hit: nil)
        ]
        let settledCard = NFLMilestoneCard9483(
            id: "milestone-1",
            player: "CeeDee Lamb",
            stat: "Receiving Yards",
            side: .home,
            basis: .pregameMark,
            rungs: rungs,
            actual: 68
        )
        XCTAssertEqual(
            EventAtlasStoryCards11666.milestoneMarkKey(for: settledCard).map(\.label),
            ["Pregame", "Actual", "✓ HIT / ✗ MISS"]
        )
        XCTAssertEqual(
            EventAtlasStoryCards11666.milestoneVerdict(rungs[0], basis: .pregameMark, expanded: false),
            "✓ HIT"
        )
        XCTAssertEqual(
            EventAtlasStoryCards11666.milestoneVerdict(rungs[0], basis: .pregameMark, expanded: true),
            "✓ HIT · details"
        )
        XCTAssertEqual(
            EventAtlasStoryCards11666.milestoneVerdict(rungs[1], basis: .pregameMark, expanded: false),
            "✗ MISS"
        )
        XCTAssertEqual(
            EventAtlasStoryCards11666.milestoneNoChanceLabel(basis: .pregamePrice),
            "No recent probability"
        )
        XCTAssertEqual(
            EventAtlasStoryCards11666.milestoneNoChanceLabel(basis: .pregameMark),
            "No pregame chance"
        )
    }

    // MARK: - 3. NBA ladder card mark key and readout

    func testLadderCardMarkKeyAndReadout() {
        let hitDetail = NBALadderCard9483.Detail(
            label: "Over 218.5",
            marketName: "Total Points",
            source: "fanduel",
            quoted: nil,
            observedAt: "2026-11-06T20:00:00Z",
            baseline: 0.56,
            baselineObservedAt: "2026-11-06T19:00:00Z",
            result: true
        )
        let missDetail = NBALadderCard9483.Detail(
            label: "Over 228.5",
            marketName: "Total Points",
            source: "fanduel",
            quoted: nil,
            observedAt: "2026-11-06T20:00:00Z",
            baseline: 0.31,
            baselineObservedAt: "2026-11-06T19:00:00Z",
            result: false
        )
        let p1 = NBALadderCard9483.Point(
            optionKey: "o:1",
            x: 218.5,
            label: "Over 218.5",
            side: .game,
            chance: 0.56,
            now: 0.78,
            observedAt: "2026-11-06T20:00:00Z",
            result: true,
            detail: hitDetail
        )
        let p2 = NBALadderCard9483.Point(
            optionKey: "o:2",
            x: 228.5,
            label: "Over 228.5",
            side: .game,
            chance: nil,
            now: nil,
            observedAt: nil,
            result: false,
            detail: missDetail
        )
        let afterCard = NBALadderCard9483(
            family: .total,
            phase: .after,
            points: [p1, p2],
            actual: 224,
            forecast: 221.5,
            awayShort: "BOS",
            homeShort: "LAL"
        )
        XCTAssertEqual(
            EventAtlasStoryCards11666.ladderMarkKey(for: afterCard).map(\.label),
            ["Pregame", "Recorded", "Change", "Actual", "Projected", "✓ HIT / ✗ MISS"]
        )
        let r1 = EventAtlasStoryCards11666.ladderReadout(afterCard, p1)
        XCTAssertEqual(r1.main, "Over 218.5 · 56%")
        XCTAssertEqual(r1.sub, "Before tip-off · ✓ HIT · now 78%")

        let r2 = EventAtlasStoryCards11666.ladderReadout(afterCard, p2)
        XCTAssertEqual(r2.main, "Over 228.5")
        XCTAssertEqual(r2.sub, "Pregame chance unavailable · ✗ MISS")

        let beforeCard = NBALadderCard9483(
            family: .total,
            phase: .before,
            points: [p2],
            actual: nil,
            forecast: nil,
            awayShort: "BOS",
            homeShort: "LAL"
        )
        XCTAssertEqual(
            EventAtlasStoryCards11666.ladderReadout(beforeCard, p2).main,
            "Over 228.5 · No recent probability"
        )
    }

    // MARK: - 4. Shared details sheet models for finish, milestone, and ladder cards

    func testDetailsSheetModelsAcrossStoryCardFamilies() {
        let finish = NFLFinishCard9483(
            phase: .after,
            pregame: .init(away: 21.0, home: 24.5, at: nil),
            projectedNow: nil,
            final: .init(away: 28, home: 21, at: Date(timeIntervalSince1970: 1_762_010_800))
        )
        let finishSheet = EventAtlasStoryCards11666.detailsModel(
            for: finish,
            awayName: "Bills",
            homeName: "Chiefs"
        )
        XCTAssertEqual(finishSheet.primaryReadingLabel, "Final score")
        XCTAssertEqual(finishSheet.primaryReadingValue, "Bills 28 – Chiefs 21 · Bills ✓ Won")
        XCTAssertEqual(finishSheet.pregameBaseline, "Bills 21 · Chiefs 24.5")
        XCTAssertNil(finishSheet.sourceLabel)

        let prop = GameMarketPlayerProp(
            marketName: "Player Receiving Yards",
            outcomeName: "CeeDee Lamb: 75+",
            threshold: 75,
            overProbability: 0.48,
            source: "draftkings",
            movement: nil,
            playerHeadshot: nil,
            playerTeam: "DAL",
            actual: 88,
            hit: true,
            pregameMark: 0.42,
            observedAt: "2026-11-06T20:15:00Z"
        )
        let propSheet = EventAtlasStoryCards11666.detailsModel(
            for: prop,
            card: nil,
            rowID: prop.id
        )
        XCTAssertEqual(propSheet.outcomeTitle, "CeeDee Lamb: 75+")
        XCTAssertEqual(propSheet.primaryReadingLabel, "Result")
        XCTAssertEqual(propSheet.primaryReadingValue, "✓ HIT · Final 88")
        XCTAssertEqual(propSheet.pregameBaseline, "42%")
        XCTAssertEqual(propSheet.sourceLabel, "DraftKings")

        let detail = NBALadderCard9483.Detail(
            label: "Celtics by 6+",
            marketName: "Winning Margin",
            source: "kalshi",
            quoted: 0.64,
            observedAt: "2026-11-06T20:15:00Z",
            baseline: 0.51,
            baselineObservedAt: "2026-11-06T19:00:00Z",
            result: nil
        )
        let ladderSheet = EventAtlasStoryCards11666.detailsModel(for: detail)
        XCTAssertEqual(ladderSheet.outcomeTitle, "Celtics by 6+")
        XCTAssertEqual(ladderSheet.primaryReadingLabel, "Last quote")
        XCTAssertEqual(ladderSheet.primaryReadingValue, "64%")
        XCTAssertEqual(ladderSheet.sourceLabel, "Kalshi")
    }

    // MARK: - 5. Source wiring guard

    func testStoryCardViewsWireEventAtlasE3BehindFlag() throws {
        let testsDir = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        let appDir = testsDir.deletingLastPathComponent().appendingPathComponent("Bain Luck")
        let nflCards = try String(contentsOf: appDir.appendingPathComponent("Components/NFLEventCards9483.swift"), encoding: .utf8)
        let nbaCards = try String(contentsOf: appDir.appendingPathComponent("Components/NBAEventCards9483.swift"), encoding: .utf8)
        let reader = try String(contentsOf: appDir.appendingPathComponent("Components/NFLCardReader9483.swift"), encoding: .utf8)

        XCTAssertTrue(nflCards.contains("EventAtlasStoryCardMarkKeyView11666"))
        XCTAssertTrue(nflCards.contains("EventAtlasStoryCards11666.finishWinnerBadge"))
        XCTAssertTrue(nflCards.contains("EventAtlasStoryCards11666.milestoneVerdict"))
        XCTAssertTrue(nbaCards.contains("EventAtlasStoryCards11666.ladderMarkKey"))
        XCTAssertTrue(nbaCards.contains("EventAtlasStoryCards11666.ladderReadout"))
        XCTAssertTrue(reader.contains("EventAtlasStoryCards11666.readerDetailsModel"))
    }

    @MainActor
    func testMarkKeyAccessibilitySummaryAndScaledMetricRendering() throws {
        let liveFinish = NFLFinishCard9483(
            phase: .during,
            pregame: .init(away: 21, home: 24.5, at: Date(timeIntervalSince1970: 1_762_450_000)),
            projectedNow: .init(away: 17, home: 27, at: Date(timeIntervalSince1970: 1_762_455_000)),
            final: nil,
            pregameBasis: .scheduledStart
        )
        let items = EventAtlasStoryCards11666.finishMarkKey(for: liveFinish)
        XCTAssertEqual(
            EventAtlasStoryCards11666.markKeyAccessibilitySummary(items),
            "Mark key: Pregame, Recorded, Change"
        )
        XCTAssertEqual(EventAtlasStoryCards11666.markKeyAccessibilitySummary([]), "")

        // On a .pregamePrice milestone card, rung.chance is the current quote while prop.pregameMark is the pregame baseline
        let pregameCard = NFLMilestoneCard9483(
            id: "milestone-pre",
            player: "CeeDee Lamb",
            stat: "Receiving Yards",
            side: .home,
            basis: .pregamePrice,
            rungs: [.init(threshold: 75, chance: 0.54, observedAt: "2026-11-06T20:15:00Z", rowID: "r75", hit: nil)],
            actual: nil
        )
        let pregameProp = GameMarketPlayerProp(
            marketName: "Player Receiving Yards",
            outcomeName: "CeeDee Lamb: 75+",
            threshold: 75,
            overProbability: 0.54,
            source: "draftkings",
            movement: nil,
            playerHeadshot: nil,
            playerTeam: "DAL",
            actual: nil,
            hit: nil,
            pregameMark: 0.42,
            observedAt: "2026-11-06T20:15:00Z"
        )
        let pregameMilestoneSheet = EventAtlasStoryCards11666.detailsModel(
            for: pregameProp,
            card: pregameCard,
            rowID: "r75"
        )
        XCTAssertEqual(pregameMilestoneSheet.primaryReadingLabel, "Last quote")
        XCTAssertEqual(pregameMilestoneSheet.primaryReadingValue, "54%")
        XCTAssertEqual(pregameMilestoneSheet.pregameBaseline, "42%")

        let keyView = EventAtlasStoryCardMarkKeyView11666(items: items)
            .padding(12)
            .frame(width: 390, alignment: .leading)
            .background(Color(.systemBackground))
        let rDefault = rendererForMeasurement(keyView)
        rDefault.scale = 2.0
        let imgDefault = try XCTUnwrap(rDefault.uiImage)
        XCTAssertEqual(Int(imgDefault.size.width), 390)

        let rA11y = rendererForMeasurement(keyView, at: .accessibility3)
        rA11y.scale = 2.0
        let imgA11y = try XCTUnwrap(rA11y.uiImage)
        XCTAssertEqual(Int(imgA11y.size.width), 390)
        XCTAssertGreaterThanOrEqual(imgA11y.size.height, imgDefault.size.height)
    }
}
