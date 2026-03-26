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
    @StateObject private var pinManager = PinManager()

    init() {
        FirebaseApp.configure()
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
                .onReceive(NotificationCenter.default.publisher(for: UIScene.didActivateNotification)) { _ in
                    authManager.checkCredentialState()
                    authManager.retrySessionIfNeeded()
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
