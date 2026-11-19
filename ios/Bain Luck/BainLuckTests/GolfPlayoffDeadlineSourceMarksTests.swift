import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// #12893, #12887, #12884 — Draws the served `source_mark` across the three newly
/// live production surfaces on commit `7a8ab80e`:
///   1. Golfer tournament prices (`#12893`: `GolfGolferData.sourceMark` & `FeedTournamentGolfer.sourceMark`
///      on `GolfTournamentView`, `EventAtlasGolfContenderChooserView11666`, `TournamentHeroCard`,
///      and `NativeTournamentDiscoverCard`).
///   2. Playoff field cards (`#12887`: `FeedRoundupRow.sourceMark` on `DiscoverRoundupCardView`
///      and `FeedDiscoverDistributionOutcome.sourceMark` on `DistributionCardView`).
///   3. Cumulative deadline cards (`#12884`: `FeedDeadlineMemberContract` `source_mark` & `no_source_mark`
///      on `NativeFuturesDiscoverCard` Yes/No rows + hero and `NativeGroupCard` compact rows).
@MainActor
final class GolfPlayoffDeadlineSourceMarksTests: XCTestCase {

    private let fixedNow = ISO8601DateFormatter().date(from: "2026-11-18T22:40:00Z")!

    private func decodeSnake<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(T.self, from: Data(json.utf8))
    }

    private func captureView<V: View>(
        _ view: V,
        width: CGFloat = 390,
        fixedHeight: CGFloat? = nil,
        scheme: ColorScheme = .light,
        at size: DynamicTypeSize = .large
    ) -> UIImage {
        let bg = scheme == .dark ? Color.black : Color(UIColor.systemGroupedBackground)
        let sizedContent: AnyView = {
            if let fixedHeight {
                return AnyView(
                    view
                        .frame(width: width, height: fixedHeight, alignment: .topLeading)
                        .background(bg)
                        .environment(\.colorScheme, scheme)
                )
            }
            return AnyView(
                view
                    .frame(width: width, alignment: .topLeading)
                    .fixedSize(horizontal: false, vertical: true)
                    .background(bg)
                    .environment(\.colorScheme, scheme)
            )
        }()

        let measureHost = hostForMeasurement(sizedContent, at: size)
        measureHost.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        let fittingH = fixedHeight ?? min(max(measureHost.sizeThatFits(in: CGSize(width: width, height: 2_400)).height + 16, 160), 2_400)

        let host = hostForMeasurement(sizedContent, at: size)
        host.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: CGRect(x: 0, y: 0, width: width, height: fittingH))
        window.frame = CGRect(x: 0, y: 0, width: width, height: fittingH)
        host.view.frame = window.bounds
        window.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        for _ in 0..<3 {
            if fixedHeight == nil {
                let nextH = min(max(host.sizeThatFits(in: CGSize(width: width, height: 2_400)).height + 16, fittingH), 2_400)
                if abs(nextH - window.frame.height) > 0.5 {
                    window.frame = CGRect(x: 0, y: 0, width: width, height: nextH)
                    host.view.frame = window.bounds
                }
            }
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
        }

        let topInset = fixedHeight == nil ? host.view.safeAreaInsets.top : 0
        let cropSize = CGSize(width: width, height: max(host.view.bounds.height - topInset, 140))
        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 3.0
        fmt.opaque = true
        return UIGraphicsImageRenderer(size: cropSize, format: fmt).image { _ in
            _ = host.view.drawHierarchy(
                in: CGRect(x: 0, y: -topInset, width: width, height: host.view.bounds.height),
                afterScreenUpdates: true
            )
        }
    }

    private func ocrLines(_ image: UIImage) throws -> [String] {
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: XCTUnwrap(image.cgImage)).perform([req])
        return (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
    }

    private func writeRenderIfEnabled(_ image: UIImage, name: String) throws {
        let dir = URL(fileURLWithPath: "/tmp/renders-12893-12887-12884", isDirectory: true)
        guard FileManager.default.fileExists(atPath: dir.path) else { return }
        let data = try XCTUnwrap(image.pngData())
        try data.write(to: dir.appendingPathComponent("\(name).png"))
    }

    // MARK: - Live Production Payloads (captured from 7a8ab80e)

    private func rsmClassicDetailJSON() -> String {
        """
        {
          "tournament": {
            "name": "The RSM Classic",
            "slug": "the-rsm-classic",
            "key": "the_rsm_classic",
            "is_major": false,
            "is_womens": false,
            "start_date": "2026-11-19T00:00:00+00:00",
            "end_date": "2026-11-22T00:00:00+00:00",
            "venue": "Sea Island Golf Club (Seaside Course)",
            "location": "Sea Island, GA",
            "schedule_status": "upcoming",
            "commence_time": "2026-11-19T17:04:00+00:00",
            "resolution_date": "2026-11-22T00:00:00+00:00",
            "tour": "pga",
            "tour_label": "PGA Tour"
          },
          "golfers": [
            {
              "name": "Ben James",
              "probability": 0.046,
              "movement_24h": -0.0015,
              "opening_probability": 0.042,
              "rank": 1,
              "source_mark": {
                "state": "blend",
                "sources": [
                  { "key": "kalshi", "name": "Kalshi", "probability": 0.061, "observed_at": null, "reason": "observation_unknown" },
                  { "key": "polymarket", "name": "Polymarket", "probability": 0.0355, "observed_at": null, "reason": "observation_unknown" },
                  { "key": "datagolf", "name": "DataGolf", "probability": 0.041583, "observed_at": null, "reason": "observation_unknown" }
                ],
                "method": "Bain Luck blend · the average of these sources"
              }
            },
            {
              "name": "Michael Brennan",
              "probability": 0.036,
              "movement_24h": 0.0048,
              "opening_probability": 0.03,
              "rank": 2,
              "source_mark": {
                "state": "blend",
                "sources": [
                  { "key": "kalshi", "name": "Kalshi", "probability": 0.038, "observed_at": null, "reason": "observation_unknown" },
                  { "key": "polymarket", "name": "Polymarket", "probability": 0.0395, "observed_at": null, "reason": "observation_unknown" },
                  { "key": "datagolf", "name": "DataGolf", "probability": 0.030167, "observed_at": null, "reason": "observation_unknown" }
                ],
                "method": "Bain Luck blend · the average of these sources"
              }
            },
            {
              "name": "Blades Brown",
              "probability": 0.036,
              "movement_24h": null,
              "opening_probability": 0.034,
              "rank": 3,
              "source_mark": {
                "state": "blend",
                "sources": [
                  { "key": "kalshi", "name": "Kalshi", "probability": 0.037, "observed_at": null, "reason": "observation_unknown" },
                  { "key": "polymarket", "name": "Polymarket", "probability": 0.042, "observed_at": null, "reason": "observation_unknown" },
                  { "key": "datagolf", "name": "DataGolf", "probability": 0.027633, "observed_at": null, "reason": "observation_unknown" }
                ],
                "method": "Bain Luck blend · the average of these sources"
              }
            },
            {
              "name": "Doug Ghim",
              "probability": 0.032,
              "movement_24h": 0.0012,
              "opening_probability": 0.048,
              "rank": 4,
              "source_mark": {
                "state": "blend",
                "sources": [
                  { "key": "kalshi", "name": "Kalshi", "probability": 0.0275, "observed_at": null, "reason": "observation_unknown" },
                  { "key": "polymarket", "name": "Polymarket", "probability": 0.03, "observed_at": null, "reason": "observation_unknown" },
                  { "key": "datagolf", "name": "DataGolf", "probability": 0.038483, "observed_at": null, "reason": "observation_unknown" }
                ],
                "method": "Bain Luck blend · the average of these sources"
              }
            },
            {
              "name": "Brian Harman",
              "probability": 0.029,
              "movement_24h": -0.0042,
              "opening_probability": 0.022,
              "rank": 5,
              "source_mark": {
                "state": "blend",
                "sources": [
                  { "key": "kalshi", "name": "Kalshi", "probability": 0.0305, "observed_at": null, "reason": "observation_unknown" },
                  { "key": "polymarket", "name": "Polymarket", "probability": 0.023, "observed_at": null, "reason": "observation_unknown" },
                  { "key": "datagolf", "name": "DataGolf", "probability": 0.032017, "observed_at": null, "reason": "observation_unknown" }
                ],
                "method": "Bain Luck blend · the average of these sources"
              }
            }
          ],
          "overflow_outcomes": [],
          "markets": [],
          "round_top_groups": []
        }
        """
    }

    private func cfpPlayoffRoundupBundleJSON() -> String {
        """
        {
          "id": "roundup:cfp-picture",
          "title": "College Football Playoff picture",
          "kind": "roundup",
          "story_key": "roundup:cfp-picture",
          "item_count": 2,
          "member_ids": [227, 181],
          "collection_ref": {
            "slug": "roundup-cfp-picture",
            "name": "College Football Playoff picture",
            "revision": 2684068319,
            "collection_count": 2
          },
          "roundup": {
            "kicker": "Round-up",
            "tag": "NCAAF",
            "footer": "Chance to make the 12-team field · teams between 20% and 80%",
            "rows": [
              {
                "market_id": 227,
                "outcome_id": 1831,
                "label": "Tennessee",
                "probability": 0.645,
                "source_mark": {
                  "state": "single",
                  "sources": [{ "key": "kalshi", "name": "Kalshi", "probability": 0.645, "observed_at": null, "reason": "observation_unknown" }]
                },
                "observed_at": "2026-11-18T22:35:47.686927+00:00"
              },
              {
                "market_id": 227,
                "outcome_id": 1861,
                "label": "BYU",
                "probability": 0.475,
                "source_mark": {
                  "state": "single",
                  "sources": [{ "key": "kalshi", "name": "Kalshi", "probability": 0.475, "observed_at": null, "reason": "observation_unknown" }]
                },
                "observed_at": "2026-11-18T22:35:47.686927+00:00"
              },
              {
                "market_id": 227,
                "outcome_id": 1829,
                "label": "Texas Tech",
                "probability": 0.475,
                "source_mark": {
                  "state": "single",
                  "sources": [{ "key": "kalshi", "name": "Kalshi", "probability": 0.475, "observed_at": null, "reason": "observation_unknown" }]
                },
                "observed_at": "2026-11-18T22:35:47.686927+00:00"
              },
              {
                "market_id": 227,
                "outcome_id": 1838,
                "label": "Oregon",
                "probability": 0.375,
                "source_mark": {
                  "state": "single",
                  "sources": [{ "key": "kalshi", "name": "Kalshi", "probability": 0.375, "observed_at": null, "reason": "observation_unknown" }]
                },
                "observed_at": "2026-11-18T22:35:47.686927+00:00"
              }
            ]
          },
          "items": []
        }
        """
    }

    private func deadlineFuturesJSON() -> String {
        """
        {
          "id": 13795456,
          "name": "Iran leadership change by December 31?",
          "sport": null,
          "sport_name": null,
          "category": "geopolitics",
          "llm_sport_category": "politics",
          "market_tier": 2,
          "market_type": "container_member",
          "status": "open",
          "source": "polymarket",
          "sources": ["polymarket"],
          "source_count": 1,
          "mutually_exclusive": true,
          "resolution_date": "2026-12-31T00:00:00+00:00",
          "price_observed_at": "2026-11-18T22:30:00+00:00",
          "top_outcomes": [
            {
              "id": 125650217,
              "name": "No",
              "probability": 0.935,
              "rank": 1,
              "movement": null,
              "rendered_percent": 94
            },
            {
              "id": 125650216,
              "name": "Yes",
              "probability": 0.065,
              "rank": 2,
              "movement": null,
              "rendered_percent": 6
            }
          ],
          "deadline_member": {
            "yes_probability": 0.065,
            "yes_rendered_percent": 6,
            "no_probability": 0.935,
            "source_mark": {
              "state": "single",
              "sources": [{ "key": "polymarket", "name": "Polymarket", "probability": 0.065, "observed_at": null, "reason": "observation_unknown" }],
              "method": "The source gave 6.5%. The card rounds it to 6%."
            },
            "no_source_mark": {
              "state": "single",
              "sources": [{ "key": "polymarket", "name": "Polymarket", "probability": 0.935, "observed_at": null, "reason": "observation_unknown" }]
            }
          }
        }
        """
    }

    private func warshNamedOutcomesDeadlineJSON() -> String {
        """
        {
          "id": 56995847,
          "name": "Will Warsh be out as Fed Chair by June 30, 2027?",
          "category": "economics",
          "llm_sport_category": "economics",
          "market_tier": 2,
          "market_type": "container_member",
          "status": "open",
          "source": "polymarket",
          "sources": ["polymarket"],
          "source_count": 1,
          "mutually_exclusive": true,
          "top_outcomes": [
            { "id": 211594121, "name": "Not Warsh", "probability": 0.945, "rank": 1, "rendered_percent": 95 },
            { "id": 211594120, "name": "Warsh", "probability": 0.055, "rank": 2, "rendered_percent": 5 }
          ],
          "deadline_member": {
            "yes_probability": 0.055,
            "yes_rendered_percent": 5,
            "no_probability": 0.945,
            "source_mark": {
              "state": "single",
              "sources": [{ "key": "polymarket", "name": "Polymarket", "probability": 0.055, "observed_at": null, "reason": "observation_unknown" }],
              "method": "The source gave 5.5%. The card rounds it to 5%."
            },
            "no_source_mark": {
              "state": "single",
              "sources": [{ "key": "polymarket", "name": "Polymarket", "probability": 0.945, "observed_at": null, "reason": "observation_unknown" }]
            }
          }
        }
        """
    }

    // MARK: - 1. Golf Tournament Source Marks (#12893)

    func testGolfTournamentDecodesAndRendersServedSourceMarks() throws {
        let detail = try decodeSnake(GolfTournamentDetailResponse.self, rsmClassicDetailJSON())
        let presentation = GolfTournamentPresentation(response: detail)
        XCTAssertEqual(presentation.field.count, 5)
        let leader = try XCTUnwrap(presentation.field.first)
        XCTAssertEqual(leader.name, "Ben James")
        XCTAssertEqual(leader.sourceMark?.state, .blend)
        XCTAssertEqual(leader.sourceMark?.sources.map(\.name), ["Kalshi", "Polymarket", "DataGolf"])
        XCTAssertEqual(leader.sourceMark?.method, "Bain Luck blend · the average of these sources")
        XCTAssertNotNil(SourceMarkButton(leader.sourceMark, number: leader.probability, numberSize: 15, compactRow: true))

        let rawObj = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(rsmClassicDetailJSON().utf8)) as? [String: Any])
        var flatObj = try XCTUnwrap(rawObj["tournament"] as? [String: Any])
        flatObj["golfers"] = rawObj["golfers"]
        flatObj["overflow_outcomes"] = rawObj["overflow_outcomes"]
        let flatData = try JSONSerialization.data(withJSONObject: flatObj)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let heroData = try decoder.decode(GolfTournamentData.self, from: flatData)
        let feedTournament = try decoder.decode(FeedTournamentData.self, from: flatData)
        XCTAssertEqual(feedTournament.golfers?.first?.sourceMark?.sources.map(\.name), ["Kalshi", "Polymarket", "DataGolf"])

        let heroView = TournamentHeroCard(tournament: heroData, now: fixedNow)
            .padding(16)
        let lightHero = captureView(heroView, scheme: .light, at: .large)
        let darkHero = captureView(heroView, scheme: .dark, at: .large)
        let ax5Hero = captureView(heroView, scheme: .light, at: .accessibility5)

        let lines = try ocrLines(lightHero)
        XCTAssertFalse(lines.contains(where: { $0.contains("…") }), "Golf hero must not truncate: \(lines)")
        XCTAssertTrue(lines.joined(separator: " ").contains("Ben James"), "Golf hero must read Ben James: \(lines)")
        let ax5Lines = try ocrLines(ax5Hero)
        XCTAssertFalse(ax5Lines.contains(where: { $0.contains("…") }), "Golf hero AX5 must not truncate: \(ax5Lines)")

        let sheetMark = try XCTUnwrap(leader.sourceMark)
        XCTAssertTrue(leader.probabilityLabel.contains("."), "Golf row prints tenths: \(leader.probabilityLabel)")
        XCTAssertEqual(SourceMarkSheet.headline(leader.probability, showsTenths: true), "4.6%")
        XCTAssertEqual(SourceMarkSheet.lines(sheetMark, showsTenths: true).map(\.price), ["6.1%", "3.5%", "4.2%"])

        let lightSheet = captureView(
            SourceMarkSheet(
                mark: sheetMark,
                number: leader.probability,
                subject: leader.name,
                showsTenths: leader.probabilityLabel.contains("."),
                now: fixedNow
            ),
            fixedHeight: 380,
            scheme: .light
        )
        let darkSheet = captureView(
            SourceMarkSheet(
                mark: sheetMark,
                number: leader.probability,
                subject: leader.name,
                showsTenths: leader.probabilityLabel.contains("."),
                now: fixedNow
            ),
            fixedHeight: 380,
            scheme: .dark
        )
        let sheetLines = try ocrLines(lightSheet)
        let sheetJoined = sheetLines.joined(separator: " ")
        XCTAssertTrue(sheetJoined.contains("4.6%"), "Golf sheet headline must print 4.6% when row prints tenths: \(sheetLines)")
        XCTAssertTrue(sheetJoined.contains("6.1%") && sheetJoined.contains("4.2%"), "Golf sheet sources must print tenths: \(sheetLines)")
        XCTAssertTrue(sheetJoined.contains("Kalshi") && sheetJoined.contains("Polymarket") && sheetJoined.contains("DataGolf"),
                      "Golf sheet must list all 3 contributing sources: \(sheetLines)")

        try writeRenderIfEnabled(lightHero, name: "12893-golf-hero-light-390")
        try writeRenderIfEnabled(darkHero, name: "12893-golf-hero-dark-390")
        try writeRenderIfEnabled(lightSheet, name: "12893-golf-sheet-light-390")
        try writeRenderIfEnabled(darkSheet, name: "12893-golf-sheet-dark-390")
    }

    // MARK: - 2. Playoff Field Round-Up & Distribution Source Marks (#12887)

    func testPlayoffFieldRoundupAndDistributionRenderServedSourceMarks() throws {
        let bundle = try decodeSnake(FeedBundle.self, cfpPlayoffRoundupBundleJSON())
        XCTAssertTrue(bundle.admitsRoundupCard)
        let model = try XCTUnwrap(DiscoverRoundupCardModel.build(title: bundle.title, contract: bundle.roundupContract, now: fixedNow))
        XCTAssertTrue(model.hasAnySourceMark)
        XCTAssertEqual(model.rows.count, 4)
        XCTAssertEqual(model.rows[0].label, "Tennessee")
        XCTAssertEqual(model.rows[0].sourceMark?.sources.first?.name, "Kalshi")

        let card = DiscoverRoundupCardView(
            model: model,
            collectionRef: bundle.roundupCollectionRef,
            now: fixedNow,
            onOpenCollection: { _ in }
        )
        .padding(16)

        let lightCard = captureView(card, scheme: .light, at: .large)
        let darkCard = captureView(card, scheme: .dark, at: .large)
        let ax5Card = captureView(card, scheme: .light, at: .accessibility5)

        let lines = try ocrLines(lightCard)
        let joined = lines.joined(separator: " ")
        XCTAssertFalse(lines.contains(where: { $0.contains("…") }), "CFP roundup card must not truncate: \(lines)")
        for team in ["Tennessee", "BYU", "Texas Tech", "Oregon"] {
            XCTAssertTrue(joined.contains(team), "CFP roundup card missing \(team): \(lines)")
        }
        let ax5Lines = try ocrLines(ax5Card)
        XCTAssertFalse(ax5Lines.contains(where: { $0.contains("…") }), "CFP roundup AX5 must not truncate: \(ax5Lines)")

        let tennMark = try XCTUnwrap(model.rows[0].sourceMark)
        let lightSheet = captureView(SourceMarkSheet(mark: tennMark, number: model.rows[0].rawProbability, subject: model.rows[0].label, now: fixedNow), fixedHeight: 320, scheme: .light)
        let darkSheet = captureView(SourceMarkSheet(mark: tennMark, number: model.rows[0].rawProbability, subject: model.rows[0].label, now: fixedNow), fixedHeight: 320, scheme: .dark)

        try writeRenderIfEnabled(lightCard, name: "12887-cfp-roundup-light-390")
        try writeRenderIfEnabled(darkCard, name: "12887-cfp-roundup-dark-390")
        try writeRenderIfEnabled(lightSheet, name: "12887-cfp-sheet-light-390")
        try writeRenderIfEnabled(darkSheet, name: "12887-cfp-sheet-dark-390")
    }

    // MARK: - 3. Cumulative Deadline Yes & No Source Marks (#12884)

    func testCumulativeDeadlineResolvesBothYesAndNoSourceMarksAcrossStandaloneAndBundleRows() throws {
        let futures = try decodeSnake(FeedFuturesData.self, deadlineFuturesJSON())
        let outcomes = try XCTUnwrap(futures.topOutcomes)
        XCTAssertEqual(outcomes.count, 2)

        let noMark = try XCTUnwrap(futures.resolvedSourceMark(for: outcomes[0]))
        let yesMark = try XCTUnwrap(futures.resolvedSourceMark(for: outcomes[1]))
        XCTAssertEqual(noMark.sources.first?.probability, 0.935)
        XCTAssertNil(noMark.method)
        XCTAssertEqual(yesMark.sources.first?.probability, 0.065)
        XCTAssertEqual(yesMark.method, "The source gave 6.5%. The card rounds it to 6%.")

        // Also verify named non-Yes/No binary outcomes ("Not Warsh" / "Warsh") match cleanly
        let warsh = try decodeSnake(FeedFuturesData.self, warshNamedOutcomesDeadlineJSON())
        let warshOutcomes = try XCTUnwrap(warsh.topOutcomes)
        let notWarshMark = try XCTUnwrap(warsh.resolvedSourceMark(for: warshOutcomes[0]))
        let yesWarshMark = try XCTUnwrap(warsh.resolvedSourceMark(for: warshOutcomes[1]))
        XCTAssertEqual(notWarshMark.sources.first?.probability, 0.945)
        XCTAssertEqual(yesWarshMark.sources.first?.probability, 0.055)
        XCTAssertEqual(yesWarshMark.method, "The source gave 5.5%. The card rounds it to 5%.")

        // Verify compactSummary for NativeGroupCard carries the leader's resolved mark
        let summary = DiscoverGroupRows.compactSummary(for: warsh)
        XCTAssertEqual(summary.label, "Not Warsh")
        XCTAssertEqual(summary.sourceMark?.sources.first?.probability, 0.945)

        let pinManager = PinManager(defaults: UserDefaults(suiteName: "test.deadline.12884")!)
        let cardView = NativeFuturesDiscoverCard(
            data: futures,
            feedContext: "Cumulative deadline market",
            expandedContext: nil,
            navigationPath: .constant(NavigationPath())
        )
        .environmentObject(pinManager)
        .padding(16)

        let lightCard = captureView(cardView, scheme: .light, at: .large)
        let darkCard = captureView(cardView, scheme: .dark, at: .large)
        let lines = try ocrLines(lightCard)
        let joined = lines.joined(separator: " ")
        XCTAssertTrue(joined.contains("94%") && joined.contains("6%"),
                      "Deadline card must render both No (94%) and Yes (6%): \(lines)")

        let lightYesSheet = captureView(SourceMarkSheet(mark: yesMark, number: 0.06, subject: "Yes", now: fixedNow), fixedHeight: 320, scheme: .light)
        let darkYesSheet = captureView(SourceMarkSheet(mark: yesMark, number: 0.06, subject: "Yes", now: fixedNow), fixedHeight: 320, scheme: .dark)
        let sheetLines = try ocrLines(lightYesSheet)
        XCTAssertTrue(sheetLines.joined(separator: " ").contains("6.5%"),
                      "Yes deadline sheet must explain half-point rounding from 6.5% to 6%: \(sheetLines)")

        try writeRenderIfEnabled(lightCard, name: "12884-deadline-card-light-390")
        try writeRenderIfEnabled(darkCard, name: "12884-deadline-card-dark-390")
        try writeRenderIfEnabled(lightYesSheet, name: "12884-deadline-yes-sheet-light-390")
        try writeRenderIfEnabled(darkYesSheet, name: "12884-deadline-yes-sheet-dark-390")
    }
}
