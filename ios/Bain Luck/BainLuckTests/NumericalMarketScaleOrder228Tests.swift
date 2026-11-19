import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// Direction 228 (#12885): any market whose outcomes are values on a single
/// numerical scale — an "at least N" ladder, disjoint ranges/brackets, a count,
/// a rate, or a margin — lists its rows in ascending numerical order (matching
/// iPhone Margin maps), never by probability. Competitor fields retain highest
/// chance first, and date ladders retain chronological order.
@MainActor
final class NumericalMarketScaleOrder228Tests: XCTestCase {

    private let referenceNow = ISO8601DateFormatter().date(from: "2026-11-17T21:45:00Z")!

    private func makeDecoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    // MARK: - 1. Live Specimen #1: 114367 "What will the Fed rate be at the end of 2026?"

    func testFedRateEnd2026Market114367ListsRowsInRateOrderNotProbability() throws {
        let dict: [String: Any] = [
            "id": 114367,
            "name": "What will the Fed rate be at the end of 2026?",
            "category": "economics",
            "llm_sport_category": "economics",
            "status": "open",
            "source": "polymarket",
            "market_type": "quantity",
            "mutually_exclusive": true,
            "outcomes": [
                ["id": 1633648, "name": "4.25%", "probability": 0.87869822, "rank": 1, "observed_at": "2026-11-17T21:40:00Z"],
                ["id": 1633649, "name": "≥ 4.5%", "probability": 0.05374753, "rank": 2, "observed_at": "2026-11-17T21:40:00Z"],
                ["id": 1633647, "name": "4.0%", "probability": 0.03500986, "rank": 3, "observed_at": "2026-11-17T21:40:00Z"],
                ["id": 1633640, "name": "3.75%", "probability": 0.00591716, "rank": 4, "observed_at": "2026-11-17T21:40:00Z"],
                ["id": 1633641, "name": "≤1.0%", "probability": 0.00493097, "rank": 5, "observed_at": "2026-11-17T21:40:00Z"],
                ["id": 1633637, "name": "3.5%", "probability": 0.00493097, "rank": 6, "observed_at": "2026-11-17T21:40:00Z"],
                ["id": 1633643, "name": "1.25", "probability": 0.00345168, "rank": 7, "observed_at": "2026-11-17T21:40:00Z"],
                ["id": 1633644, "name": "2.0%", "probability": 0.00295858, "rank": 8, "observed_at": "2026-11-17T21:40:00Z"],
            ]
        ]
        let market = try makeDecoder().decode(
            FuturesMarketDetail.self,
            from: try JSONSerialization.data(withJSONObject: dict)
        )
        let page = FuturesAtlasPresentation11666.build(market: market, now: referenceNow)
        XCTAssertEqual(page.body.shape, .numericalScale)
        XCTAssertNil(page.body.subtitleBadge, "Mutually-exclusive rate scale must not print cumulative non-100% badge")
        XCTAssertEqual(
            page.body.allRows.map(\.name),
            ["≤1.0%", "1.25", "2.0%", "3.5%", "3.75%", "4.0%", "4.25%", "≥ 4.5%"]
        )
        XCTAssertEqual(page.body.allRows.filter(\.isLeading).map(\.name), ["4.25%"])

        // First-screen 4-row headline slice keeps the 4 highest-probability outcomes and lists them in rate order.
        let headline = FuturesAtlasPresentation11666.firstScreenHeadlineRows192A(for: page.body)
        XCTAssertEqual(headline.map(\.name), ["3.75%", "4.0%", "4.25%", "≥ 4.5%"])
    }

    // MARK: - 2. Live Specimen #2: 70732744 "How many Fed rate hikes in 2026?"

    func testFedRateHikesMarket70732744ListsCountsAscendingEvenWhenStoredMarketTypeIsField() throws {
        let dict: [String: Any] = [
            "id": 70732744,
            "name": "How many Fed rate hikes in 2026?",
            "category": "economics",
            "llm_sport_category": "economics",
            "status": "open",
            "source": "polymarket",
            "market_type": "field",
            "mutually_exclusive": true,
            "outcomes": [
                ["id": 266765481, "name": "2 (50 bps)", "probability": 0.92953523, "rank": 1, "observed_at": "2026-11-17T21:40:00Z"],
                ["id": 266765482, "name": "3 (75 bps)", "probability": 0.04347826, "rank": 2, "observed_at": "2026-11-17T21:40:00Z"],
                ["id": 266765483, "name": "1 (25 bps)", "probability": 0.02598701, "rank": 3, "observed_at": "2026-11-17T21:40:00Z"],
                ["id": 266765485, "name": "5+ (125+ bps)", "probability": 0.00049975, "rank": 4, "observed_at": "2026-11-17T21:40:00Z"],
                ["id": 266765484, "name": "4 (100 bps)", "probability": 0.00049975, "rank": 5, "observed_at": "2026-11-17T21:40:00Z"],
            ]
        ]
        let market = try makeDecoder().decode(
            FuturesMarketDetail.self,
            from: try JSONSerialization.data(withJSONObject: dict)
        )
        let page = FuturesAtlasPresentation11666.build(market: market, now: referenceNow)
        XCTAssertEqual(page.body.shape, .numericalScale)
        XCTAssertEqual(
            page.body.allRows.map(\.name),
            ["1 (25 bps)", "2 (50 bps)", "3 (75 bps)", "4 (100 bps)", "5+ (125+ bps)"]
        )
        let headline = FuturesAtlasPresentation11666.firstScreenHeadlineRows192A(for: page.body)
        XCTAssertEqual(
            headline.map(\.name),
            ["1 (25 bps)", "2 (50 bps)", "3 (75 bps)", "4 (100 bps)"]
        )

        // Plain bare-integer phrasing ("2, 3, 1, 4") also runs 1, 2, 3, 4.
        let bareSlice = NumericalMarketScaleOrder228.orderedSlice(
            [("2", 0.55), ("3", 0.22), ("1", 0.15), ("4", 0.08)],
            limit: 4,
            label: \.0,
            probability: \.1
        )
        XCTAssertEqual(bareSlice?.map(\.element.0), ["1", "2", "3", "4"])
        XCTAssertEqual(bareSlice?.filter(\.isLeader).map(\.element.0), ["2"])
    }

    // MARK: - 3. Signed Policy Axis, Ranges, Explicit Server Sort Keys, and Negative Controls

    func testSignedPolicyLaddersRangesAndExplicitServerSortKeys() {
        // Live market 108625: "Fed decision in Jan 2027?"
        let signedDecision = [
            ("Fed maintains rate", 0.375),
            ("Hike 25bps", 0.585),
            ("Hike >25bps", 0.02),
            ("Cut 25bps", 0.015),
            ("Cut >25bps", 0.01),
        ]
        let orderedSigned = NumericalMarketScaleOrder228.orderedAll(
            signedDecision,
            label: \.0,
            probability: \.1
        )
        XCTAssertEqual(
            orderedSigned?.map(\.element.0),
            ["Cut >25bps", "Cut 25bps", "Fed maintains rate", "Hike 25bps", "Hike >25bps"]
        )
        XCTAssertEqual(orderedSigned?.filter(\.isLeader).map(\.element.0), ["Hike 25bps"])

        // Disjoint ranges with open lower/upper tails
        let ranges = [
            ("$150M - $200M", 0.42),
            ("$200M+", 0.24),
            ("$100M - $150M", 0.21),
            ("< $100M", 0.13),
        ]
        let orderedRanges = NumericalMarketScaleOrder228.orderedAll(ranges, label: \.0, probability: \.1)
        XCTAssertEqual(
            orderedRanges?.map(\.element.0),
            ["< $100M", "$100M - $150M", "$150M - $200M", "$200M+"]
        )

        // Explicit server `sort_key` (Builder B #12885 contract) takes priority whenever served
        let customServerOrder = NumericalMarketScaleOrder228.orderedAll(
            [("Tier B", 0.60, 20.0), ("Tier A", 0.25, 10.0), ("Tier C", 0.15, 30.0)],
            label: \.0,
            probability: \.1,
            explicitSortKey: { $0.2 }
        )
        XCTAssertEqual(customServerOrder?.map(\.element.0), ["Tier A", "Tier B", "Tier C"])
    }

    func testCompetitorFieldsAndCalendarDatesNeverSortNumerically() {
        // Teams with numbers in their names
        XCTAssertFalse(
            NumericalMarketScaleOrder228.isNumericalScale(
                labels: ["Philadelphia 76ers", "San Francisco 49ers", "Boston Celtics"]
            )
        )
        XCTAssertFalse(
            NumericalMarketScaleOrder228.isNumericalScale(
                labels: ["76ers", "49ers", "Celtics"]
            )
        )
        // Films with numbers in their titles
        XCTAssertFalse(
            NumericalMarketScaleOrder228.isNumericalScale(
                labels: ["Anora", "28 Years Later", "1917", "Conclave"]
            )
        )
        // Calendar dates & FOMC meetings
        XCTAssertFalse(
            NumericalMarketScaleOrder228.isNumericalScale(
                labels: ["October 27", "October 12", "October 14", "No release by October 31"],
                orderHint: "chronological"
            )
        )
        XCTAssertFalse(
            NumericalMarketScaleOrder228.isNumericalScale(
                labels: ["April 2027 Meeting", "June 2027 Meeting", "March 2027 Meeting"]
            )
        )
        // Binary Yes/No
        XCTAssertFalse(
            NumericalMarketScaleOrder228.isNumericalScale(labels: ["Yes", "No"])
        )
    }

    // MARK: - 4. DistributionCard, RoundupCard, and Economics FOMC / CPI Surfaces

    func testDistributionRoundupAndEconomicsSurfacesOrderNumericalScalesAscending() throws {
        // DistributionBoardOrder
        let distOutcomes = [
            FeedDiscoverDistributionOutcome(label: "4.25%", probability: 0.88, movement: nil),
            FeedDiscoverDistributionOutcome(label: "≥ 4.5%", probability: 0.05, movement: nil),
            FeedDiscoverDistributionOutcome(label: "4.0%", probability: 0.04, movement: nil),
            FeedDiscoverDistributionOutcome(label: "3.75%", probability: 0.01, movement: nil),
        ]
        XCTAssertTrue(DistributionBoardOrder.isNumerical(distOutcomes, order: "probability"))
        let listed = DistributionBoardOrder.listedRows(distOutcomes, order: "probability")
        XCTAssertEqual(listed.map(\.outcome.label), ["3.75%", "4.0%", "4.25%", "≥ 4.5%"])
        XCTAssertEqual(listed.filter(\.isLeader).map(\.outcome.label), ["4.25%"])

        // DiscoverRoundupCardModel
        let roundup = FeedRoundupContract(
            kicker: "FED & U.S. MACRO",
            subtitle: "End-of-2026 policy rate",
            completeGroup: true,
            footer: "All 4 outcomes",
            order: "probability",
            rows: [
                FeedRoundupRow(marketId: 114367, outcomeId: 1, label: "4.25%", probability: 0.88),
                FeedRoundupRow(marketId: 114367, outcomeId: 2, label: "≥ 4.5%", probability: 0.05),
                FeedRoundupRow(marketId: 114367, outcomeId: 3, label: "4.0%", probability: 0.04),
                FeedRoundupRow(marketId: 114367, outcomeId: 4, label: "3.75%", probability: 0.01),
            ]
        )
        let builtRoundup = try XCTUnwrap(
            DiscoverRoundupCardModel.build(
                title: "What will the Fed rate be at the end of 2026?",
                contract: roundup,
                now: referenceNow
            )
        )
        XCTAssertEqual(builtRoundup.rows.map(\.label), ["3.75%", "4.0%", "4.25%", "≥ 4.5%"])

        // Economics FOMC & CPI brackets
        let fomcJSON = """
        [[58.0, "4.00-4.25%"], [24.0, "4.25-4.50%"], [14.0, "3.75-4.00%"], [4.0, "3.50-3.75%"]]
        """
        let fomcDist = try makeDecoder().decode([[WeatherAnyCodable]].self, from: Data(fomcJSON.utf8))
        let orderedFOMC = NumericalMarketScaleOrder228.orderedFOMCDistribution(fomcDist, limit: 5)
        XCTAssertEqual(
            orderedFOMC.map(\.rate),
            ["3.50-3.75%", "3.75-4.00%", "4.00-4.25%", "4.25-4.50%"]
        )

        let cpiJSON = """
        [[46.0, "2.5% to 2.7%"], [28.0, "2.2% to 2.4%"], [16.0, "2.8% or above"], [10.0, "2.1% or below"]]
        """
        let cpiBrackets = try makeDecoder().decode([[WeatherAnyCodable]].self, from: Data(cpiJSON.utf8))
        let orderedCPI = NumericalMarketScaleOrder228.orderedCPIBrackets(cpiBrackets, fallbackPeakIndex: 0)
        XCTAssertEqual(
            orderedCPI.brackets.compactMap { $0[1].stringValue },
            ["2.1% or below", "2.2% to 2.4%", "2.5% to 2.7%", "2.8% or above"]
        )
        XCTAssertEqual(orderedCPI.peakIndex, 2)
    }

    // MARK: - 5. Optional 390 px Render Export (No-op unless BUILDER_C_RENDER_DIR is set)

    private func renderSnapshot<V: View>(_ view: V, width: CGFloat = 390, to url: URL) throws {
        let host = hostForMeasurement(view.environment(\.colorScheme, .light), at: .large)
        host.overrideUserInterfaceStyle = .light
        let fitting = host.sizeThatFits(in: CGSize(width: width, height: 6000))
        let size = CGSize(width: width, height: ceil(max(200, fitting.height)))
        host.view.frame = CGRect(origin: .zero, size: size)
        let window: UIWindow
        if let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first {
            window = UIWindow(windowScene: scene)
        } else {
            window = UIWindow(frame: host.view.frame)
        }
        window.frame = host.view.frame
        window.overrideUserInterfaceStyle = .light
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }
        let until = Date().addingTimeInterval(0.35)
        repeat {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.015))
        } while Date() < until
        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 3.0
        let image = UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { _ in
            _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
        if let png = image.pngData() {
            try png.write(to: url)
        }
    }

    func testExport390pxRendersWhenRequested() throws {
        guard let rawDir = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_DIR"], !rawDir.isEmpty else {
            return
        }
        let dirURL = URL(fileURLWithPath: rawDir, isDirectory: true)
        try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)

        // Build live-data Fed Rate (114367) and Fed Rate Hikes (70732744) specimens
        let fedRateFeedDict: [String: Any] = [
            "id": 114367,
            "name": "What will the Fed rate be at the end of 2026?",
            "llm_sport_category": "economics",
            "source": "polymarket",
            "status": "open",
            "resolution_date": "2026-12-31T00:00:00Z",
            "outcome_count": 15,
            "market_type": "quantity",
            "mutually_exclusive": true,
            "top_outcomes": [
                ["id": 1633648, "name": "4.25%", "probability": 0.87869822, "rank": 1],
                ["id": 1633649, "name": "≥ 4.5%", "probability": 0.05374753, "rank": 2],
                ["id": 1633647, "name": "4.0%", "probability": 0.03500986, "rank": 3],
                ["id": 1633640, "name": "3.75%", "probability": 0.00591716, "rank": 4],
            ]
        ]
        let hikesFeedDict: [String: Any] = [
            "id": 70732744,
            "name": "How many Fed rate hikes in 2026?",
            "llm_sport_category": "economics",
            "source": "polymarket",
            "status": "open",
            "resolution_date": "2026-12-31T00:00:00Z",
            "outcome_count": 5,
            "market_type": "field",
            "mutually_exclusive": true,
            "top_outcomes": [
                ["id": 266765481, "name": "2 (50 bps)", "probability": 0.92953523, "rank": 1],
                ["id": 266765482, "name": "3 (75 bps)", "probability": 0.04347826, "rank": 2],
                ["id": 266765483, "name": "1 (25 bps)", "probability": 0.02598701, "rank": 3],
                ["id": 266765484, "name": "4 (100 bps)", "probability": 0.00049975, "rank": 4],
            ]
        ]
        let fedRateFeed = try makeDecoder().decode(
            FeedFuturesData.self,
            from: try JSONSerialization.data(withJSONObject: fedRateFeedDict)
        )
        let hikesFeed = try makeDecoder().decode(
            FeedFuturesData.self,
            from: try JSONSerialization.data(withJSONObject: hikesFeedDict)
        )

        let fedDetailDict: [String: Any] = [
            "id": 114367,
            "name": "What will the Fed rate be at the end of 2026?",
            "category": "economics",
            "llm_sport_category": "economics",
            "status": "open",
            "source": "polymarket",
            "market_type": "quantity",
            "mutually_exclusive": true,
            "outcomes": [
                ["id": 1633648, "name": "4.25%", "probability": 0.87869822, "rank": 1, "observed_at": "2026-11-17T21:40:00Z"],
                ["id": 1633649, "name": "≥ 4.5%", "probability": 0.05374753, "rank": 2, "observed_at": "2026-11-17T21:40:00Z"],
                ["id": 1633647, "name": "4.0%", "probability": 0.03500986, "rank": 3, "observed_at": "2026-11-17T21:40:00Z"],
                ["id": 1633640, "name": "3.75%", "probability": 0.00591716, "rank": 4, "observed_at": "2026-11-17T21:40:00Z"],
                ["id": 1633641, "name": "≤1.0%", "probability": 0.00493097, "rank": 5, "observed_at": "2026-11-17T21:40:00Z"],
                ["id": 1633637, "name": "3.5%", "probability": 0.00493097, "rank": 6, "observed_at": "2026-11-17T21:40:00Z"],
            ]
        ]
        let fedDetail = try makeDecoder().decode(
            FuturesMarketDetail.self,
            from: try JSONSerialization.data(withJSONObject: fedDetailDict)
        )
        let fedPage = FuturesAtlasPresentation11666.build(market: fedDetail, now: referenceNow)
        let fedHeadlineRows = FuturesAtlasPresentation11666.firstScreenHeadlineRows192A(for: fedPage.body)

        let beforeRowsFed: [(String, Int, Bool)] = [
            ("4.25%", 88, true), ("≥ 4.5%", 5, false), ("4.0%", 4, false), ("3.75%", 1, false)
        ]
        let beforeRowsHikes: [(String, Int, Bool)] = [
            ("2 (50 bps)", 93, true), ("3 (75 bps)", 4, false), ("1 (25 bps)", 3, false), ("4 (100 bps)", 1, false)
        ]

        @ViewBuilder
        func legacyBeforeCard(title: String, rows: [(String, Int, Bool)], countText: String) -> some View {
            VStack(alignment: .leading, spacing: 0) {
                HStack {
                    Text("ECONOMICS")
                        .font(.system(size: 10, weight: .heavy))
                        .tracking(0.5)
                        .foregroundStyle(.secondary)
                    Spacer()
                    Text("Resolves Dec 31")
                        .font(.system(size: 11))
                        .foregroundStyle(.secondary)
                }
                .padding(.bottom, 3)

                Text(title)
                    .font(.system(size: 15, weight: .semibold))
                    .padding(.bottom, 12)

                ForEach(Array(rows.enumerated()), id: \.offset) { idx, row in
                    Divider()
                    HStack(spacing: 10) {
                        Text("#\(idx + 1)")
                            .font(.system(size: 11, weight: .semibold, design: .monospaced))
                            .foregroundStyle(DS.textMuted)
                            .frame(width: 20, alignment: .leading)
                        Text(row.0)
                            .font(.system(size: 13, weight: row.2 ? .semibold : .medium))
                            .foregroundStyle(row.2 ? DS.textPrimary : DS.textSecondary)
                        Spacer()
                        RoundedRectangle(cornerRadius: 999)
                            .fill(DS.emerald.opacity(row.1 >= 40 ? 1.0 : 0.55))
                            .frame(width: max(4, CGFloat(row.1)), height: 7)
                            .frame(width: 100, alignment: .leading)
                            .background(RoundedRectangle(cornerRadius: 999).fill(DS.trackBg))
                        Text("\(row.1)%")
                            .font(.system(size: 14, weight: .bold, design: .monospaced))
                            .frame(width: 38, alignment: .trailing)
                    }
                    .padding(.vertical, 8)
                }
                Divider().padding(.top, 8)
                HStack {
                    Text("Sorted by probability (old)")
                        .font(.system(size: 11))
                        .foregroundStyle(DS.danger)
                    Spacer()
                    Text(countText)
                        .font(.system(size: 11))
                        .foregroundStyle(DS.textMuted)
                }
                .padding(.top, 10)
            }
            .padding(16)
            .background(Color.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .overlay(RoundedRectangle(cornerRadius: 10).stroke(Color.barTrack.opacity(0.55), lineWidth: 0.5))
        }

        let sheet228 = VStack(alignment: .leading, spacing: 14) {
            VStack(alignment: .leading, spacing: 4) {
                Text("DIRECTION 228 (#12885) · IPHONE BEFORE & AFTER (390 PX)")
                    .font(.caption2.weight(.heavy))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                Text("Ladder, range, rate & count markets list rows in numerical order")
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Text("BEFORE — Sorted by probability descending (#114367 & #70732744)")
                .font(.caption.weight(.bold))
                .foregroundStyle(DS.danger)
                .fixedSize(horizontal: false, vertical: true)
            legacyBeforeCard(
                title: "What will the Fed rate be at the end of 2026?",
                rows: beforeRowsFed,
                countText: "15 outcomes"
            )
            legacyBeforeCard(
                title: "How many Fed rate hikes in 2026?",
                rows: beforeRowsHikes,
                countText: "5 outcomes"
            )

            Text("AFTER — Ascending numerical order on Discover cards & Futures page")
                .font(.caption.weight(.bold))
                .foregroundStyle(DS.emerald)
                .fixedSize(horizontal: false, vertical: true)
            ComparisonCardView(data: fedRateFeed, navigationPath: .constant(NavigationPath()))
            ComparisonCardView(data: hikesFeed, navigationPath: .constant(NavigationPath()))
            FuturesAtlasHeadlineCard192A(
                market: fedDetail,
                header: fedPage.header,
                headlineRows: fedHeadlineRows,
                allFieldLabel: FuturesAtlasPresentation11666.allFieldLinkLabel192A(market: fedDetail, body: fedPage.body),
                isNumericallyOrdered: true,
                onOpenDetails: {},
                onOpenFullField: {}
            )
        }
        .padding(16)
        .frame(width: 390)
        .background(Color(uiColor: .systemGroupedBackground))

        try renderSnapshot(
            sheet228,
            width: 390,
            to: dirURL.appendingPathComponent("12885-direction-228-before-after-390.png")
        )

        // Optional #12889 diagnostic render for Trail Blazers at Timberwolves (15350164)
        let evDetailURL = URL(fileURLWithPath: "/tmp/ev15350164_detail.json")
        let evHistoryURL = URL(fileURLWithPath: "/tmp/ev15350164_history.json")
        if FileManager.default.fileExists(atPath: evDetailURL.path),
           FileManager.default.fileExists(atPath: evHistoryURL.path) {
            let detail = try makeDecoder().decode(EventDetail.self, from: Data(contentsOf: evDetailURL))
            let history = try makeDecoder().decode(EventHistoryResponse.self, from: Data(contentsOf: evHistoryURL))
            let chartNow = Date()
            if let projInput = ProjectedFinalPointsMount.input(
                sportKey: detail.sport,
                eventStatus: detail.status,
                history: history,
                finalHome: detail.homeScore,
                finalAway: detail.awayScore,
                asOf: chartNow
            ) {
                let colors = TeamTextContrast.cardColors(
                    awayHex: detail.awayTeamData?.primaryColor,
                    homeHex: detail.homeTeamData?.primaryColor,
                    awaySecondaryHex: detail.awayTeamData?.secondaryColor,
                    checkHueFamily: true
                )
                let chartCard = VStack(alignment: .leading, spacing: 10) {
                    Text("iPhone Master (#12639 live) · Event 15350164 (Trail Blazers at Timberwolves)")
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                    ProjectedFinalPointsChartView(
                        input: projInput,
                        homeTeam: detail.homeTeam,
                        awayTeam: detail.awayTeam,
                        homeColor: colors.home,
                        awayColor: colors.away,
                        periodMarkers: history.periodMarkers,
                        sportKey: detail.sport
                    )
                    .padding(16)
                    .background(Color.cardBackground)
                    .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(DS.border, lineWidth: 0.75))
                }
                .padding(16)
                .frame(width: 390)
                .background(Color(uiColor: .systemGroupedBackground))

                try renderSnapshot(
                    chartCard,
                    width: 390,
                    to: dirURL.appendingPathComponent("12889-ev15350164-trail-blazers-at-timberwolves-iphone-390.png")
                )
            }
        }
    }
}
