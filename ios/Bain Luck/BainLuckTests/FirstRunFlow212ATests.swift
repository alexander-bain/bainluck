import SwiftUI
#if os(iOS)
import UIKit
import Vision
#endif
import XCTest
@testable import Bain_Luck

#if os(iOS)
private final class TraitContainer212A: UIViewController {
    private let child: UIViewController
    private let overrideTraits: UITraitCollection

    init(child: UIViewController, traits: UITraitCollection) {
        self.child = child
        self.overrideTraits = traits
        super.init(nibName: nil, bundle: nil)
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        addChild(child)
        child.view.frame = view.bounds
        child.view.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        view.addSubview(child.view)
        setOverrideTraitCollection(overrideTraits, forChild: child)
        child.didMove(toParent: self)
    }
}
#endif

@MainActor
final class FirstRunFlow212ATests: XCTestCase {

    private var iosRoot: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
    }

    private func source(_ relativePath: String) throws -> String {
        try String(contentsOf: iosRoot.appendingPathComponent(relativePath), encoding: .utf8)
    }

    private func makeDecoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    // MARK: - Launch Guard & Copy Rules

    func testNoNotificationOrTelemetryPromptBlocksFirstLaunch() throws {
        let appSrc = try source("Bain Luck/Bain_LuckApp.swift")
        let cleanCode = appSrc
            .components(separatedBy: .newlines)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")

        XCTAssertFalse(cleanCode.contains("requestPermissionAfterDelay("))
        XCTAssertTrue(cleanCode.contains("FirstRunStorageKeys212A.onboardedKey"))
    }

    func testOldQuizCopyReplacedAndPointsUsedInsteadOfPts() throws {
        let onboardSrc = try source("Bain Luck/Views/OnboardingView.swift")
        XCTAssertFalse(onboardSrc.contains("Where do you follow sports?"))
        XCTAssertFalse(onboardSrc.contains("What do you care about?"))
        XCTAssertFalse(onboardSrc.contains("Any rivals?"))

        let modelsSrc = try source("Bain Luck/Utilities/FirstRunModels212A.swift")
            .components(separatedBy: .newlines)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")
        XCTAssertFalse(modelsSrc.contains("\"pts"))
        XCTAssertEqual(FirstRunCard212A.shiftText(points: 4), "▲ up 4 points")
        XCTAssertEqual(FirstRunCard212A.shiftText(points: 1), "▲ up 1 point")
        XCTAssertEqual(FirstRunCard212A.shiftText(points: -6), "▼ down 6 points")
    }

    func testDefaultPairsIncludeRealNumbersAndNonSportsPairs() {
        let pairs = FirstRunPair212A.buildPairs(from: [])
        XCTAssertEqual(pairs.count, 3)
        XCTAssertTrue(pairs.contains { !$0.topCard.isSports && !$0.bottomCard.isSports },
                      "At least one pair must be wholly non-sports")
        for pair in pairs {
            XCTAssertGreaterThan(pair.topCard.percent, 0)
            XCTAssertGreaterThan(pair.bottomCard.percent, 0)
            XCTAssertTrue(!pair.topCard.isSports || !pair.bottomCard.isSports,
                          "Every pair must expose non-sports content")
        }
    }

    // MARK: - Interactive State Behavior (Tap Feedback, Non-Clearing Search, Multi-Sport Disambiguation, Skip)

    func testPairTapShowsSelectionImmediatelyAndSkipWorksOnEveryScreen() {
        let defaults = UserDefaults(suiteName: "FirstRun212A.Tap.\(UUID().uuidString)")!
        let follow = FollowManager295A(defaults: defaults, initialSubjects: [])
        let vm = FirstRunViewModel212A(
            defaults: defaults,
            debounceNs: 0,
            autoAdvanceDelayNs: 0
        )

        XCTAssertEqual(vm.stepIndex, 0)
        vm.selectChoice(.bottom, forPairIndex: 0, followManager: follow)
        XCTAssertEqual(vm.selectedChoices[0], .bottom, "First tap must register choice immediately")
        XCTAssertEqual(vm.stepIndex, 1)

        // Skip works on pair screens and final typeahead screen.
        let auth = AuthManager()
        var dismissed = false
        vm.skipCurrentStep(followManager: follow, authManager: auth) { dismissed = true }
        XCTAssertEqual(vm.stepIndex, 2)
        XCTAssertFalse(dismissed)

        vm.skipCurrentStep(followManager: follow, authManager: auth) { dismissed = true }
        XCTAssertEqual(vm.stepIndex, 3)
        XCTAssertTrue(vm.isOnTypeaheadStep)
        XCTAssertFalse(dismissed)

        vm.skipCurrentStep(followManager: follow, authManager: auth) { dismissed = true }
        XCTAssertTrue(dismissed)
        XCTAssertTrue(defaults.bool(forKey: FirstRunStorageKeys212A.onboardedKey))
    }

    func testTypeaheadPreservesQueryAndResultsAfterFirstPickAndDisambiguatesSchoolTeams() async throws {
        let decoder = makeDecoder()
        let brownTeamResultsJSON = """
        [
          {"id": 2392, "name": "Brown Bears", "location": "Providence", "sport_key": "basketball_ncaab", "logo_url": null, "abbreviation": "BRWN", "sports": []},
          {"id": 19933, "name": "Brown Bears", "location": "Providence", "sport_key": "americanfootball_ncaaf", "logo_url": null, "abbreviation": "BRWN", "sports": []},
          {"id": 2690, "name": "Brown Bears", "location": "Providence", "sport_key": "basketball_wncaab", "logo_url": null, "abbreviation": "BRWN", "sports": []}
        ]
        """
        let brownGlobalJSON = """
        {
          "query": "brown",
          "teams": [
            {"id": 2392, "name": "Brown Bears", "slug": "brown-bears", "abbreviation": "BRWN", "logo": null, "record": "2-5", "sport_key": "basketball_ncaab", "query_names_team": true}
          ],
          "event_concepts": [],
          "results": [],
          "futures": []
        }
        """
        let brownTeamResults = try decoder.decode([TeamSearchResult].self, from: Data(brownTeamResultsJSON.utf8))
        let brownGlobal = try decoder.decode(SearchResponse.self, from: Data(brownGlobalJSON.utf8))

        let defaults = UserDefaults(suiteName: "FirstRun212A.Brown.\(UUID().uuidString)")!
        let follow = FollowManager295A(defaults: defaults, initialSubjects: [])
        let vm = FirstRunViewModel212A(
            initialStep: 3,
            defaults: defaults,
            debounceNs: 0,
            autoAdvanceDelayNs: 0,
            searchLocationTeams: { _ in [] },
            searchTeamsByName: { _ in brownTeamResults },
            searchGlobal: { _ in brownGlobal }
        )

        vm.searchQuery = "brown"
        await vm.performTypeahead(query: "brown")

        XCTAssertEqual(vm.suggestions.count, 3)
        let chipTexts = vm.suggestions.map(\.chipDisplayText)
        XCTAssertEqual(Set(chipTexts).count, 3, "Every Brown Bears team must carry a distinct sport label: \(chipTexts)")
        XCTAssertTrue(chipTexts.contains { $0.contains("NCAAB") })
        XCTAssertTrue(chipTexts.contains { $0.contains("NCAAF") })
        XCTAssertTrue(chipTexts.contains { $0.contains("WNCAAB") })

        // Pick #1: first tap adds immediately, query & results MUST remain on screen for pick #2.
        vm.toggleSuggestion(vm.suggestions[0], followManager: follow)
        XCTAssertTrue(vm.isPicked(vm.suggestions[0]))
        XCTAssertEqual(vm.searchQuery, "brown", "Search box must NOT clear after picking one team")
        XCTAssertEqual(vm.suggestions.count, 3, "Results must stay on screen after a pick")

        // Pick #2 without re-typing: immediately obvious and works in one tap.
        vm.toggleSuggestion(vm.suggestions[1], followManager: follow)
        XCTAssertEqual(vm.pickedItems.count, 2)
        XCTAssertEqual(follow.subjects.count, 2)
    }

    // MARK: - #13517 Width & Dynamic Type Truncation Audit + 390pt Light/Dark Visual Captures

    #if os(iOS)
    func testNoTeamNameTruncatedOn390And440AtDefaultAndAX5AndExportSheets() async throws {
        let decoder = makeDecoder()

        let bostonResultsJSON = """
        [
          {"id": 100, "name": "Boston Celtics", "location": "Boston", "sport_key": "basketball_nba", "logo_url": null, "abbreviation": "BOS", "sports": []},
          {"id": 574, "name": "Boston Bruins", "location": "Boston", "sport_key": "icehockey_nhl", "logo_url": null, "abbreviation": "BOS", "sports": []},
          {"id": 10709, "name": "Boston Red Sox", "location": "Boston", "sport_key": "baseball_mlb", "logo_url": null, "abbreviation": "BOS", "sports": []},
          {"id": 511, "name": "New England Revolution", "location": "Boston", "sport_key": "soccer_usa_mls", "logo_url": null, "abbreviation": "NE", "sports": []},
          {"id": 500, "name": "New England Patriots", "location": "Boston", "sport_key": "americanfootball_nfl", "logo_url": null, "abbreviation": "NE", "sports": []},
          {"id": 2392, "name": "Brown Bears", "location": "Providence", "sport_key": "basketball_ncaab", "logo_url": null, "abbreviation": "BRWN", "sports": []},
          {"id": 19933, "name": "Brown Bears", "location": "Providence", "sport_key": "americanfootball_ncaaf", "logo_url": null, "abbreviation": "BRWN", "sports": []}
        ]
        """
        let bostonTeams = try decoder.decode([TeamSearchResult].self, from: Data(bostonResultsJSON.utf8))
        let bostonGlobal = try decoder.decode(
            SearchResponse.self,
            from: Data(#"{"query":"boston","teams":[],"event_concepts":[],"results":[],"futures":[]}"#.utf8)
        )

        // 1) Prove ZERO truncation (#13517) across 390pt and 440pt, Default and AX5
        let matrix: [(tag: String, width: CGFloat, size: DynamicTypeSize)] = [
            ("13517-boston-390-default", 390, .large),
            ("13517-boston-390-ax5", 390, .accessibility5),
            ("13517-boston-440-default", 440, .large),
            ("13517-boston-440-ax5", 440, .accessibility5),
        ]
        for cfg in matrix {
            let defaults = UserDefaults(suiteName: "FirstRun212A.13517.\(UUID().uuidString)")!
            let follow = FollowManager295A(defaults: defaults, initialSubjects: [])
            let vm = FirstRunViewModel212A(
                initialStep: 3,
                defaults: defaults,
                debounceNs: 0,
                autoAdvanceDelayNs: 0,
                searchLocationTeams: { _ in bostonTeams },
                searchTeamsByName: { _ in bostonTeams },
                searchGlobal: { _ in bostonGlobal }
            )
            vm.searchQuery = "Boston"
            await vm.performTypeahead(query: "Boston")
            vm.toggleSuggestion(vm.suggestions[0], followManager: follow) // Boston Celtics
            vm.toggleSuggestion(vm.suggestions[3], followManager: follow) // New England Revolution
            vm.toggleSuggestion(vm.suggestions[5], followManager: follow) // Brown Bears NCAAB
            vm.toggleSuggestion(vm.suggestions[6], followManager: follow) // Brown Bears NCAAF

            let ocr = try await renderAndOCR(
                view: FirstRunFlowView212A(viewModelForTest: vm)
                    .environment(\.followManager295A, follow),
                filename: "\(cfg.tag).png",
                width: cfg.width,
                height: cfg.size.isAccessibilitySize ? 1400 : 900,
                colorScheme: .light,
                dynamicTypeSize: cfg.size
            )
            let truncs = ocr.filter { $0.contains("…") || $0.contains("...") }
            let joined = ocr.joined(separator: " ")
            XCTAssertEqual(truncs, [], "Truncated text at \(cfg.tag): \(truncs) (all=\(ocr))")
            XCTAssertTrue(joined.contains("New England") && joined.contains("Revolution"), "Missing full New England Revolution at \(cfg.tag): \(ocr)")
            XCTAssertTrue(joined.contains("Boston") && joined.contains("Celtics"), "Missing full Boston Celtics at \(cfg.tag): \(ocr)")
            XCTAssertTrue(joined.contains("NCAAB"))
            XCTAssertTrue(joined.contains("NCAAF"))
        }

        // 2) Export full 390pt Light & Dark set when requested
        let env = ProcessInfo.processInfo.environment
        guard let exportDir = env["EXPORT_212A_RENDER_DIR"] ?? env["TEST_RUNNER_EXPORT_212A_RENDER_DIR"] ?? env["SIMCTL_CHILD_EXPORT_212A_RENDER_DIR"],
              !exportDir.isEmpty else {
            return
        }

        let eventJSON = """
        {
          "id": 9101,
          "sport": "americanfootball_nfl",
          "home_team": "Cincinnati Bengals",
          "away_team": "Pittsburgh Steelers",
          "commence_time": "2026-11-29T18:00:00Z",
          "status": "scheduled",
          "home_team_data": {"abbreviation": "CIN", "primary_color": "#FB4F14"},
          "away_team_data": {"abbreviation": "PIT", "primary_color": "#FFB612"},
          "pregame_projection": {"projected_home_score": 25.0, "projected_away_score": 20.0},
          "current_odds": {"away_probability": 0.34, "home_probability": 0.66, "away_rendered_percent": 34, "home_rendered_percent": 66}
        }
        """
        let sampleEvent = try decoder.decode(EventDetail.self, from: Data(eventJSON.utf8))
        let historyJSON = """
        {
          "event_id": 9101,
          "home_team": "Cincinnati Bengals",
          "away_team": "Pittsburgh Steelers",
          "status": "scheduled",
          "history": [
            {"timestamp": "2026-11-20T18:00:00Z", "home_probability": 0.61, "away_probability": 0.39},
            {"timestamp": "2026-11-21T18:00:00Z", "home_probability": 0.63, "away_probability": 0.37},
            {"timestamp": "2026-11-22T18:00:00Z", "home_probability": 0.65, "away_probability": 0.35},
            {"timestamp": "2026-11-23T18:00:00Z", "home_probability": 0.66, "away_probability": 0.34}
          ]
        }
        """
        let sampleHistory = try decoder.decode(EventHistoryResponse.self, from: Data(historyJSON.utf8))

        for (scheme, suffix) in [(ColorScheme.light, "light"), (ColorScheme.dark, "dark")] {
            // 1A: Shared link arrival
            _ = try await renderAndOCR(
                view: SharedLinkArrivalView212A(
                    event: sampleEvent,
                    preloadedHistory: sampleHistory,
                    moreCards: [
                        FirstRunPair212A.fallbackNonSportsCard1,
                        FirstRunPair212A.fallbackSportsCard2,
                        FirstRunPair212A.fallbackNonSportsCard2,
                    ],
                    onOpenFullGame: {},
                    onOpenDiscover: {}
                ),
                filename: "212a-01-shared-arrival-\(suffix)-390.png",
                width: 390,
                height: 844,
                colorScheme: scheme,
                dynamicTypeSize: .large
            )

            // 2A..2C Pairs
            for step in 0...2 {
                let d = UserDefaults(suiteName: "FirstRun212A.P\(step).\(UUID().uuidString)")!
                let f = FollowManager295A(defaults: d, initialSubjects: [])
                let dispVM = FirstRunViewModel212A(
                    arrivedHeadline: step == 0 ? "Steelers at Bengals" : nil,
                    initialStep: step,
                    defaults: d,
                    debounceNs: 0,
                    autoAdvanceDelayNs: 10_000_000_000
                )
                if step == 1 { dispVM.selectChoice(.bottom, forPairIndex: 1, followManager: f) }
                _ = try await renderAndOCR(
                    view: FirstRunFlowView212A(viewModelForTest: dispVM).environment(\.followManager295A, f),
                    filename: "212a-02\(UnicodeScalar(97 + step)!)-\(suffix)-390.png",
                    width: 390,
                    height: 844,
                    colorScheme: scheme,
                    dynamicTypeSize: .large
                )
            }

            // 2D Unified Typeahead ("Boston" + "Brown")
            let dt = UserDefaults(suiteName: "FirstRun212A.Typeahead.\(UUID().uuidString)")!
            let ft = FollowManager295A(defaults: dt, initialSubjects: [])
            let tvm = FirstRunViewModel212A(
                initialStep: 3,
                defaults: dt,
                debounceNs: 0,
                autoAdvanceDelayNs: 0,
                searchLocationTeams: { _ in bostonTeams },
                searchTeamsByName: { _ in bostonTeams },
                searchGlobal: { _ in bostonGlobal }
            )
            tvm.searchQuery = "Boston"
            await tvm.performTypeahead(query: "Boston")
            tvm.toggleSuggestion(tvm.suggestions[0], followManager: ft)
            tvm.toggleSuggestion(tvm.suggestions[5], followManager: ft)
            tvm.toggleSuggestion(tvm.suggestions[6], followManager: ft)
            _ = try await renderAndOCR(
                view: FirstRunFlowView212A(viewModelForTest: tvm).environment(\.followManager295A, ft),
                filename: "212a-02d-typeahead-\(suffix)-390.png",
                width: 390,
                height: 844,
                colorScheme: scheme,
                dynamicTypeSize: .large
            )

            // 4A Contextual alerts ask at pin
            _ = try await renderAndOCR(
                view: VStack {
                    Spacer()
                    GameAlertsPinPromptSheet13084(onTurnOn: {}, onNotNow: {})
                    Spacer()
                }
                .background(DS.surface),
                filename: "212a-04a-alert-ask-\(suffix)-390.png",
                width: 390,
                height: 844,
                colorScheme: scheme,
                dynamicTypeSize: .large
            )

            // 5 Earned sign-in card
            _ = try await renderAndOCR(
                view: VStack {
                    Spacer()
                    EarnedSignInCard212A(onAppleSignIn: {}, onGoogleSignIn: {}, onDismissLocalOnly: {})
                        .padding(.horizontal, 16)
                    Spacer()
                }
                .background(DS.surface),
                filename: "212a-05-earned-signin-\(suffix)-390.png",
                width: 390,
                height: 844,
                colorScheme: scheme,
                dynamicTypeSize: .large
            )

            // 6 About Bain Luck worked 64% strip (inside NavigationStack just like Settings & Why? push)
            _ = try await renderAndOCR(
                view: NavigationStack {
                    AboutBainLuckView212A(showsBackToDiscoverCTA: true, onBackToDiscover: {})
                },
                filename: "212a-06-about-64pct-\(suffix)-390.png",
                width: 390,
                height: 844,
                colorScheme: scheme,
                dynamicTypeSize: .large
            )
        }
    }

    private func renderAndOCR<V: View>(
        view: V,
        filename: String,
        width: CGFloat,
        height: CGFloat,
        colorScheme: ColorScheme,
        dynamicTypeSize: DynamicTypeSize
    ) async throws -> [String] {
        let uiStyle: UIUserInterfaceStyle = colorScheme == .dark ? .dark : .light
        let uiCategory: UIContentSizeCategory = dynamicTypeSize.isAccessibilitySize
            ? .accessibilityExtraExtraExtraLarge
            : .large
        let auth = AuthManager()
        let renderDefaults = UserDefaults(suiteName: "FirstRun212A.Render.\(UUID().uuidString)")!
        let pins = PinManager(defaults: renderDefaults, serverLoad: { PinsResponse(events: [], futures: []) }, serverSync: { _, _, _ in })
        let root = view
            .frame(width: width, height: height, alignment: .topLeading)
            .environment(\.horizontalSizeClass, .compact)
            .environment(\.colorScheme, colorScheme)
            .environment(\.dynamicTypeSize, dynamicTypeSize)
            .environmentObject(NavigationCoordinator())
            .environmentObject(pins)
            .environmentObject(auth)

        let traits = UITraitCollection(traitsFrom: [
            UITraitCollection(horizontalSizeClass: .compact),
            UITraitCollection(userInterfaceStyle: uiStyle),
            UITraitCollection(preferredContentSizeCategory: uiCategory),
        ])
        let host = hostForMeasurement(root, at: dynamicTypeSize)
        let container = TraitContainer212A(child: host, traits: traits)
        container.view.backgroundColor = colorScheme == .dark ? UIColor(red: 0.059, green: 0.067, blue: 0.082, alpha: 1) : .systemGroupedBackground
        container.view.frame = CGRect(x: 0, y: 0, width: width, height: height)

        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: container.view.frame)
        window.frame = container.view.frame
        window.rootViewController = container
        window.makeKeyAndVisible()
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        for _ in 0..<8 {
            container.view.setNeedsLayout()
            container.view.layoutIfNeeded()
            try? await Task.sleep(nanoseconds: 40_000_000)
        }

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 2.0
        fmt.opaque = true
        let image = UIGraphicsImageRenderer(bounds: container.view.bounds, format: fmt).image { _ in
            _ = container.view.drawHierarchy(in: container.view.bounds, afterScreenUpdates: true)
        }

        let env = ProcessInfo.processInfo.environment
        if let outDir = env["EXPORT_212A_RENDER_DIR"] ?? env["TEST_RUNNER_EXPORT_212A_RENDER_DIR"] ?? env["SIMCTL_CHILD_EXPORT_212A_RENDER_DIR"],
           !outDir.isEmpty,
           let png = image.pngData() {
            let dirURL = URL(fileURLWithPath: outDir, isDirectory: true)
            try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
            try png.write(to: dirURL.appendingPathComponent(filename))
        }

        guard let cg = image.cgImage else { return [] }
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
        return (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
    }
    #endif
}
