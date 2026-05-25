import AuthenticationServices
import Combine
import GoogleSignIn
import Network
import os
import SwiftUI
#if canImport(UIKit)
import UIKit
#elseif canImport(AppKit)
import AppKit
#endif

private let logger = Logger(subsystem: "com.bainluck", category: "auth")

private let keychainTokenKey = "com.bainluck.sessionToken"
private let keychainAppleUserIdKey = "com.bainluck.appleUserId"

/// Owns the app's authenticated session state and exchanges provider
/// credentials for Bain Luck backend session tokens stored in Keychain.
@MainActor
final class AuthManager: ObservableObject {
    /// The signed-in Bain Luck profile, or nil when the app is anonymous.
    @Published var user: AuthUser?
    /// True while launch-time Keychain restore or token validation is running.
    @Published var isLoading = true
    /// Last user-facing sign-in error for auth screens to present.
    @Published var error: String?

    private var appleSignInCoordinator: AppleSignInCoordinator?

    /// True when a backend session has been restored or established.
    var isAuthenticated: Bool { user != nil }

    /// Admin email addresses that unlock internal-only features in the app.
    /// Mirrors ``DEFAULT_ADMIN_EMAILS`` in ``backend/app/routes/admin_utils.py``.
    private static let adminEmails: Set<String> = [
        "alex.bain@gmail.com",
        "alex.bain@bainluck.com",
        "olivercbain@gmail.com",
    ]

    /// True when the signed-in user's email matches a known admin address.
    var isAdmin: Bool {
        guard let email = user?.email?.lowercased() else { return false }
        return Self.adminEmails.contains(email)
    }

    init() {
        Task {
            await restoreSession()
        }
    }

    // MARK: - Session Restore

    private func restoreSession() async {
        guard let tokenData = KeychainHelper.load(key: keychainTokenKey),
              String(data: tokenData, encoding: .utf8) != nil else {
            isLoading = false
            return
        }

        // Wire token to APIClient before verifying
        await APIClient.shared.setAuthTokenProvider {
            KeychainHelper.load(key: keychainTokenKey).flatMap { String(data: $0, encoding: .utf8) }
        }

        do {
            let profile: AuthUser = try await APIClient.shared.fetchProfile()
            self.user = profile
            AnalyticsService.setUserId(String(profile.id))
            AnalyticsService.setUserProperty("logged_in", forName: "login_status")
            logger.info("Session restored for user \(profile.id)")
        } catch let apiError as APIError {
            switch apiError {
            case .httpError(let statusCode, _) where statusCode == 401 || statusCode == 403:
                // Token is invalid/expired — try silent Google re-auth before giving up
                logger.warning("Session token rejected (\(statusCode)). Attempting silent Google restore.")
                let silentRestored = await attemptSilentGoogleRestore()
                if !silentRestored {
                    clearStoredAuth()
                }
            default:
                // Network error, timeout, decoding — keep token and stay signed out temporarily
                logger.warning("Session restore failed (transient): \(apiError.errorDescription ?? "unknown"). Keeping stored token.")
            }
        } catch {
            // Non-API errors — keep token for retry on next launch
            logger.warning("Session restore failed (unknown): \(error). Keeping stored token.")
        }
        isLoading = false
    }

    // MARK: - Apple Sign-In

    /// Starts native Apple Sign-In and exchanges the Apple identity token with
    /// the backend for a Bain Luck session token.
    func signInWithApple() {
        Task {
            guard await checkNetworkAvailable() else {
                self.error = "No internet connection. Connect to Wi-Fi or cellular and try again."
                return
            }

            #if os(iOS)
            guard Self.findRootViewController() != nil else {
                self.error = "Cannot present sign-in. Please try again."
                return
            }
            #endif

            let coordinator = AppleSignInCoordinator { [weak self] result in
                Task { @MainActor [weak self] in
                    guard let self else { return }
                    switch result {
                    case .success(let credential):
                        await self.handleAppleCredential(credential)
                    case .failure(let error):
                        self.error = Self.userFacingAuthError(error)
                        logger.error("Apple sign-in error: \(error)")
                    }
                }
            }
            self.appleSignInCoordinator = coordinator
            coordinator.performRequest()
        }
    }

    // MARK: - Google Sign-In

    /// Starts Google Sign-In and exchanges the Google access token with the
    /// backend for a Bain Luck session token.
    func signInWithGoogle() {
        Task {
            await handleGoogleSignIn()
        }
    }

    // MARK: - Delete Account

    /// Deletes the user's account on the backend, then clears all local state.
    func deleteAccount() async throws {
        let _: [String: String] = try await APIClient.shared.deleteAccount()
        signOut()
        logger.info("Account deleted and signed out")
    }

    // MARK: - Sign Out

    /// Clears local session state, provider state, and analytics identity.
    func signOut() {
        clearStoredAuth()
        GIDSignIn.sharedInstance.signOut()
        user = nil
        error = nil
        AnalyticsService.trackLogout()
        AnalyticsService.setUserId(nil)
        AnalyticsService.setUserProperty("anonymous", forName: "login_status")
        logger.info("User signed out")
    }

    // MARK: - Foreground Retry

    /// Call when app returns to foreground. If a stored token exists but user is nil
    /// (e.g., network failed on initial launch), retry session restore.
    func retrySessionIfNeeded() {
        guard !isAuthenticated,
              KeychainHelper.load(key: keychainTokenKey) != nil else { return }
        Task {
            await restoreSession()
        }
    }

    // MARK: - Refresh Profile

    /// Reloads the current backend profile without changing stored credentials.
    func refreshProfile() async {
        guard isAuthenticated else { return }
        do {
            let profile: AuthUser = try await APIClient.shared.fetchProfile()
            self.user = profile
        } catch {
            logger.error("Profile refresh failed: \(error)")
        }
    }

    // MARK: - Credential State Check

    /// Checks whether the stored Apple credential was revoked and signs out if
    /// Apple no longer considers it valid.
    func checkCredentialState() {
        guard let appleUserIdData = KeychainHelper.load(key: keychainAppleUserIdKey),
              let appleUserId = String(data: appleUserIdData, encoding: .utf8) else {
            return
        }

        let signOut = { @MainActor [weak self] in
            self?.signOut()
            logger.info("Apple credential revoked — signed out")
        }

        ASAuthorizationAppleIDProvider().getCredentialState(forUserID: appleUserId) { state, _ in
            if state == .revoked {
                Task { @MainActor in
                    signOut()
                }
            }
        }
    }

    // MARK: - Private Helpers

    /// Try to silently restore Google Sign-In and re-exchange for a fresh session token.
    /// Returns true if successful (user is now authenticated).
    private func attemptSilentGoogleRestore() async -> Bool {
        do {
            let result = try await GIDSignIn.sharedInstance.restorePreviousSignIn()
            let accessToken = result.accessToken.tokenString

            let response = try await APIClient.shared.signInWithGoogle(accessToken: accessToken)

            guard let tokenData = response.idToken.data(using: .utf8) else {
                return false
            }
            _ = KeychainHelper.save(key: keychainTokenKey, data: tokenData)

            await APIClient.shared.setAuthTokenProvider {
                KeychainHelper.load(key: keychainTokenKey).flatMap { String(data: $0, encoding: .utf8) }
            }

            self.user = response.user
            self.error = nil
            AnalyticsService.setUserId(String(response.user.id))
            AnalyticsService.setUserProperty("logged_in", forName: "login_status")
            logger.info("Silent Google restore successful: user \(response.user.id)")
            return true
        } catch {
            logger.info("Silent Google restore failed: \(error)")
            return false
        }
    }

    private func checkNetworkAvailable() async -> Bool {
        await withCheckedContinuation { continuation in
            let monitor = NWPathMonitor()
            let queue = DispatchQueue(label: "com.bainluck.auth-network-check")
            monitor.pathUpdateHandler = { path in
                monitor.cancel()
                continuation.resume(returning: path.status == .satisfied)
            }
            monitor.start(queue: queue)
        }
    }

    private func clearStoredAuth() {
        KeychainHelper.delete(key: keychainTokenKey)
        KeychainHelper.delete(key: keychainAppleUserIdKey)
        Task {
            await APIClient.shared.setAuthTokenProvider(nil)
        }
    }

    private func handleAppleCredential(_ credential: ASAuthorizationAppleIDCredential) async {
        guard let identityTokenData = credential.identityToken,
              let identityToken = String(data: identityTokenData, encoding: .utf8) else {
            error = "Apple Sign-In failed: no identity token"
            logger.error("No identity token in Apple credential")
            return
        }

        let firstName = credential.fullName?.givenName
        let lastName = credential.fullName?.familyName

        if let userIdData = credential.user.data(using: .utf8) {
            _ = KeychainHelper.save(key: keychainAppleUserIdKey, data: userIdData)
        }

        do {
            let response = try await APIClient.shared.signInWithApple(
                idToken: identityToken,
                firstName: firstName,
                lastName: lastName
            )

            guard let tokenData = response.idToken.data(using: .utf8) else {
                error = "Failed to encode session token"
                return
            }
            _ = KeychainHelper.save(key: keychainTokenKey, data: tokenData)

            await APIClient.shared.setAuthTokenProvider {
                KeychainHelper.load(key: keychainTokenKey).flatMap { String(data: $0, encoding: .utf8) }
            }

            self.user = response.user
            self.error = nil
            AnalyticsService.trackLogin(method: "apple")
            AnalyticsService.setUserId(String(response.user.id))
            AnalyticsService.setUserProperty("logged_in", forName: "login_status")
            logger.info("Apple sign-in successful: user \(response.user.id)")
        } catch {
            self.error = Self.userFacingAuthError(error)
            logger.error("Apple sign-in backend call failed: \(error)")
        }
    }

    private func handleGoogleSignIn() async {
        guard await checkNetworkAvailable() else {
            error = "No internet connection. Connect to Wi-Fi or cellular and try again."
            return
        }

        guard let clientID = googleClientID() else {
            error = "Google Sign-In not configured"
            logger.error("GoogleService-Info.plist missing or has no CLIENT_ID")
            return
        }

        GIDSignIn.sharedInstance.configuration = GIDConfiguration(clientID: clientID)

        do {
            #if os(iOS)
            guard let rootViewController = Self.findRootViewController() else {
                error = "Cannot present sign-in"
                logger.error("No root view controller found for Google sign-in")
                return
            }
            let result = try await GIDSignIn.sharedInstance.signIn(withPresenting: rootViewController)
            #elseif os(macOS)
            guard let window = NSApplication.shared.keyWindow else {
                error = "Cannot present sign-in"
                return
            }
            let result = try await GIDSignIn.sharedInstance.signIn(withPresenting: window)
            #endif
            let accessToken = result.user.accessToken.tokenString

            let response = try await APIClient.shared.signInWithGoogle(accessToken: accessToken)

            guard let tokenData = response.idToken.data(using: .utf8) else {
                error = "Failed to encode session token"
                return
            }
            _ = KeychainHelper.save(key: keychainTokenKey, data: tokenData)

            await APIClient.shared.setAuthTokenProvider {
                KeychainHelper.load(key: keychainTokenKey).flatMap { String(data: $0, encoding: .utf8) }
            }

            self.user = response.user
            self.error = nil
            AnalyticsService.trackLogin(method: "google")
            AnalyticsService.setUserId(String(response.user.id))
            AnalyticsService.setUserProperty("logged_in", forName: "login_status")
            logger.info("Google sign-in successful: user \(response.user.id)")
        } catch {
            if (error as NSError).code == -5 {
                return
            }
            self.error = Self.userFacingAuthError(error)
            logger.error("Google sign-in error: \(error)")
        }
    }

    private func googleClientID() -> String? {
        guard let path = Bundle.main.path(forResource: "GoogleService-Info", ofType: "plist"),
              let dict = NSDictionary(contentsOfFile: path),
              let clientID = dict["CLIENT_ID"] as? String else {
            return nil
        }
        return clientID
    }

    // MARK: - Shared Helpers

    #if os(iOS)
    /// Returns the foreground scene's root view controller for native auth UI
    /// presentation, preferring the key window under iPad multi-window modes.
    @MainActor
    static func findRootViewController() -> UIViewController? {
        let scene = UIApplication.shared.connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .first(where: { $0.activationState == .foregroundActive })
            ?? UIApplication.shared.connectedScenes
                .compactMap { $0 as? UIWindowScene }
                .first
        return scene?.windows.first(where: { $0.isKeyWindow })?.rootViewController
            ?? scene?.windows.first?.rootViewController
    }
    #endif

    /// Maps low-level auth and API failures to short messages safe for display.
    static func userFacingAuthError(_ error: Error) -> String {
        if let apiError = error as? APIError {
            switch apiError {
            case .networkError:
                return "Connection failed. Check your network and try again."
            case .httpError(let code, _) where code >= 500:
                return "Server error (\(code)). Please try again."
            case .httpError(let code, _):
                return "Sign-in rejected (\(code)). Please try again."
            case .decodingError:
                return "Unexpected server response. Please try again."
            case .invalidURL:
                return "Sign-in failed. Please try again."
            }
        }
        let nsError = error as NSError
        if nsError.domain == NSURLErrorDomain {
            switch nsError.code {
            case NSURLErrorNotConnectedToInternet, NSURLErrorNetworkConnectionLost:
                return "No internet connection. Connect to Wi-Fi or cellular and try again."
            case NSURLErrorTimedOut:
                return "Connection timed out. Check your network and try again."
            case NSURLErrorCannotFindHost, NSURLErrorCannotConnectToHost, NSURLErrorDNSLookupFailed:
                return "Cannot reach sign-in servers. Check your network and try again."
            default:
                break
            }
        }

        return "Sign-in failed. Please try again."
    }
}

// MARK: - Apple Sign-In Coordinator

/// Bridges ASAuthorization delegate callbacks to a closure, avoiding NSObject
/// inheritance on AuthManager (which conflicts with @MainActor + ObservableObject).
private class AppleSignInCoordinator: NSObject, ASAuthorizationControllerDelegate, ASAuthorizationControllerPresentationContextProviding {
    private let completion: @Sendable (Result<ASAuthorizationAppleIDCredential, Error>) -> Void

    init(completion: @escaping @Sendable (Result<ASAuthorizationAppleIDCredential, Error>) -> Void) {
        self.completion = completion
    }

    func performRequest() {
        let provider = ASAuthorizationAppleIDProvider()
        let request = provider.createRequest()
        request.requestedScopes = [.email, .fullName]

        let controller = ASAuthorizationController(authorizationRequests: [request])
        controller.delegate = self
        controller.presentationContextProvider = self
        controller.performRequests()
    }

    func authorizationController(controller: ASAuthorizationController, didCompleteWithAuthorization authorization: ASAuthorization) {
        guard let credential = authorization.credential as? ASAuthorizationAppleIDCredential else { return }
        completion(.success(credential))
    }

    func authorizationController(controller: ASAuthorizationController, didCompleteWithError error: Error) {
        if let authError = error as? ASAuthorizationError, authError.code == .canceled {
            return
        }
        completion(.failure(error))
    }

    func presentationAnchor(for controller: ASAuthorizationController) -> ASPresentationAnchor {
        MainActor.assumeIsolated {
            #if os(iOS)
            let scene = UIApplication.shared.connectedScenes
                .compactMap { $0 as? UIWindowScene }
                .first(where: { $0.activationState == .foregroundActive })
                ?? UIApplication.shared.connectedScenes
                    .compactMap { $0 as? UIWindowScene }
                    .first
            return scene?.windows.first(where: { $0.isKeyWindow })
                ?? scene?.windows.first
                ?? ASPresentationAnchor()
            #elseif os(macOS)
            return NSApplication.shared.keyWindow ?? NSWindow()
            #endif
        }
    }
}
