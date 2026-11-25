import XCTest
@testable import Bain_Luck

@MainActor
final class GoogleFirstSignIn13516Tests: XCTestCase {

    private func sampleAuthResponse(userId: Int = 9001, token: String = "session-jwt-13516") -> AppleAuthResponse {
        AppleAuthResponse(
            customToken: nil,
            idToken: token,
            uid: "uid-\(userId)",
            email: "reader@example.com",
            name: "Reader",
            picture: nil,
            expiresIn: 28800,
            user: AuthUser(
                id: userId,
                email: "reader@example.com",
                displayName: "Reader",
                photoUrl: nil,
                onboardingCompleted: true,
                createdAt: nil
            )
        )
    }

    func testPrepareGoogleSignInPurgesOnceOnCleanInstallAndSkipsWhenSessionExists() {
        let suiteName = "GoogleFirstSignIn13516Tests.Clean.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defer { defaults.removePersistentDomain(forName: suiteName) }

        var configuredClients: [String] = []
        var purgeCalls = 0

        AuthManager.prepareGoogleSignIn(
            defaults: defaults,
            hasStoredSession: { false },
            clientIDProvider: { "client-13516" },
            configureClient: { configuredClients.append($0) },
            purgeGoogleKeychain: { purgeCalls += 1 }
        )

        XCTAssertEqual(configuredClients, ["client-13516"])
        XCTAssertEqual(purgeCalls, 1)

        // Second launch must configure client again without wiping fresh Google Keychain state.
        AuthManager.prepareGoogleSignIn(
            defaults: defaults,
            hasStoredSession: { false },
            clientIDProvider: { "client-13516" },
            configureClient: { configuredClients.append($0) },
            purgeGoogleKeychain: { purgeCalls += 1 }
        )

        XCTAssertEqual(configuredClients, ["client-13516", "client-13516"])
        XCTAssertEqual(purgeCalls, 1)

        // An upgrade with an existing session must not purge its Google Keychain state.
        let upgradeSuite = "GoogleFirstSignIn13516Tests.Upgrade.\(UUID().uuidString)"
        let upgradeDefaults = UserDefaults(suiteName: upgradeSuite)!
        defer { upgradeDefaults.removePersistentDomain(forName: upgradeSuite) }
        var upgradePurges = 0
        AuthManager.prepareGoogleSignIn(
            defaults: upgradeDefaults,
            hasStoredSession: { true },
            clientIDProvider: { "client-13516" },
            configureClient: { _ in },
            purgeGoogleKeychain: { upgradePurges += 1 }
        )
        XCTAssertEqual(upgradePurges, 0)
        XCTAssertTrue(upgradeDefaults.bool(forKey: AuthManager.googleFreshInstallPurgedDefaultsKey))
    }

    func testFirstGoogleSignInAfterCleanInstallSucceeds() async {
        let auth = AuthManager(restoreOnInit: false)
        var configured: String?
        var savedToken: Data?
        var boundProvider = false
        var analyticsUserId: Int?
        var foregroundRetryTriggered = true

        await auth.performGoogleSignInFlow(
            checkNetwork: { true },
            clientIDProvider: { "client-13516" },
            configureClient: { configured = $0 },
            presentGoogleSignIn: {
                // Foreground UIScene activation while Google sheet returns must not start restore.
                foregroundRetryTriggered = auth.retrySessionIfNeeded(
                    hasStoredToken: { true },
                    startRestore: { XCTFail("restore must not race an in-flight sign-in") }
                )
                return AuthManager.GoogleSignInTokenPayload(accessToken: "google-access-token")
            },
            exchangeToken: { token in
                XCTAssertEqual(token, "google-access-token")
                return self.sampleAuthResponse(userId: 4242)
            },
            saveSessionToken: { data in
                savedToken = data
                return true
            },
            bindAuthTokenProvider: {
                boundProvider = true
            },
            onSuccessAnalytics: { userId in
                analyticsUserId = userId
            }
        )

        XCTAssertEqual(configured, "client-13516")
        XCTAssertFalse(foregroundRetryTriggered)
        XCTAssertEqual(savedToken, "session-jwt-13516".data(using: .utf8))
        XCTAssertTrue(boundProvider)
        XCTAssertEqual(auth.user?.id, 4242)
        XCTAssertTrue(auth.isAuthenticated)
        XCTAssertNil(auth.error)
        XCTAssertNil(auth.lastAuthErrorDiagnostic)
        XCTAssertFalse(auth.isSigningIn)
        XCTAssertEqual(analyticsUserId, 4242)
    }

    func testReentrancyGuardRejectsSecondSignInWhileInFlight() async {
        let auth = AuthManager(restoreOnInit: false)
        var presentCalls = 0

        await auth.performGoogleSignInFlow(
            checkNetwork: { true },
            clientIDProvider: { "client-13516" },
            configureClient: { _ in },
            presentGoogleSignIn: {
                presentCalls += 1
                // Second tap arrives before the first attempt completes.
                await auth.performGoogleSignInFlow(
                    checkNetwork: { true },
                    clientIDProvider: { "client-13516" },
                    configureClient: { _ in },
                    presentGoogleSignIn: {
                        presentCalls += 1
                        return AuthManager.GoogleSignInTokenPayload(accessToken: "second")
                    },
                    exchangeToken: { _ in self.sampleAuthResponse() },
                    saveSessionToken: { _ in true },
                    bindAuthTokenProvider: {},
                    onSuccessAnalytics: { _ in }
                )
                return AuthManager.GoogleSignInTokenPayload(accessToken: "first")
            },
            exchangeToken: { _ in self.sampleAuthResponse() },
            saveSessionToken: { _ in true },
            bindAuthTokenProvider: {},
            onSuccessAnalytics: { _ in }
        )

        XCTAssertEqual(presentCalls, 1)
        XCTAssertFalse(auth.isSigningIn)
    }

    func testUnderlyingErrorDiagnosticsCancelDomainAndErrorMapping() async {
        let googleCancel = NSError(domain: AuthManager.googleSignInErrorDomain, code: -5)
        XCTAssertTrue(AuthManager.isGoogleSignInCanceled(googleCancel))

        // AppAuth OIDErrorCodeServerError is also code -5 in a different domain and must NOT be silenced.
        let appAuthServerError = NSError(
            domain: "org.openid.appauth.general",
            code: -5,
            userInfo: [NSLocalizedDescriptionKey: "Token exchange failed"]
        )
        XCTAssertFalse(AuthManager.isGoogleSignInCanceled(appAuthServerError))

        // AppAuth OIDErrorCodeNetworkError wrapping URLError(.timedOut) must map to timeout message, not generic fallback.
        let urlTimeout = NSError(domain: NSURLErrorDomain, code: NSURLErrorTimedOut, userInfo: [NSLocalizedDescriptionKey: "The request timed out."])
        let oidNetworkError = NSError(
            domain: "org.openid.appauth.general",
            code: -3,
            userInfo: [
                NSLocalizedDescriptionKey: "Connection error making token request",
                NSUnderlyingErrorKey: urlTimeout,
            ]
        )
        XCTAssertEqual(AuthManager.userFacingAuthError(oidNetworkError), "Connection timed out. Check your network and try again.")
        let networkDiag = AuthManager.describeErrorForLog(oidNetworkError, stage: .googleSDK)
        XCTAssertTrue(networkDiag.contains("stage=google_sdk"))
        XCTAssertTrue(networkDiag.contains("org.openid.appauth.general"))
        XCTAssertTrue(networkDiag.contains("underlying=\(NSURLErrorDomain)(\(NSURLErrorTimedOut))"))

        // Non-network SDK errors (e.g. GIDSignIn keychain error -2) retain fallback copy and populate diagnostic.
        let auth = AuthManager(restoreOnInit: false)
        let keychainErr = NSError(
            domain: AuthManager.googleSignInErrorDomain,
            code: -2,
            userInfo: [NSLocalizedDescriptionKey: "keychain error"]
        )
        await auth.performGoogleSignInFlow(
            checkNetwork: { true },
            clientIDProvider: { "client-13516" },
            configureClient: { _ in },
            presentGoogleSignIn: { throw keychainErr },
            exchangeToken: { _ in
                XCTFail("backend must not be called when Google SDK throws")
                return self.sampleAuthResponse()
            },
            saveSessionToken: { _ in true },
            bindAuthTokenProvider: {},
            onSuccessAnalytics: { _ in }
        )

        XCTAssertEqual(auth.error, "Sign-in failed. Please try again.")
        XCTAssertNotNil(auth.lastAuthErrorDiagnostic)
        XCTAssertTrue(auth.lastAuthErrorDiagnostic?.contains("code=-2") == true)
        XCTAssertFalse(auth.isSigningIn)
    }

    func testTransientBackendNetworkErrorRetriesOnceAndSucceeds() async {
        let auth = AuthManager(restoreOnInit: false)
        var presentCalls = 0
        var exchangeCalls = 0
        var sleptNs: [UInt64] = []

        await auth.performGoogleSignInFlow(
            checkNetwork: { true },
            clientIDProvider: { "client-13516" },
            configureClient: { _ in },
            presentGoogleSignIn: {
                presentCalls += 1
                return AuthManager.GoogleSignInTokenPayload(accessToken: "token-once")
            },
            exchangeToken: { _ in
                exchangeCalls += 1
                if exchangeCalls == 1 {
                    throw APIError.networkError(underlying: URLError(.networkConnectionLost))
                }
                return self.sampleAuthResponse(userId: 7777)
            },
            saveSessionToken: { _ in true },
            bindAuthTokenProvider: {},
            sleepNanoseconds: { sleptNs.append($0) },
            onSuccessAnalytics: { _ in }
        )

        XCTAssertEqual(presentCalls, 1)
        XCTAssertEqual(exchangeCalls, 2)
        XCTAssertEqual(sleptNs, [300_000_000])
        XCTAssertEqual(auth.user?.id, 7777)
        XCTAssertNil(auth.error)
        XCTAssertNil(auth.lastAuthErrorDiagnostic)
    }
}
