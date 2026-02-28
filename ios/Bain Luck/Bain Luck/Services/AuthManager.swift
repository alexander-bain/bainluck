import AuthenticationServices
import Combine
import os
import SwiftUI

private let logger = Logger(subsystem: "com.bainluck", category: "auth")

private let keychainTokenKey = "com.bainluck.sessionToken"
private let keychainAppleUserIdKey = "com.bainluck.appleUserId"

final class AuthManager: ObservableObject {
    @Published var user: AuthUser?
    @Published var isLoading = true
    @Published var error: String?

    private var appleSignInCoordinator: AppleSignInCoordinator?

    var isAuthenticated: Bool { user != nil }

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
            logger.info("Session restored for user \(profile.id)")
        } catch {
            logger.warning("Session restore failed: \(error). Clearing stored token.")
            clearStoredAuth()
        }
        isLoading = false
    }

    // MARK: - Apple Sign-In

    func signInWithApple() {
        let coordinator = AppleSignInCoordinator { [weak self] result in
            Task { @MainActor [weak self] in
                guard let self else { return }
                switch result {
                case .success(let credential):
                    await self.handleAppleCredential(credential)
                case .failure(let error):
                    self.error = "Sign-in failed: \(error.localizedDescription)"
                    logger.error("Apple sign-in error: \(error)")
                }
            }
        }
        self.appleSignInCoordinator = coordinator
        coordinator.performRequest()
    }

    // MARK: - Sign Out

    func signOut() {
        clearStoredAuth()
        user = nil
        error = nil
        logger.info("User signed out")
    }

    // MARK: - Refresh Profile

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
            logger.info("Apple sign-in successful: user \(response.user.id)")
        } catch {
            self.error = "Sign-in failed. Please try again."
            logger.error("Apple sign-in backend call failed: \(error)")
        }
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
            guard let scene = UIApplication.shared.connectedScenes.first as? UIWindowScene,
                  let window = scene.windows.first else {
                return ASPresentationAnchor()
            }
            return window
        }
    }
}
