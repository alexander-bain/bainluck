//
//  Bain_LuckApp.swift
//  Bain Luck
//
//  Created by bain on 2/27/26.
//

import FirebaseCore
import GoogleSignIn
import SwiftUI

@main
struct Bain_LuckApp: App {
    @StateObject private var authManager = AuthManager()
    @StateObject private var navCoordinator = NavigationCoordinator()

    init() {
        FirebaseApp.configure()
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(authManager)
                .environmentObject(navCoordinator)
                .onReceive(NotificationCenter.default.publisher(for: UIScene.didActivateNotification)) { _ in
                    authManager.checkCredentialState()
                }
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
        }
    }
}
