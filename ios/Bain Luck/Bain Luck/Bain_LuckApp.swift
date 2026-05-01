//
//  Bain_LuckApp.swift
//  Bain Luck
//
//  Created by bain on 2/27/26.
//

import FirebaseCore
import GoogleSignIn
import SwiftUI
#if canImport(UIKit)
import UIKit
#elseif canImport(AppKit)
import AppKit
#endif

@main
struct Bain_LuckApp: App {
    @StateObject private var authManager = AuthManager()
    @StateObject private var navCoordinator = NavigationCoordinator()
    @StateObject private var pinManager = PinManager()

    init() {
        FirebaseApp.configure()
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
                .onChange(of: authManager.isAuthenticated) { _, isAuth in
                    pinManager.isAuthenticated = isAuth
                    Task {
                        if isAuth {
                            await pinManager.syncLocalToServer()
                        }
                        await pinManager.loadPins()
                    }
                }
                .task {
                    pinManager.isAuthenticated = authManager.isAuthenticated
                    await pinManager.loadPins()
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
            }
        }
        #endif

        #if os(macOS)
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
}
