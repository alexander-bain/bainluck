import Foundation
import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

@MainActor
final class SportsShorterRows13013Tests: XCTestCase {

    private nonisolated struct FakeSportsProvider13013: SportsFeedProviding, @unchecked Sendable {
        let main: FeedResponse
        let backfill: FeedResponse
        let grouped: GroupedFeedResponse

        nonisolated func fetchSportsFeed() async throws -> FeedResponse { main }
        nonisolated func fetchSportsEventBackfill(limit: Int) async throws -> FeedResponse { backfill }
        nonisolated func fetchSportsGroupedFeed(limit: Int) async throws -> GroupedFeedResponse { grouped }
    }

    private final class SportsTraitContainer: UIViewController {
        let child: UIViewController
        let traits: UITraitCollection

        init(child: UIViewController, traits: UITraitCollection) {
            self.child = child
            self.traits = traits
            super.init(nibName: nil, bundle: nil)
        }

        required init?(coder: NSCoder) { fatalError("unused") }

        override func viewDidLoad() {
            super.viewDidLoad()
            addChild(child)
            child.view.frame = view.bounds
            child.view.autoresizingMask = [.flexibleWidth, .flexibleHeight]
            view.addSubview(child.view)
            child.didMove(toParent: self)
            setOverrideTraitCollection(traits, forChild: child)
        }
    }

    func testSportsListOmitsFollowBarWhileDirectEventCardKeepsIt() async throws {
        let now = Date()
        let iso = ISO8601DateFormatter()
        let liveEarlier = iso.string(from: now.addingTimeInterval(-3600))
        let liveLater = iso.string(from: now.addingTimeInterval(-1800))
        let up1 = iso.string(from: now.addingTimeInterval(2 * 3600))
        let up2 = iso.string(from: now.addingTimeInterval(4 * 3600))

        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        let feedJSON = """
        {
          "items": [
            {"type":"event","score":95,"data":{"id":7101,"sport":"basketball_nba","sport_name":"NBA","status":"live","away_team":"Celtics","home_team":"Knicks","commence_time":"\(liveEarlier)","away_score":81,"home_score":76,"away_team_data":{"team_id":101,"abbreviation":"BOS","primary_color":"#007A33"},"home_team_data":{"team_id":102,"abbreviation":"NYK","primary_color":"#006BB6"},"current_odds":{"away_probability":0.62,"home_probability":0.38},"opening_odds":{"away_probability":0.55,"home_probability":0.45},"espn":{"period":"Q3","game_clock":"4:12"}}},
            {"type":"event","score":90,"data":{"id":7102,"sport":"basketball_nba","sport_name":"NBA","status":"live","away_team":"Clippers","home_team":"Lakers","commence_time":"\(liveLater)","away_score":54,"home_score":58,"away_team_data":{"team_id":103,"abbreviation":"LAC","primary_color":"#C8102E"},"home_team_data":{"team_id":104,"abbreviation":"LAL","primary_color":"#552583"},"current_odds":{"away_probability":0.41,"home_probability":0.59},"opening_odds":{"away_probability":0.48,"home_probability":0.52},"espn":{"period":"Q2","game_clock":"2:05"}}},
            {"type":"event","score":85,"data":{"id":7103,"sport":"icehockey_nhl","sport_name":"NHL","status":"live","away_team":"Stars","home_team":"Oilers","commence_time":"\(liveEarlier)","away_score":2,"home_score":2,"away_team_data":{"team_id":105,"abbreviation":"DAL","primary_color":"#006847"},"home_team_data":{"team_id":106,"abbreviation":"EDM","primary_color":"#041E42"},"current_odds":{"away_probability":0.48,"home_probability":0.52},"opening_odds":{"away_probability":0.46,"home_probability":0.54},"espn":{"period":"2nd","game_clock":"11:18"}}},
            {"type":"event","score":80,"data":{"id":7104,"sport":"americanfootball_nfl","sport_name":"NFL","status":"scheduled","away_team":"Bills","home_team":"Lions","commence_time":"\(up1)","away_team_data":{"team_id":107,"abbreviation":"BUF","primary_color":"#00338D"},"home_team_data":{"team_id":108,"abbreviation":"DET","primary_color":"#0076B6"},"current_odds":{"away_probability":0.44,"home_probability":0.56},"opening_odds":{"away_probability":0.45,"home_probability":0.55}}},
            {"type":"event","score":75,"data":{"id":7105,"sport":"basketball_ncaab","sport_name":"NCAAB","status":"scheduled","away_team":"Duke","home_team":"Kansas","commence_time":"\(up2)","away_team_data":{"team_id":109,"abbreviation":"DUKE","primary_color":"#003087"},"home_team_data":{"team_id":110,"abbreviation":"KU","primary_color":"#0051BA"},"current_odds":{"away_probability":0.51,"home_probability":0.49},"opening_odds":{"away_probability":0.50,"home_probability":0.50}}}
          ],
          "total": 5, "limit": 50, "offset": 0, "has_more": false
        }
        """
        let feed = try dec.decode(FeedResponse.self, from: Data(feedJSON.utf8))
        let emptyBackfill = try dec.decode(FeedResponse.self, from: Data(#"{"items":[],"total":0,"limit":200,"offset":0,"has_more":false}"#.utf8))
        let emptyGrouped = try dec.decode(GroupedFeedResponse.self, from: Data(#"{"feed":[],"total":0,"limit":20,"offset":0}"#.utf8))

        let firstEvent = try XCTUnwrap(feed.items.first?.event)
        let beforeCard = VStack { EventCardView(event: firstEvent, reason: nil) }.padding(16)
        let afterCard = VStack { EventCardView(event: firstEvent, reason: nil, showsTeamFollowBar: false) }.padding(16)
        let beforeCardImg = await render390(view: beforeCard, scheme: .light, typeSize: .large, height: 320)
        let afterCardImg = await render390(view: afterCard, scheme: .light, typeSize: .large, height: 320)
        let beforeText = try ocrLines(beforeCardImg).joined(separator: " ")
        let afterText = try ocrLines(afterCardImg).joined(separator: " ")
        XCTAssertTrue(beforeText.contains("Follow"), "Direct EventCardView default must still show Follow chips: \(beforeText)")
        XCTAssertFalse(afterText.contains("Follow"), "showsTeamFollowBar: false must hide Follow chips: \(afterText)")

        let outPath = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_13013_DIR"]
        if let outPath, !outPath.isEmpty {
            try FileManager.default.createDirectory(atPath: outPath, withIntermediateDirectories: true)
        }

        for (tag, scheme, typeSize, height) in [
            ("after-reg-light", ColorScheme.light, DynamicTypeSize.large, CGFloat(852)),
            ("after-reg-dark", ColorScheme.dark, DynamicTypeSize.large, CGFloat(852)),
            ("after-ax5-light", ColorScheme.light, DynamicTypeSize.accessibility5, CGFloat(1450)),
            ("after-ax5-dark", ColorScheme.dark, DynamicTypeSize.accessibility5, CGFloat(1450))
        ] {
            let vm = FeedViewModel(
                client: FakeSportsProvider13013(main: feed, backfill: emptyBackfill, grouped: emptyGrouped),
                telemetry: nil,
                autoRefreshEnabled: false
            )
            await vm.startLoad()
            let img = await render390(view: FeedView(viewModel: vm), scheme: scheme, typeSize: typeSize, height: height)
            let ocr = try ocrLines(img).joined(separator: " ")
            XCTAssertFalse(ocr.contains("Follow"), "Sports tab (\(tag)) must omit team Follow buttons: \(ocr)")
            XCTAssertTrue(ocr.contains("Live Now") && ocr.contains("Celtics"), "Sports tab (\(tag)) must preserve league headings and games: \(ocr)")
            if let outPath, !outPath.isEmpty, let png = img.pngData() {
                try png.write(to: URL(fileURLWithPath: outPath).appendingPathComponent("\(tag)-390.png"))
            }
        }

        // Also render "Before" (showsTeamFollowBar: true) in exact FeedView insetGrouped chrome for Light & Dark 390
        for (tag, scheme, typeSize, height) in [
            ("before-reg-light", ColorScheme.light, DynamicTypeSize.large, CGFloat(852)),
            ("before-reg-dark", ColorScheme.dark, DynamicTypeSize.large, CGFloat(852))
        ] {
            let events = feed.items.compactMap(\.event)
            let nbaEvents = events.filter { $0.sport == "basketball_nba" }
            let nhlEvents = events.filter { $0.sport == "icehockey_nhl" }
            let beforeList = NavigationStack {
                List {
                    Section {
                        SportFilterChips(selectedCategory: .constant("all"), items: feed.items) { _ in }
                            .listRowInsets(EdgeInsets())
                            .listRowBackground(Color.clear)
                            .listRowSeparator(.hidden)
                    }
                    Section {
                        ForEach(nbaEvents) { ev in
                            EventCardView(event: ev, reason: nil, showsTeamFollowBar: true)
                        }
                    } header: {
                        VStack(alignment: .leading, spacing: 6) {
                            HStack(spacing: 6) {
                                Image(systemName: "circle.fill")
                                    .font(.subheadline.weight(.semibold))
                                    .foregroundStyle(.red)
                                Text("Live Now")
                                    .font(.subheadline.weight(.semibold))
                                    .foregroundStyle(.red)
                                    .textCase(nil)
                                Text("3")
                                    .font(.caption2.weight(.medium))
                                    .foregroundStyle(DS.textSecondaryReadable)
                                    .padding(.horizontal, 5)
                                    .padding(.vertical, 1)
                                    .background(Color.secondary.opacity(0.12))
                                    .clipShape(Capsule())
                                Spacer(minLength: 0)
                            }
                            HStack(spacing: 6) {
                                Image(systemName: "basketball.fill")
                                    .font(.footnote.weight(.semibold))
                                    .foregroundStyle(DS.textSecondaryReadable)
                                Text("NBA")
                                    .font(.footnote.weight(.bold))
                                    .foregroundStyle(.primary)
                                    .textCase(nil)
                                Text("2")
                                    .font(.caption2.weight(.medium))
                                    .foregroundStyle(DS.textSecondaryReadable)
                                Spacer(minLength: 0)
                            }
                        }
                    }
                    Section {
                        ForEach(nhlEvents) { ev in
                            EventCardView(event: ev, reason: nil, showsTeamFollowBar: true)
                        }
                    } header: {
                        HStack(spacing: 6) {
                            Image(systemName: "hockey.puck.fill")
                                .font(.footnote.weight(.semibold))
                                .foregroundStyle(DS.textSecondaryReadable)
                            Text("NHL")
                                .font(.footnote.weight(.bold))
                                .foregroundStyle(.primary)
                                .textCase(nil)
                            Text("1")
                                .font(.caption2.weight(.medium))
                                .foregroundStyle(DS.textSecondaryReadable)
                            Spacer(minLength: 0)
                        }
                    }
                }
                .listStyle(.insetGrouped)
                .contentMargins(.top, 4, for: .scrollContent)
                .navigationTitle("Bain Luck")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .principal) {
                        HStack(spacing: 6) {
                            BainLuckMarkView(size: 20)
                            Text("Bain Luck")
                                .font(.headline.weight(.semibold))
                        }
                        .lineLimit(1)
                    }
                }
            }
            let img = await render390(view: beforeList, scheme: scheme, typeSize: typeSize, height: height)
            if let outPath, !outPath.isEmpty, let png = img.pngData() {
                try png.write(to: URL(fileURLWithPath: outPath).appendingPathComponent("\(tag)-390.png"))
            }
        }
    }

    private func render390<V: View>(
        view: V,
        scheme: ColorScheme,
        typeSize: DynamicTypeSize,
        height: CGFloat
    ) async -> UIImage {
        let bg = scheme == .dark ? Color.black : Color(UIColor.systemGroupedBackground)
        let wrapped = view
            .frame(width: 390, height: height, alignment: .topLeading)
            .background(bg)
            .environment(\.horizontalSizeClass, .compact)
            .environment(\.colorScheme, scheme)
            .environment(\.dynamicTypeSize, typeSize)
            .environmentObject(NavigationCoordinator())
            .environmentObject(PinManager(defaults: .standard, allowLegacyGuestPins: false))
            .environmentObject(AuthManager(restoreOnInit: false))

        let host = hostForMeasurement(wrapped, at: typeSize)
        let cat: UIContentSizeCategory = typeSize.isAccessibilitySize
            ? .accessibilityExtraExtraExtraLarge
            : .large
        let traits = UITraitCollection(traitsFrom: [
            UITraitCollection(horizontalSizeClass: .compact),
            UITraitCollection(userInterfaceStyle: scheme == .dark ? .dark : .light),
            UITraitCollection(preferredContentSizeCategory: cat)
        ])
        let container = SportsTraitContainer(child: host, traits: traits)
        let frame = CGRect(x: 0, y: 0, width: 390, height: height)
        container.view.frame = frame

        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: frame)
        window.frame = frame
        window.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        window.rootViewController = container
        window.isHidden = false
        window.makeKeyAndVisible()

        for _ in 0..<5 {
            container.view.setNeedsLayout()
            container.view.layoutIfNeeded()
            try? await Task.sleep(for: .milliseconds(50))
        }

        let renderer = UIGraphicsImageRenderer(size: frame.size)
        return renderer.image { _ in
            container.view.drawHierarchy(in: container.view.bounds, afterScreenUpdates: true)
        }
    }

    private func ocrLines(_ image: UIImage) throws -> [String] {
        guard let cg = image.cgImage else { return [] }
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
        return (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
    }
}
