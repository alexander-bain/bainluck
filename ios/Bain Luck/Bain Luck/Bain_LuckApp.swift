//
//  Bain_LuckApp.swift
//  Bain Luck
//
//  Created by bain on 2/27/26.
//

import FirebaseCore
import FirebaseCrashlytics
import GoogleSignIn
import SwiftUI
#if canImport(UIKit)
import UIKit
#elseif canImport(AppKit)
import AppKit
#endif

@main
struct Bain_LuckApp: App {
    #if os(iOS)
    @UIApplicationDelegateAdaptor(BainLuckAppDelegate.self) var appDelegate
    #elseif os(macOS)
    @NSApplicationDelegateAdaptor(BainLuckMacAppDelegate.self) var macAppDelegate
    #endif
    @StateObject private var authManager = AuthManager()
    @StateObject private var navCoordinator = NavigationCoordinator()
    @StateObject private var pinManager = PinManager()
    /// Whether the consent ask is showing. Seeded from the authority: `true`
    /// only when no choice has ever been recorded.
    @State private var showTelemetryConsent = TelemetryConsent.shared.needsChoice


    init() {
        // Pin the launch reference as early as app code can run, so "cold" means
        // time since launch rather than time since whichever screen happened to
        // measure itself first (latency/121).
        AppLaunchClock.touch()
        FirebaseConfiguration.shared.setLoggerLevel(.min)
        FirebaseApp.configure()
        // Resolve consent BEFORE the first telemetry call below (Queue 311 A3 /
        // ruling 007, #1632). Collection is off by default in the plist, so
        // this either leaves it off (no choice yet, or a refusal) or restores a
        // previous grant. Everything after this line is gated; nothing before
        // it may touch Firebase.
        TelemetryConsent.shared.initialize()
        // Subscribe to FCM registration tokens. After `configure()`, by
        // requirement — the delegate is ignored before it (#1159).
        NotificationManager.shared.startMessaging()
        #if os(macOS)
        AnalyticsService.setUserProperty("macos", forName: "platform")
        #else
        AnalyticsService.setUserProperty("ios", forName: "platform")
        #endif

        // App version
        if let version = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String {
            AnalyticsService.setUserProperty(version, forName: "app_version")
        }

        // Return visit + session count tracking
        let defaults = UserDefaults.standard
        let sessionCount = defaults.integer(forKey: "bainluck_session_count") + 1
        defaults.set(sessionCount, forKey: "bainluck_session_count")
        let today = Calendar.current.startOfDay(for: Date())
        if let lastVisit = defaults.object(forKey: "bainluck_last_visit") as? Date {
            let daysSince = Calendar.current.dateComponents([.day], from: lastVisit, to: today).day ?? 0
            if daysSince > 0 {
                AnalyticsService.trackReturnVisit(daysSinceLast: daysSince, sessionNumber: sessionCount)
            }
        }
        defaults.set(today, forKey: "bainluck_last_visit")

        // Days since install
        if defaults.object(forKey: "bainluck_install_date") == nil {
            defaults.set(today, forKey: "bainluck_install_date")
        }
        if let installDate = defaults.object(forKey: "bainluck_install_date") as? Date {
            let daysSinceInstall = Calendar.current.dateComponents([.day], from: installDate, to: today).day ?? 0
            AnalyticsService.setUserProperty(String(daysSinceInstall), forName: "days_since_install")
        }
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(authManager)
                .environmentObject(navCoordinator)
                .environmentObject(pinManager)
                .overlay {
                    PinFeedbackToast()
                        .environmentObject(pinManager)
                }
                // The consent ask (Queue 311 A3 / #1632). Presented when no
                // choice has been recorded — and only then, so it never
                // re-nags someone who declined. Nothing is collected while it
                // is up: no-choice IS a denial, so an ignored prompt is the
                // safe state rather than a leak with a timer on it.
                .sheet(isPresented: $showTelemetryConsent) {
                    TelemetryConsentPrompt { _ in
                        showTelemetryConsent = false
                    }
                }
                #if os(macOS)
                .navigationTitle(navCoordinator.liveGameTitle)
                .task { await pollLiveGames() }
                #endif
                .onChange(of: authManager.isAuthenticated) { _, isAuth in
                    pinManager.setAuthenticated(isAuth)
                    NotificationManager.shared.setUser(id: isAuth ? authManager.user?.id : nil)
                    AnalyticsService.setCrashReportingUserId(
                        isAuth ? ((authManager.user?.id).map { String($0) } ?? "") : ""
                    )
                    Task {
                        if isAuth {
                            await pinManager.syncLocalToServer()
                        }
                        await pinManager.loadPins()
                    }
                }
                .task {
                    pinManager.setAuthenticated(authManager.isAuthenticated)
                    await pinManager.loadPins()
                    // Wire up notification deep linking and request permission
                    NotificationManager.shared.navCoordinator = navCoordinator
                    NotificationManager.shared.requestPermissionAfterDelay()
                    if let userId = authManager.user?.id {
                        NotificationManager.shared.setUser(id: userId)
                        AnalyticsService.setCrashReportingUserId(String(userId))
                    }
                    // The LOOK rig's one way to reach a screen that is not the
                    // default tab (#3157). Routed through `handleURL`, so it can
                    // only ever open something a real link could open, and only
                    // when `-launch_route` was passed. Last in this task on
                    // purpose: nothing above it is allowed to depend on the
                    // rig's presence.
                    if let route = LaunchRig.route() {
                        try? await Task.sleep(
                            nanoseconds: UInt64(LaunchRig.routeDelay * 1_000_000_000)
                        )
                        _ = navCoordinator.handleURL(route)
                    }
                }
                #if os(iOS)
                .onReceive(NotificationCenter.default.publisher(for: UIScene.didActivateNotification)) { _ in
                    authManager.checkCredentialState()
                    authManager.retrySessionIfNeeded()
                }
                #elseif os(macOS)
                .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
                    authManager.checkCredentialState()
                    authManager.retrySessionIfNeeded()
                }
                #endif
                .onOpenURL { url in
                    // Google Sign-In uses the reversed client ID scheme
                    if url.scheme?.contains("googleusercontent") == true {
                        GIDSignIn.sharedInstance.handle(url)
                    } else {
                        _ = navCoordinator.handleURL(url)
                    }
                }
                .onContinueUserActivity(NSUserActivityTypeBrowsingWeb) { activity in
                    if let url = activity.webpageURL {
                        _ = navCoordinator.handleURL(url)
                    }
                }
                .preferredColorScheme(.light)
        }
        #if os(macOS)
        .defaultSize(width: 1200, height: 800)
        .commands {
            CommandGroup(replacing: .newItem) { }
            CommandMenu("Navigate") {
                Button("Sports") { navCoordinator.selectedTab = .feed }
                    .keyboardShortcut("1", modifiers: .command)
                Button("Leagues") { navCoordinator.selectedTab = .leagues }
                    .keyboardShortcut("2", modifiers: .command)
                Button("Search") { navCoordinator.selectedTab = .search }
                    .keyboardShortcut("3", modifiers: .command)
                Button("My Stuff") { navCoordinator.selectedTab = .myStuff }
                    .keyboardShortcut("4", modifiers: .command)
                Divider()
                Button("Quick Search") { navCoordinator.selectedTab = .search }
                    .keyboardShortcut("k", modifiers: .command)
            }
            CommandGroup(after: .help) {
                Button("Report a Bug") {
                    navCoordinator.showBugReport = true
                }
                .keyboardShortcut("b", modifiers: [.command, .shift])
            }
        }
        .onChange(of: navCoordinator.liveGameTitle) { _, title in
            NSApplication.shared.mainWindow?.title = title
        }
        #endif

        #if os(macOS)
        MenuBarExtra {
            MenuBarView()
        } label: {
            HStack(spacing: 3) {
                Image(systemName: "chart.line.uptrend.xyaxis")
                if navCoordinator.liveGameCount > 0 {
                    Text("\(navCoordinator.liveGameCount)")
                        .font(.system(size: 10, weight: .bold).monospacedDigit())
                }
            }
        }
        .menuBarExtraStyle(.window)

        WindowGroup(for: Int.self) { $eventId in
            if let id = eventId {
                NavigationStack {
                    EventDetailView(eventId: id)
                        .environmentObject(authManager)
                        .environmentObject(navCoordinator)
                        .environmentObject(pinManager)
                }
                .preferredColorScheme(.light)
            }
        }
        .defaultSize(width: 900, height: 700)
        #endif
    }

    #if os(macOS)
    @MainActor
    private func pollLiveGames() async {
        while !Task.isCancelled {
            do {
                let feed = try await APIClient.shared.fetchFeed(
                    limit: 10,
                    myTeamsOnly: true,
                    includeFutures: false
                )
                let liveEvents = feed.items
                    .compactMap { $0.event }
                    .filter { $0.status == "live" }

                if let best = liveEvents.first {
                    // #3430 — one matchup, both sides, one line of text.
                    let (away, home) = TeamShortName.shortPair(
                        away: best.awayTeam, home: best.homeTeam
                    )
                    let score = "\(away) \(best.awayScore ?? 0) - \(home) \(best.homeScore ?? 0)"
                    let period = best.espn?.period ?? best.espn?.gameClock ?? ""
                    navCoordinator.liveGameTitle = period.isEmpty ? score : "\(score) • \(period)"
                    navCoordinator.liveGameCount = liveEvents.count
                } else {
                    navCoordinator.liveGameTitle = "Bain Luck"
                    navCoordinator.liveGameCount = 0
                }
            } catch {
                navCoordinator.liveGameTitle = "Bain Luck"
            }
            try? await Task.sleep(nanoseconds: 30_000_000_000) // 30s
        }
    }
    #endif
}
