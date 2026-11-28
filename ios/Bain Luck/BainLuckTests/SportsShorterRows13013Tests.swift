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

        // Verify iPad regular width (`834 pt`) Sports tab also omits Follow buttons while preserving headings & cards.
        let iPadVM = FeedViewModel(
            client: FakeSportsProvider13013(main: feed, backfill: emptyBackfill, grouped: emptyGrouped),
            telemetry: nil,
            autoRefreshEnabled: false
        )
        await iPadVM.startLoad()
        let iPadImg = await renderViewport(view: FeedView(viewModel: iPadVM), width: 834, height: 1194, scheme: .light, typeSize: .large)
        let iPadOCR = try ocrLines(iPadImg).joined(separator: " ")
        XCTAssertFalse(iPadOCR.contains("Follow"), "iPad 834pt Sports tab must omit team Follow buttons: \(iPadOCR)")
        XCTAssertTrue(iPadOCR.contains("Live Now") && iPadOCR.contains("Celtics"), "iPad 834pt Sports tab must preserve league headings and games: \(iPadOCR)")
    }

    private final class StaticEventClient13013: EventDetailProviding, @unchecked Sendable {
        struct Missing: Error {}
        let event: EventDetail
        init(event: EventDetail) { self.event = event }
        func fetchEvent(id: Int) async throws -> EventDetail { event }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse { throw Missing() }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Missing() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Missing() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Missing() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Missing() }
    }

    private final class StaticStreamHandle13013: LiveStreamHandle, @unchecked Sendable {
        var isClosed = false
        var isConnecting = false
        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) {}
        func close() {}
    }

    func testMondayWalkExportLiveSportsAndFollowPathIfRequested() async throws {
        let env = ProcessInfo.processInfo.environment
        guard let outPath = env["TEST_RUNNER_LIVE_13013_DIR"] ?? env["LIVE_13013_DIR"], !outPath.isEmpty,
              let feedPath = env["TEST_RUNNER_LIVE_SPORTS_JSON"] ?? env["LIVE_SPORTS_JSON"],
              let eventPath = env["TEST_RUNNER_LIVE_EVENT_JSON"] ?? env["LIVE_EVENT_JSON"],
              let teamPath = env["TEST_RUNNER_LIVE_TEAM_JSON"] ?? env["LIVE_TEAM_JSON"] else {
            return
        }
        try FileManager.default.createDirectory(atPath: outPath, withIntermediateDirectories: true)

        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        let feed = try dec.decode(FeedResponse.self, from: Data(contentsOf: URL(fileURLWithPath: feedPath)))
        let eventDetail = try dec.decode(EventDetail.self, from: Data(contentsOf: URL(fileURLWithPath: eventPath)))
        let teamPage = try dec.decode(TeamPageResponse.self, from: Data(contentsOf: URL(fileURLWithPath: teamPath)))
        let emptyBackfill = try dec.decode(FeedResponse.self, from: Data(#"{"items":[],"total":0,"limit":200,"offset":0,"has_more":false}"#.utf8))
        let emptyGrouped = try dec.decode(GroupedFeedResponse.self, from: Data(#"{"feed":[],"total":0,"limit":20,"offset":0}"#.utf8))

        let vm = FeedViewModel(
            client: FakeSportsProvider13013(main: feed, backfill: emptyBackfill, grouped: emptyGrouped),
            telemetry: nil,
            autoRefreshEnabled: false
        )
        await vm.startLoad()
        let liveGroups = SportsLeagueBands401B.grouped(vm.filteredLiveNow(for: "all"), band: .live)
        let upcomingGroups = SportsLeagueBands401B.grouped(vm.filteredUpcoming(for: "all"), band: .upcoming)

        @ViewBuilder
        func bandAndLeagueHeader(bandTitle: String?, bandColor: Color, bandIcon: String, bandCount: Int, group: SportsLeagueGroup401B) -> some View {
            VStack(alignment: .leading, spacing: 6) {
                if let bandTitle {
                    HStack(spacing: 6) {
                        Image(systemName: bandIcon).font(.subheadline.weight(.semibold)).foregroundStyle(bandColor)
                        Text(bandTitle).font(.subheadline.weight(.semibold)).foregroundStyle(bandColor).textCase(nil)
                        Text("\(bandCount)").font(.caption2.weight(.medium)).foregroundStyle(DS.textSecondaryReadable)
                            .padding(.horizontal, 5).padding(.vertical, 1).background(Color.secondary.opacity(0.12)).clipShape(Capsule())
                        Spacer(minLength: 0)
                    }
                }
                HStack(spacing: 6) {
                    Image(systemName: group.systemImage).font(.footnote.weight(.semibold)).foregroundStyle(DS.textSecondaryReadable)
                    Text(group.title).font(.footnote.weight(.bold)).foregroundStyle(.primary).textCase(nil)
                    Text("\(group.items.count)").font(.caption2.weight(.medium)).foregroundStyle(DS.textSecondaryReadable)
                    Spacer(minLength: 0)
                }
            }
        }

        func beforeSportsList(isIPad: Bool) -> some View {
            NavigationStack {
                List {
                    Section {
                        SportFilterChips(selectedCategory: .constant("all"), items: vm.items) { _ in }
                            .listRowInsets(EdgeInsets())
                            .listRowBackground(Color.clear)
                            .listRowSeparator(.hidden)
                    }
                    if isIPad {
                        let blocks = SportsRegularGridLayout13869.blocks(from: liveGroups)
                        ForEach(Array(blocks.enumerated()), id: \.element.id) { index, block in
                            switch block {
                            case .singletons(_, let singletonGroups):
                                let cols = DiscoverMasonry.columns(cardCount: singletonGroups.count, columnCount: 2)
                                Section {
                                    HStack(alignment: .top, spacing: DiscoverMasonry.listCardSpacing) {
                                        ForEach(Array(cols.enumerated()), id: \.offset) { _, indices in
                                            VStack(alignment: .leading, spacing: DiscoverMasonry.listCardSpacing) {
                                                ForEach(indices, id: \.self) { i in
                                                    let group = singletonGroups[i]
                                                    if let ev = group.items.first?.event {
                                                        VStack(alignment: .leading, spacing: 6) {
                                                            bandAndLeagueHeader(bandTitle: nil, bandColor: .red, bandIcon: "circle.fill", bandCount: 0, group: group)
                                                                .padding(.horizontal, 4)
                                                            EventCardView(event: ev, reason: nil, showsTeamFollowBar: true)
                                                                .padding(12)
                                                                .background(Color(uiColor: .secondarySystemGroupedBackground))
                                                                .clipShape(RoundedRectangle(cornerRadius: 12))
                                                        }
                                                    }
                                                }
                                            }
                                            .frame(maxWidth: .infinity, alignment: .topLeading)
                                        }
                                    }
                                    .listRowInsets(EdgeInsets(top: 6, leading: 4, bottom: 10, trailing: 4))
                                    .listRowBackground(Color.clear)
                                    .listRowSeparator(.hidden)
                                } header: {
                                    if index == 0, let firstSingleton = singletonGroups.first {
                                        bandAndLeagueHeader(bandTitle: "Live Now", bandColor: .red, bandIcon: "circle.fill", bandCount: liveGroups.flatMap(\.items).count, group: firstSingleton)
                                    }
                                }
                            case .league(let group):
                                let events = group.items.compactMap(\.event)
                                let cols = DiscoverMasonry.columns(cardCount: events.count, columnCount: 2)
                                Section {
                                    HStack(alignment: .top, spacing: DiscoverMasonry.listCardSpacing) {
                                        ForEach(Array(cols.enumerated()), id: \.offset) { _, indices in
                                            VStack(spacing: DiscoverMasonry.listCardSpacing) {
                                                ForEach(indices, id: \.self) { i in
                                                    EventCardView(event: events[i], reason: nil, showsTeamFollowBar: true)
                                                        .padding(12)
                                                        .background(Color(uiColor: .secondarySystemGroupedBackground))
                                                        .clipShape(RoundedRectangle(cornerRadius: 12))
                                                }
                                            }
                                            .frame(maxWidth: .infinity)
                                        }
                                    }
                                    .listRowInsets(EdgeInsets(top: 6, leading: 4, bottom: 10, trailing: 4))
                                    .listRowBackground(Color.clear)
                                    .listRowSeparator(.hidden)
                                } header: {
                                    bandAndLeagueHeader(bandTitle: index == 0 ? "Live Now" : nil, bandColor: .red, bandIcon: "circle.fill", bandCount: liveGroups.flatMap(\.items).count, group: group)
                                }
                            }
                        }
                    } else {
                        ForEach(Array(liveGroups.enumerated()), id: \.element.id) { index, group in
                            Section {
                                ForEach(group.items.compactMap(\.event)) { ev in
                                    EventCardView(event: ev, reason: nil, showsTeamFollowBar: true)
                                }
                            } header: {
                                bandAndLeagueHeader(bandTitle: index == 0 ? "Live Now" : nil, bandColor: .red, bandIcon: "circle.fill", bandCount: liveGroups.flatMap(\.items).count, group: group)
                            }
                        }
                        ForEach(Array(upcomingGroups.prefix(2).enumerated()), id: \.element.id) { index, group in
                            Section {
                                ForEach(group.items.compactMap(\.event)) { ev in
                                    EventCardView(event: ev, reason: nil, showsTeamFollowBar: true)
                                }
                            } header: {
                                bandAndLeagueHeader(bandTitle: index == 0 ? "Upcoming" : nil, bandColor: .blue, bandIcon: "calendar", bandCount: upcomingGroups.flatMap(\.items).count, group: group)
                            }
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
                            Text("Bain Luck").font(.headline.weight(.semibold))
                        }
                    }
                }
            }
        }

        for (scheme, sName) in [(ColorScheme.light, "light"), (ColorScheme.dark, "dark")] {
            for (width, height) in [(CGFloat(390), CGFloat(852)), (CGFloat(834), CGFloat(1194))] {
                let bImg = await renderViewport(view: beforeSportsList(isIPad: width >= 700), width: width, height: height, scheme: scheme, typeSize: .large)
                let aImg = await renderViewport(view: FeedView(viewModel: vm), width: width, height: height, scheme: scheme, typeSize: .large)
                try XCTUnwrap(bImg.pngData()).write(to: URL(fileURLWithPath: "\(outPath)/live-before-\(Int(width))-\(sName).png"))
                try XCTUnwrap(aImg.pngData()).write(to: URL(fileURLWithPath: "\(outPath)/live-after-\(Int(width))-\(sName).png"))
            }
        }

        // Follow path panels
        let eventVM = EventDetailViewModel(
            eventId: eventDetail.id,
            client: StaticEventClient13013(event: eventDetail),
            makeStreamHandle: { _ in StaticStreamHandle13013() }
        )
        await eventVM.load()
        let gamePageImg = await renderViewport(
            view: NavigationStack { EventDetailView(eventId: eventDetail.id, viewModel: eventVM) },
            width: 390,
            height: 760,
            scheme: .light,
            typeSize: .large
        )
        try XCTUnwrap(gamePageImg.pngData()).write(to: URL(fileURLWithPath: "\(outPath)/live-game-page-390-light.png"))

        let teamPageImg = await renderViewport(
            view: NavigationStack { TeamDetailView(slug: teamPage.team.slug, loadedPageForTest: teamPage) },
            width: 390,
            height: 620,
            scheme: .light,
            typeSize: .large
        )
        try XCTUnwrap(teamPageImg.pngData()).write(to: URL(fileURLWithPath: "\(outPath)/live-team-page-390-light.png"))

        if let firstFeedEvent = feed.items.compactMap(\.event).first(where: { $0.id == eventDetail.id }) ?? feed.items.compactMap(\.event).first {
            let discImg = await renderViewport(
                view: ScrollView {
                    NativeEventDiscoverCard(
                        event: firstFeedEvent,
                        feedContext: nil,
                        expandedContext: nil,
                        navigationPath: .constant(NavigationPath())
                    )
                    .padding(16)
                },
                width: 390,
                height: 520,
                scheme: .light,
                typeSize: .large
            )
            try XCTUnwrap(discImg.pngData()).write(to: URL(fileURLWithPath: "\(outPath)/live-discover-follow-390-light.png"))
        }
    }

    private func render390<V: View>(
        view: V,
        scheme: ColorScheme,
        typeSize: DynamicTypeSize,
        height: CGFloat
    ) async -> UIImage {
        await renderViewport(view: view, width: 390, height: height, scheme: scheme, typeSize: typeSize)
    }

    private func renderViewport<V: View>(
        view: V,
        width: CGFloat,
        height: CGFloat,
        scheme: ColorScheme,
        typeSize: DynamicTypeSize
    ) async -> UIImage {
        let isRegular = width >= 700
        let bg = scheme == .dark ? Color.black : Color(UIColor.systemGroupedBackground)
        let wrapped = view
            .frame(width: width, height: height, alignment: .topLeading)
            .background(bg)
            .environment(\.horizontalSizeClass, isRegular ? .regular : .compact)
            .environment(\.colorScheme, scheme)
            .environment(\.dynamicTypeSize, typeSize)
            .environmentObject(NavigationCoordinator())
            .environmentObject(PinManager(defaults: .standard, allowLegacyGuestPins: false))
            .environmentObject(AuthManager(restoreOnInit: false))

        let host = hostForMeasurement(wrapped, at: typeSize)
        host.safeAreaRegions = []
        let cat: UIContentSizeCategory = typeSize.isAccessibilitySize
            ? .accessibilityExtraExtraExtraLarge
            : .large
        let traits = UITraitCollection(traitsFrom: [
            UITraitCollection(horizontalSizeClass: isRegular ? .regular : .compact),
            UITraitCollection(userInterfaceStyle: scheme == .dark ? .dark : .light),
            UITraitCollection(preferredContentSizeCategory: cat)
        ])
        let container = SportsTraitContainer(child: host, traits: traits)
        let frame = CGRect(x: 0, y: 0, width: width, height: height)
        container.view.frame = frame

        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: frame)
        window.frame = frame
        window.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        window.rootViewController = container
        window.isHidden = false
        window.makeKeyAndVisible()
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        for _ in 0..<6 {
            container.view.setNeedsLayout()
            container.view.layoutIfNeeded()
            try? await Task.sleep(for: .milliseconds(50))
        }

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 2.0
        fmt.opaque = true
        return UIGraphicsImageRenderer(size: frame.size, format: fmt).image { _ in
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
