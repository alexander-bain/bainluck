//
//  Bain_LuckApp.swift
//  Bain Luck
//
//  Created by bain on 2/27/26.
//

import GoogleSignIn
import SwiftUI

@main
struct Bain_LuckApp: App {
    @StateObject private var authManager = AuthManager()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(authManager)
                .onReceive(NotificationCenter.default.publisher(for: UIScene.didActivateNotification)) { _ in
                    authManager.checkCredentialState()
                }
                .onOpenURL { url in
                    GIDSignIn.sharedInstance.handle(url)
                }
        }
    }
}
