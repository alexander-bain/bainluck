import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// `#13552` — When `/api/me/team-futures` fails or times out:
/// 1. `MyStuffViewModel` records `teamFuturesFailed = true` (leaving `error == nil` so
///    any loaded games remain visible) and clears it when `retryTeamFutures()` succeeds.
/// 2. `MyStuffLandingViewModel295A` keeps `teamFuturesFailed = true` even when local
///    `followedSubjects` and `signedInItems` are empty (server-only follows), never
///    pretending the reader follows nothing.
/// 3. Both `MyStuffLandingView295A` and fallback `MyStuffView(viewModelForTest:)` tell
///    the reader plainly that it failed and offer a `Try again` control.
@MainActor
final class MyStuffTeamFuturesFailure13552Tests: XCTestCase {

    private nonisolated final class AsyncGate: @unchecked Sendable {
        private let lock = NSLock()
        private var opened = false
        private var conts: [CheckedContinuation<Void, Never>] = []

        func wait() async {
            await withCheckedContinuation { (cont: CheckedContinuation<Void, Never>) in
                let shouldResume: Bool = lock.withLock {
                    if opened { return true }
                    conts.append(cont)
                    return false
                }
                if shouldResume { cont.resume() }
            }
        }
    }

    private nonisolated final class ScriptedClient: MyStuffFeedProviding, @unchecked Sendable {
        private let lock = NSLock()
        private let feedResult: Result<FeedResponse, Error>
        private var futuresReplies: [Result<TeamFuturesResponse, Error>]
        private var futuresIndex = 0
        private var _futuresCalls = 0
        let futuresGate: AsyncGate?

        init(
            feedResult: Result<FeedResponse, Error>,
            futuresReplies: [Result<TeamFuturesResponse, Error>],
            futuresGate: AsyncGate? = nil
        ) {
            self.feedResult = feedResult
            self.futuresReplies = futuresReplies
            self.futuresGate = futuresGate
        }

        var futuresCalls: Int { lock.withLock { _futuresCalls } }

        nonisolated func fetchMyTeamsFeed() async throws -> FeedResponse {
            try feedResult.get()
        }

        nonisolated func fetchMyTeamFuturesSection(limit: Int) async throws -> TeamFuturesResponse {
            let reply: Result<TeamFuturesResponse, Error> = lock.withLock {
                _futuresCalls += 1
                let idx = min(futuresIndex, max(0, futuresReplies.count - 1))
                futuresIndex += 1
                return futuresReplies[idx]
            }
            if let futuresGate { await futuresGate.wait() }
            return try reply.get()
        }

        nonisolated func currentMyStuffPrincipal() async -> String {
            "user:test-13552"
        }
    }

    private struct FakeHTTPError: Error {}

    private static func decoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    private static func decodeFeed(withGame: Bool) throws -> FeedResponse {
        let json: String
        if withGame {
            json = """
            {
              "items": [
                {
                  "type": "event",
                  "score": 90.0,
                  "data": {
                    "id": 1355201,
                    "sport": "basketball_nba",
                    "sport_name": "NBA",
                    "away_team": "Miami Heat",
                    "home_team": "Boston Celtics",
                    "commence_time": "2026-11-26T00:30:00Z",
                    "status": "scheduled",
                    "current_odds": {
                      "away_probability": 0.36,
                      "home_probability": 0.64,
                      "away_rendered_percent": 36,
                      "home_rendered_percent": 64
                    }
                  }
                }
              ],
              "total": 1,
              "limit": 100,
              "offset": 0,
              "has_more": false
            }
            """
        } else {
            json = #"{"items":[],"total":0,"limit":100,"offset":0,"has_more":false}"#
        }
        return try decoder().decode(FeedResponse.self, from: Data(json.utf8))
    }

    private static func decodeFutures() throws -> TeamFuturesResponse {
        let json = """
        {
          "items": [
            {
              "outcome_id": 8801,
              "outcome_name": "Boston Celtics",
              "market_id": 4401,
              "market_name": "2027 NBA Championship",
              "probability": 0.24,
              "matched_team": { "id": 2, "name": "Boston Celtics" }
            }
          ],
          "team_ids": [2],
          "total_count": 1
        }
        """
        return try decoder().decode(TeamFuturesResponse.self, from: Data(json.utf8))
    }

    private func settleOptional(maxWaitSeconds: TimeInterval = 1.5, until predicate: () -> Bool) async {
        let deadline = Date().addingTimeInterval(maxWaitSeconds)
        while Date() < deadline && !predicate() {
            await Task.yield()
            try? await Task.sleep(nanoseconds: 15_000_000)
        }
    }

    // MARK: - ViewModel failure & timeout tests

    func testFuturesErrorSetsTeamFuturesFailedAndRetryRecovers() async throws {
        let futures = try Self.decodeFutures()
        let client = ScriptedClient(
            feedResult: .success(try Self.decodeFeed(withGame: false)),
            futuresReplies: [.failure(FakeHTTPError()), .success(futures)]
        )
        let vm = MyStuffViewModel(
            client: client,
            telemetry: nil,
            autoRefreshEnabled: false,
            optionalDeadline: 1.0,
            requiredAttempts: 1,
            retryBackoff: 0
        )

        vm.viewDidStart()
        await vm.startLoad()
        await settleOptional { !vm.teamFuturesLoading && vm.teamFuturesFailed }

        XCTAssertNil(vm.error, "Required feed succeeded — error stays nil")
        XCTAssertTrue(vm.items.isEmpty)
        XCTAssertNil(vm.teamFutures)
        XCTAssertTrue(vm.teamFuturesFailed, "Failure on /api/me/team-futures must flag teamFuturesFailed")
        XCTAssertFalse(vm.teamFuturesLoading)
        XCTAssertEqual(client.futuresCalls, 1)

        await vm.retryTeamFutures()

        XCTAssertFalse(vm.teamFuturesFailed, "Retry recovery should clear teamFuturesFailed")
        XCTAssertFalse(vm.teamFuturesLoading)
        XCTAssertEqual(vm.teamFutures?.items.count, 1)
        XCTAssertEqual(client.futuresCalls, 2)
    }

    func testFuturesDeadlineTimeoutSetsTeamFuturesFailedAndKeepsGamesIntact() async throws {
        let gate = AsyncGate()
        let futures = try Self.decodeFutures()
        let client = ScriptedClient(
            feedResult: .success(try Self.decodeFeed(withGame: true)),
            futuresReplies: [.success(futures)],
            futuresGate: gate
        )
        let vm = MyStuffViewModel(
            client: client,
            telemetry: nil,
            autoRefreshEnabled: false,
            optionalDeadline: 0.05,
            requiredAttempts: 1,
            retryBackoff: 0
        )

        vm.viewDidStart()
        await vm.startLoad()
        await settleOptional { !vm.teamFuturesLoading && vm.teamFuturesFailed }

        XCTAssertNil(vm.error)
        XCTAssertEqual(vm.items.count, 1, "Loaded games stay visible when optional futures time out")
        XCTAssertTrue(vm.teamFuturesFailed, "Timeout past optionalDeadline must flag teamFuturesFailed")
        XCTAssertFalse(vm.teamFuturesLoading)
    }

    func testLandingViewModelMarksTeamFuturesFailedEvenWithNoLocalFollowsOrGames() async throws {
        let suite = "Tests13552.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }

        let discoverFeed = try Self.decodeFeed(withGame: true)
        let landingVM = MyStuffLandingViewModel295A(
            defaults: defaults,
            discoverFetcher: { discoverFeed }
        )

        await landingVM.refresh(
            followedSubjects: [],
            savedPins: [],
            pinContent: [:],
            signedInItems: [],
            signedInTeamFutures: nil,
            signedInTeamFeedFailed: false,
            signedInTeamFuturesFailed: true,
            signedInTeamFuturesLoading: false
        )

        XCTAssertFalse(landingVM.loadFailed)
        XCTAssertTrue(landingVM.teamFuturesFailed, "Signed-in /api/me/team-futures failure must surface even when Discover loads and local follows are empty")
        XCTAssertFalse(landingVM.discoverItems.isEmpty)

        // Recovery clears teamFuturesFailed
        await landingVM.refresh(
            followedSubjects: [],
            savedPins: [],
            pinContent: [:],
            signedInItems: [],
            signedInTeamFutures: try Self.decodeFutures(),
            signedInTeamFeedFailed: false,
            signedInTeamFuturesFailed: false,
            signedInTeamFuturesLoading: false
        )
        XCTAssertFalse(landingVM.teamFuturesFailed)
    }

    // MARK: - 390pt Light & Dark Render + Vision OCR Proof

    #if os(iOS)
    func testFailedTeamFuturesRendersPlainErrorAndTryAgainAt390LightAndDark() async throws {
        let discoverFeed = try Self.decodeFeed(withGame: true)
        let gamePair: [(event: FeedEventData, awayVerified: Bool)] = discoverFeed.items.compactMap { item in
            guard let ev = item.event else { return nil }
            return (event: ev, awayVerified: true)
        }
        let noGamesSnapshot = MyStuffLandingViewModel295A.PreloadedSnapshot(
            liveEvents: [],
            nextEvents: [],
            nextMarkets: [],
            movedEntries: [],
            discoverItems: discoverFeed.items,
            loadFailed: false,
            hydratingRemainingCount: 0,
            teamFuturesFailed: true,
            teamFuturesRetrying: false
        )
        let withGamesSnapshot = MyStuffLandingViewModel295A.PreloadedSnapshot(
            liveEvents: [],
            nextEvents: gamePair,
            nextMarkets: [],
            movedEntries: [],
            discoverItems: [],
            loadFailed: false,
            hydratingRemainingCount: 0,
            teamFuturesFailed: true,
            teamFuturesRetrying: false
        )

        let imgNoGamesLight = await renderLanding(snapshot: noGamesSnapshot, scheme: .light)
        let imgNoGamesDark = await renderLanding(snapshot: noGamesSnapshot, scheme: .dark)
        let imgWithGameLight = await renderLanding(snapshot: withGamesSnapshot, scheme: .light)
        let imgWithGameDark = await renderLanding(snapshot: withGamesSnapshot, scheme: .dark)

        let ocrNoGamesLight = recognizeText(in: imgNoGamesLight).replacingOccurrences(of: " | ", with: " ")
        XCTAssertTrue(ocrNoGamesLight.contains("Couldn't load your teams' futures"), "Missing failure headline: \(ocrNoGamesLight)")
        XCTAssertTrue(ocrNoGamesLight.contains("Your teams are still saved. This part didn't load."), "Missing plain copy: \(ocrNoGamesLight)")
        XCTAssertTrue(ocrNoGamesLight.contains("Try again"), "Missing Try again control: \(ocrNoGamesLight)")
        XCTAssertFalse(ocrNoGamesLight.contains("No Games Right Now"), "Must never imply no follows: \(ocrNoGamesLight)")

        let ocrWithGameLight = recognizeText(in: imgWithGameLight).replacingOccurrences(of: " | ", with: " ")
        XCTAssertTrue(ocrWithGameLight.contains("Couldn't load your teams' futures"), "Missing failure headline alongside game: \(ocrWithGameLight)")
        XCTAssertTrue(ocrWithGameLight.contains("Your teams are still saved. This part didn't load."), "Missing plain copy alongside game: \(ocrWithGameLight)")
        XCTAssertTrue(ocrWithGameLight.contains("Try again"), "Missing Try again beside game: \(ocrWithGameLight)")
        XCTAssertTrue(ocrWithGameLight.contains("Celtics") || ocrWithGameLight.contains("Next for you"), "Missing game card: \(ocrWithGameLight)")

        // Fallback teamFeedView (legacy MyStuffView path) also shows plain error + Try again instead of "No Games Right Now"
        let client = ScriptedClient(
            feedResult: .success(try Self.decodeFeed(withGame: false)),
            futuresReplies: [.failure(FakeHTTPError())]
        )
        let fallbackVM = MyStuffViewModel(
            client: client,
            telemetry: nil,
            autoRefreshEnabled: false,
            optionalDeadline: 1.0,
            requiredAttempts: 1,
            retryBackoff: 0
        )
        let imgFallbackLight = await renderFallbackTeamFeed(vm: fallbackVM, scheme: .light)
        let ocrFallback = recognizeText(in: imgFallbackLight).replacingOccurrences(of: " | ", with: " ")
        XCTAssertTrue(ocrFallback.contains("Couldn't Load Your Teams' Futures") || ocrFallback.contains("Couldn’t Load Your Teams’ Futures"), "Fallback view missing futures failure copy: \(ocrFallback)")
        XCTAssertTrue(ocrFallback.contains("Your teams are still saved. This part didn't load."), "Fallback view missing plain copy: \(ocrFallback)")
        XCTAssertTrue(ocrFallback.contains("Try again"), "Fallback view missing Try again button: \(ocrFallback)")
        XCTAssertFalse(ocrFallback.contains("No Games Right Now"), "Fallback view fell into No Games Right Now: \(ocrFallback)")

        let fallbackClientDark = ScriptedClient(
            feedResult: .success(try Self.decodeFeed(withGame: false)),
            futuresReplies: [.failure(FakeHTTPError())]
        )
        let fallbackVMDark = MyStuffViewModel(
            client: fallbackClientDark,
            telemetry: nil,
            autoRefreshEnabled: false,
            optionalDeadline: 1.0,
            requiredAttempts: 1,
            retryBackoff: 0
        )
        let imgFallbackDark = await renderFallbackTeamFeed(vm: fallbackVMDark, scheme: .dark)

        let env = ProcessInfo.processInfo.environment
        if let exportDir = env["EXPORT_MYSTUFF_FAIL_13552_DIR"] ?? env["TEST_RUNNER_EXPORT_MYSTUFF_FAIL_13552_DIR"],
           !exportDir.isEmpty {
            let dir = URL(fileURLWithPath: exportDir, isDirectory: true)
            try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            try imgNoGamesLight.pngData()?.write(to: dir.appendingPathComponent("13552-nogames-fail-light-390.png"))
            try imgNoGamesDark.pngData()?.write(to: dir.appendingPathComponent("13552-nogames-fail-dark-390.png"))
            try imgWithGameLight.pngData()?.write(to: dir.appendingPathComponent("13552-withgame-fail-light-390.png"))
            try imgWithGameDark.pngData()?.write(to: dir.appendingPathComponent("13552-withgame-fail-dark-390.png"))
            try imgFallbackLight.pngData()?.write(to: dir.appendingPathComponent("13552-fallback-fail-light-390.png"))
            try imgFallbackDark.pngData()?.write(to: dir.appendingPathComponent("13552-fallback-fail-dark-390.png"))
        }
    }

    private func renderLanding(
        snapshot: MyStuffLandingViewModel295A.PreloadedSnapshot,
        scheme: ColorScheme
    ) async -> UIImage {
        let suite = "RenderLanding13552.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        let followMgr = FollowManager295A(defaults: defaults)
        let pins = PinManager(defaults: defaults, allowLegacyGuestPins: false)
        let vm = MyStuffLandingViewModel295A(defaults: defaults, preloaded: snapshot)

        let root = NavigationStack {
            MyStuffLandingView295A(
                landingVM: vm,
                path: .constant(NavigationPath()),
                onOpenDiscover: {},
                onManagePins: {},
                onRefresh: {},
                onRetryTeamFutures: {}
            )
            .navigationTitle("My Stuff")
        }
        .environment(\.followManager295A, followMgr)
        .environmentObject(pins)
        .frame(width: 390, height: 844)
        .environment(\.colorScheme, scheme)
        .environment(\.horizontalSizeClass, .compact)

        return await rasterize(root, width: 390, height: 844, scheme: scheme)
    }

    private func renderFallbackTeamFeed(
        vm: MyStuffViewModel,
        scheme: ColorScheme
    ) async -> UIImage {
        let auth = AuthManager()
        auth.user = AuthUser(
            id: 902,
            email: "reader@example.com",
            displayName: "Reader",
            photoUrl: nil,
            onboardingCompleted: true,
            createdAt: nil
        )
        auth.isLoading = false
        let nav = NavigationCoordinator()
        let pins = PinManager(defaults: UserDefaults(suiteName: "RenderFallback13552.\(UUID().uuidString)")!, allowLegacyGuestPins: false)

        let root = MyStuffView(viewModelForTest: vm)
            .environmentObject(auth)
            .environmentObject(nav)
            .environmentObject(pins)
            .frame(width: 390, height: 844)
            .environment(\.colorScheme, scheme)
            .environment(\.horizontalSizeClass, .compact)

        return await rasterize(root, width: 390, height: 844, scheme: scheme, waitSeconds: 0.45)
    }

    private func rasterize<V: View>(
        _ root: V,
        width: CGFloat,
        height: CGFloat,
        scheme: ColorScheme,
        waitSeconds: TimeInterval = 0.25
    ) async -> UIImage {
        let style: UIUserInterfaceStyle = scheme == .dark ? .dark : .light
        let host = hostForMeasurement(root, at: .large)
        host.overrideUserInterfaceStyle = style
        let rect = CGRect(x: 0, y: 0, width: width, height: height)
        host.view.frame = rect

        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: rect)
        window.frame = rect
        window.overrideUserInterfaceStyle = style
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        let until = Date().addingTimeInterval(waitSeconds)
        repeat {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            try? await Task.sleep(nanoseconds: 35_000_000)
        } while Date() < until

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 3.0
        fmt.opaque = true
        return UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { ctx in
            let bg = (scheme == .dark) ? UIColor(white: 0.08, alpha: 1.0) : UIColor.white
            bg.setFill()
            ctx.fill(host.view.bounds)
            if !host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true) {
                host.view.layer.render(in: ctx.cgContext)
            }
        }
    }

    private func recognizeText(in image: UIImage) -> String {
        guard let cg = image.cgImage else { return "" }
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
        return (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: " | ")
    }
    #endif
}
