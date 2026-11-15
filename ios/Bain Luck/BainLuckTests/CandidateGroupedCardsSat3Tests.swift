import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

@MainActor
final class CandidateGroupedCardsSat3Tests: XCTestCase {

    private static let expectedCandidateSlugs: [String] = [
        "roundup-ai-race",
        "roundup-as-likely-as",
        "roundup-big-movers-today",
        "roundup-ceremony-award-categories",
        "roundup-headliners-and-hosts",
        "roundup-long-shot-movers",
        "roundup-nba-award-ladders",
        "roundup-nba-division-races",
        "roundup-opening-weekend-slate",
        "roundup-team-active-streaks",
        "roundup-upsets-brewing",
    ]

    private func loadCandidateFeedItemsMap() throws -> [String: Data] {
        let fixtureURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .appendingPathComponent("Fixtures/discover_candidates_sat3_feed_items.json")
        let rawData = try Data(contentsOf: fixtureURL)
        let topObject = try XCTUnwrap(JSONSerialization.jsonObject(with: rawData) as? [String: Any])
        var out: [String: Data] = [:]
        for (slug, dict) in topObject {
            out[slug] = try JSONSerialization.data(withJSONObject: dict)
        }
        return out
    }

    private func decodeFeedResponse(itemsData: [Data]) throws -> FeedResponse {
        let joined = itemsData.compactMap { String(data: $0, encoding: .utf8) }.joined(separator: ",")
        let envelope = """
        {
          "items": [\(joined)],
          "total": \(itemsData.count),
          "limit": 20,
          "offset": 0,
          "has_more": false,
          "edition": "sat3-candidates-1"
        }
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(FeedResponse.self, from: Data(envelope.utf8))
    }

    func testAllElevenCandidatePayloadsDecodeAdmitGroupAndBuildEndToEnd() throws {
        let rawBySlug = try loadCandidateFeedItemsMap()
        XCTAssertEqual(rawBySlug.keys.sorted(), Self.expectedCandidateSlugs)

        let orderedData = try Self.expectedCandidateSlugs.map { try XCTUnwrap(rawBySlug[$0]) }
        let response = try decodeFeedResponse(itemsData: orderedData)
        XCTAssertEqual(response.items.count, 11, "Every candidate payload including float-scored items must decode")

        for item in response.items {
            XCTAssertTrue(DiscoverViewModel.isRenderable(item), "Candidate \(item.id) must pass DiscoverViewModel.isRenderable")
        }

        let fixedNow = try XCTUnwrap("2026-11-14T12:00:00Z".asDate)
        let sanitized = DiscoverView.sanitizedFeedItems(response.items, now: fixedNow)
        XCTAssertEqual(sanitized.count, 11, "sanitizedFeedItems must retain all 11 admitted round-up candidates")

        let grouped = DiscoverView.groupRelatedItems(sanitized)
        XCTAssertEqual(grouped.count, 11, "groupRelatedItems must emit 1 grouped card per round-up candidate")

        for (index, slug) in Self.expectedCandidateSlugs.enumerated() {
            guard case .group(let title, let members, let kind, _, _, let collectionRef) = grouped[index] else {
                return XCTFail("Expected .group for \(slug)")
            }
            XCTAssertEqual(kind, "roundup")
            XCTAssertEqual(collectionRef?.slug, slug)
            XCTAssertFalse(members.isEmpty, "Swipe dismiss keys require non-empty group members for \(slug)")

            let resolved = try XCTUnwrap(
                DiscoverView.resolveRoundupBundle(
                    title: title,
                    collectionRef: collectionRef,
                    groupItems: members,
                    feedItems: sanitized
                )
            )
            let model = try XCTUnwrap(
                DiscoverRoundupCardModel.build(
                    title: resolved.title,
                    contract: resolved.roundupContract,
                    now: fixedNow
                )
            )
            XCTAssertFalse(model.rows.isEmpty)
            XCTAssertNotNil(model.tag)
            XCTAssertNotNil(model.countLine)
            XCTAssertFalse(model.footer.isEmpty)
            XCTAssertEqual(
                DiscoverGroupRows.collectionRoute(for: try XCTUnwrap(collectionRef)),
                .containerHub(slug: slug, name: try XCTUnwrap(collectionRef?.name))
            )
        }
    }

    func testEventMixedSharedMarketDualBarAndStripShapes() throws {
        let rawBySlug = try loadCandidateFeedItemsMap()
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        // 1. Live game-event rows: roundup-upsets-brewing
        let upsetsItem = try decoder.decode(FeedItem.self, from: try XCTUnwrap(rawBySlug["roundup-upsets-brewing"]))
        let upsetsModel = try XCTUnwrap(
            DiscoverRoundupCardModel.build(
                title: upsetsItem.bundle?.title,
                contract: upsetsItem.bundle?.roundupContract
            )
        )
        XCTAssertEqual(upsetsModel.rows.count, 3)
        XCTAssertTrue(upsetsModel.rows.allSatisfy { $0.kind == .event && $0.cadence == .live })
        XCTAssertEqual(upsetsModel.rows[0].label, "Hornets 78–71 vs Celtics")
        XCTAssertEqual(upsetsModel.rows[0].detailCallout, "Q3 4:12 · +33 pts · 28% pregame")

        // 2. Upcoming game-event streak rows: roundup-team-active-streaks
        let streaksItem = try decoder.decode(FeedItem.self, from: try XCTUnwrap(rawBySlug["roundup-team-active-streaks"]))
        let streaksModel = try XCTUnwrap(
            DiscoverRoundupCardModel.build(
                title: streaksItem.bundle?.title,
                contract: streaksItem.bundle?.roundupContract
            )
        )
        XCTAssertEqual(streaksModel.rows.count, 5)
        XCTAssertTrue(streaksModel.rows.allSatisfy { $0.kind == .event })
        XCTAssertEqual(streaksModel.rows[0].label, "San Antonio Spurs (W11) · at Utah Jazz")
        XCTAssertEqual(streaksModel.rows[0].formattedPercentText, "89%")

        // 3. Mixed event + market yardstick band (`id` + `member_type`): roundup-as-likely-as
        let yardstickItem = try decoder.decode(FeedItem.self, from: try XCTUnwrap(rawBySlug["roundup-as-likely-as"]))
        let yardstickModel = try XCTUnwrap(
            DiscoverRoundupCardModel.build(
                title: yardstickItem.bundle?.title,
                contract: yardstickItem.bundle?.roundupContract
            )
        )
        XCTAssertEqual(yardstickModel.rows.count, 4)
        XCTAssertTrue(yardstickModel.rows.contains { $0.kind == .event })
        XCTAssertTrue(yardstickModel.rows.contains { $0.kind == .market })

        // 4. Shared multi-outcome market contenders: roundup-headliners-and-hosts
        let headlinersItem = try decoder.decode(FeedItem.self, from: try XCTUnwrap(rawBySlug["roundup-headliners-and-hosts"]))
        let headlinersModel = try XCTUnwrap(
            DiscoverRoundupCardModel.build(
                title: headlinersItem.bundle?.title,
                contract: headlinersItem.bundle?.roundupContract
            )
        )
        XCTAssertEqual(headlinersModel.rows.count, 5)

        // 5. Preserves closest-race container order (not re-sorted highest probability first)
        let awardsItem = try decoder.decode(FeedItem.self, from: try XCTUnwrap(rawBySlug["roundup-nba-award-ladders"]))
        let awardsModel = try XCTUnwrap(
            DiscoverRoundupCardModel.build(
                title: awardsItem.bundle?.title,
                contract: awardsItem.bundle?.roundupContract
            )
        )
        XCTAssertEqual(awardsModel.rows[0].label, "MVP · Victor Wembanyama")
        XCTAssertEqual(awardsModel.rows[0].detailCallout, "Runner-up · Luka Doncic 34%")

        // 6. Dual-bar ceremony rows (`secondary_probability`) + 3-up `presentation: "strip"`
        let dualBarModel = try XCTUnwrap(DiscoverRoundupCardModel.build(title: "99th Oscars — Best Picture contenders", contract: makeDualBarContract()))
        XCTAssertEqual(dualBarModel.rows[0].secondary?.formattedPercentText, "98%")
        XCTAssertEqual(dualBarModel.rows[0].formattedPercentText, "57%")

        let stripModel = try XCTUnwrap(DiscoverRoundupCardModel.build(title: "Celtics — next 3 games", contract: makeStripContract()))
        XCTAssertEqual(stripModel.presentation, .strip)
        XCTAssertEqual(stripModel.rows.map(\.opponentLabel), ["vs Knicks", "at Bucks", "vs Heat"])
    }

    func testRefusalsAndPriceAgeMarkRules() throws {
        let fixedNow = try XCTUnwrap("2026-11-14T16:00:00Z".asDate)

        // Missing collection_ref refuses the bundle
        let childlessRoundup = FeedBundle(
            id: "roundup:missing-ref",
            title: "The AI model race",
            items: [],
            kind: "roundup",
            comparisonTheme: nil,
            collectionRef: nil,
            roundupContract: makeStripContract()
        )
        XCTAssertFalse(childlessRoundup.admitsRoundupCard)

        // All rows old -> single footer stamp, zero per-row marks
        let allOldContract = FeedRoundupContract(
            kicker: "NBA · DIVISIONS",
            tag: "NBA",
            footer: "One winner per division",
            rows: [
                FeedRoundupRow(marketId: 101, label: "Southeast · Hawks", probability: 0.42, observedAt: "2026-11-13T08:00:00Z"),
                FeedRoundupRow(marketId: 102, label: "Atlantic · Celtics", probability: 0.48, observedAt: "2026-11-13T06:00:00Z"),
                FeedRoundupRow(marketId: 103, label: "Central · Cavaliers", probability: 0.56, observedAt: "2026-11-13T10:00:00Z"),
            ]
        )
        let allOldModel = try XCTUnwrap(DiscoverRoundupCardModel.build(title: "NBA division races", contract: allOldContract, now: fixedNow))
        XCTAssertEqual(allOldModel.cardMarkObservedAt, "2026-11-13T06:00:00Z")
        XCTAssertTrue(allOldModel.rows.allSatisfy { !$0.showsRowAgeMark })

        // Some rows old -> row mark only on old row, nil footer stamp
        let mixedAgeContract = FeedRoundupContract(
            kicker: "NBA · DIVISIONS",
            tag: "NBA",
            footer: "One winner per division",
            rows: [
                FeedRoundupRow(marketId: 101, label: "Southeast · Hawks", probability: 0.42, observedAt: "2026-11-14T15:30:00Z"),
                FeedRoundupRow(marketId: 102, label: "Atlantic · Celtics", probability: 0.48, observedAt: "2026-11-13T06:00:00Z"),
                FeedRoundupRow(marketId: 103, label: "Central · Cavaliers", probability: 0.56, observedAt: nil),
            ]
        )
        let mixedModel = try XCTUnwrap(DiscoverRoundupCardModel.build(title: "NBA division races", contract: mixedAgeContract, now: fixedNow))
        XCTAssertNil(mixedModel.cardMarkObservedAt)
        XCTAssertEqual(mixedModel.rows.map(\.showsRowAgeMark), [false, true, false])
    }

    func testAllElevenCandidatesPlusDualBarAndStripFit390AndAX2AndExportRenders() throws {
        let rawBySlug = try loadCandidateFeedItemsMap()
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let fixedNow = try XCTUnwrap("2026-11-14T12:00:00Z".asDate)

        var renderedCards: [(slug: String, model: DiscoverRoundupCardModel, ref: FeedThemeCollectionRef)] = []
        for slug in Self.expectedCandidateSlugs {
            let item = try decoder.decode(FeedItem.self, from: try XCTUnwrap(rawBySlug[slug]))
            let bundle = try XCTUnwrap(item.bundle)
            let ref = try XCTUnwrap(bundle.roundupCollectionRef)
            let model = try XCTUnwrap(DiscoverRoundupCardModel.build(title: bundle.title, contract: bundle.roundupContract, now: fixedNow))
            renderedCards.append((slug, model, ref))
        }

        let extraRef = try XCTUnwrap(FeedThemeCollectionRef(slug: "roundup-celtics-next-3", name: "Celtics next 3 games", revision: 1, collectionCount: 3))
        renderedCards.append(("roundup-dual-bar-ceremony", try XCTUnwrap(DiscoverRoundupCardModel.build(title: "99th Oscars — Best Picture contenders", contract: makeDualBarContract(), now: fixedNow)), extraRef))
        renderedCards.append(("roundup-strip-schedule", try XCTUnwrap(DiscoverRoundupCardModel.build(title: "Celtics — next 3 games", contract: makeStripContract(), now: fixedNow)), extraRef))

        for entry in renderedCards {
            for size in [DynamicTypeSize.large, .accessibility2] {
                let card = DiscoverRoundupCardView(model: entry.model, collectionRef: entry.ref, now: fixedNow, onOpenCollection: { _ in })
                    .padding(16)
                    .frame(width: 390)
                    .background(DS.surface)
                let host = hostForMeasurement(card, at: size)
                host.view.frame = CGRect(x: 0, y: 0, width: 390, height: 1800)
                host.view.setNeedsLayout()
                host.view.layoutIfNeeded()
                let measured = host.sizeThatFits(in: CGSize(width: 390, height: CGFloat.greatestFiniteMagnitude))
                XCTAssertLessThanOrEqual(measured.width, 390.5, "\(entry.slug) overflowed 390pt at \(size)")
                XCTAssertGreaterThan(measured.height, 140, "\(entry.slug) failed to render body at \(size)")
            }
        }

        if let exportDir = ProcessInfo.processInfo.environment["SAT3_EXPORT_DIR"], !exportDir.isEmpty {
            let dirURL = URL(fileURLWithPath: exportDir, isDirectory: true)
            try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)

            for entry in renderedCards {
                let cardView = DiscoverRoundupCardView(model: entry.model, collectionRef: entry.ref, now: fixedNow, onOpenCollection: { _ in })
                    .padding(16)
                    .frame(width: 390)
                    .background(DS.surface)
                let r = rendererForMeasurement(cardView, at: .large)
                r.scale = 2.0
                r.proposedSize = ProposedViewSize(width: 390, height: nil)
                let img = try XCTUnwrap(r.uiImage)
                let data = try XCTUnwrap(img.pngData())
                try data.write(to: dirURL.appendingPathComponent("sat3-\(entry.slug)-390.png"))
            }

            // Sheet 1: Event & mixed & mover shapes (6 cards)
            let sheet1Slugs: Set<String> = [
                "roundup-upsets-brewing",
                "roundup-team-active-streaks",
                "roundup-as-likely-as",
                "roundup-big-movers-today",
                "roundup-long-shot-movers",
                "roundup-strip-schedule",
            ]
            let sheet1 = VStack(spacing: 14) {
                ForEach(Array(renderedCards.filter { sheet1Slugs.contains($0.slug) }.enumerated()), id: \.offset) { _, entry in
                    DiscoverRoundupCardView(model: entry.model, collectionRef: entry.ref, now: fixedNow, onOpenCollection: { _ in })
                }
            }
            .padding(16)
            .frame(width: 390)
            .background(DS.surface)
            let r1 = rendererForMeasurement(sheet1, at: .large)
            r1.scale = 2.0
            r1.proposedSize = ProposedViewSize(width: 390, height: nil)
            try XCTUnwrap(r1.uiImage?.pngData()).write(to: dirURL.appendingPathComponent("sat3-sheet1-events-yardstick-movers-strip-390.png"))

            // Sheet 2: Leaderboard, awards, ceremony, box-office & stage shapes (7 cards)
            let sheet2 = VStack(spacing: 14) {
                ForEach(Array(renderedCards.filter { !sheet1Slugs.contains($0.slug) }.enumerated()), id: \.offset) { _, entry in
                    DiscoverRoundupCardView(model: entry.model, collectionRef: entry.ref, now: fixedNow, onOpenCollection: { _ in })
                }
            }
            .padding(16)
            .frame(width: 390)
            .background(DS.surface)
            let r2 = rendererForMeasurement(sheet2, at: .large)
            r2.scale = 2.0
            r2.proposedSize = ProposedViewSize(width: 390, height: nil)
            try XCTUnwrap(r2.uiImage?.pngData()).write(to: dirURL.appendingPathComponent("sat3-sheet2-leaderboards-ceremony-boxoffice-stage-390.png"))
        }
    }

    private func makeDualBarContract() -> FeedRoundupContract {
        FeedRoundupContract(
            kicker: "OSCARS 2027 · BEST PICTURE",
            tag: "AWARDS",
            subtitle: "Nomination chance alongside Winner chance across top contenders.",
            footer: "Single winner · up to 10 nominees",
            countLine: "3 leading contenders",
            rows: [
                FeedRoundupRow(
                    marketId: 6173044,
                    outcomeId: 1,
                    label: "The Odyssey",
                    probability: 0.565,
                    renderedPercent: 57,
                    secondaryProbability: 0.978,
                    secondaryRenderedPercent: 98,
                    primaryBarLabel: "Wins",
                    secondaryBarLabel: "Nominated"
                ),
                FeedRoundupRow(
                    marketId: 6173044,
                    outcomeId: 2,
                    label: "You Can See Everything",
                    probability: 0.165,
                    renderedPercent: 17,
                    secondaryProbability: 0.853,
                    secondaryRenderedPercent: 85,
                    primaryBarLabel: "Wins",
                    secondaryBarLabel: "Nominated"
                ),
                FeedRoundupRow(
                    marketId: 6173044,
                    outcomeId: 3,
                    label: "The Black Ball",
                    probability: 0.145,
                    renderedPercent: 15,
                    secondaryProbability: 0.945,
                    secondaryRenderedPercent: 95,
                    primaryBarLabel: "Wins",
                    secondaryBarLabel: "Nominated"
                ),
            ]
        )
    }

    private func makeStripContract() -> FeedRoundupContract {
        FeedRoundupContract(
            kicker: "NBA · NEXT 3 GAMES",
            tag: "SCHEDULE",
            footer: "Win chance per game in schedule order",
            countLine: "3 upcoming games",
            order: "sequence",
            presentation: "strip",
            rows: [
                FeedRoundupRow(eventId: 9001, label: "vs Knicks · Sun Nov 15", opponentLabel: "vs Knicks", dateLabel: "Sun Nov 15", probability: 0.64, renderedPercent: 64),
                FeedRoundupRow(eventId: 9002, label: "at Bucks · Tue Nov 17", opponentLabel: "at Bucks", dateLabel: "Tue Nov 17", probability: 0.52, renderedPercent: 52),
                FeedRoundupRow(eventId: 9003, label: "vs Heat · Thu Nov 19", opponentLabel: "vs Heat", dateLabel: "Thu Nov 19", probability: 0.73, renderedPercent: 73),
            ]
        )
    }
}
