import AuthenticationServices
import GoogleSignIn
import XCTest
@testable import Bain_Luck

/// `#13516` Train 5 measurement event (`auth_sign_in_failed`) — consent-gated,
/// cancel-exclusive, strictly bounded non-PII domain/code/stage fields (#13516#issuecomment-7116042682).
@MainActor
final class AuthSignInFailed13516TelemetryTests: XCTestCase {
    private final class SpySink: TelemetrySink {
        func setAnalyticsCollectionEnabled(_ enabled: Bool) {}
        func setCrashlyticsCollectionEnabled(_ enabled: Bool) {}
        func resetAnalyticsData() {}
    }

    private var captured: [(name: String, params: [String: Any])] = []

    override func setUp() {
        super.setUp()
        captured = []
        TelemetryConsent.shared.resetForTests(sink: SpySink())
        TelemetryConsent.shared.initialize()
        AnalyticsService.eventEmitterForTests = { [weak self] name, params in
            self?.captured.append((name, params ?? [:]))
        }
    }

    override func tearDown() {
        AnalyticsService.eventEmitterForTests = nil
        TelemetryConsent.shared.resetForTests(sink: FirebaseTelemetrySink())
        super.tearDown()
    }

    // 1. Emits auth_sign_in_failed with exact method, stage, error_domain, error_code
    //    (+ optional underlying_*) after "Allow".
    func testEmitsAuthSignInFailedWithExactBoundedFieldsAfterAllow() async {
        TelemetryConsent.shared.set(.analytics)

        let underlying = NSError(
            domain: "com.google.HTTPStatus",
            code: 503,
            userInfo: [NSLocalizedDescriptionKey: "Service unavailable user@example.com"]
        )
        let sdkError = NSError(
            domain: GIDSignInError.errorDomain,
            code: -2,
            userInfo: [
                NSUnderlyingErrorKey: underlying,
                NSURLErrorFailingURLStringErrorKey: "https://accounts.google.com/o/oauth2/auth?token=secret",
            ]
        )

        let auth = AuthManager(restoreOnInit: false)
        await auth.performGoogleSignInFlow(
            checkNetwork: { true },
            clientIDProvider: { "client-id.apps.googleusercontent.com" },
            configureClient: { _ in },
            presentGoogleSignIn: { throw sdkError },
            exchangeToken: { _ in fatalError("should not exchange after SDK failure") },
            saveSessionToken: { _ in true },
            bindAuthTokenProvider: {},
            onSuccessAnalytics: { _ in }
        )

        let failedEvents = captured.filter { $0.name == "auth_sign_in_failed" }
        XCTAssertEqual(failedEvents.count, 1)
        let p = failedEvents[0].params
        XCTAssertEqual(p["method"] as? String, "google")
        XCTAssertEqual(p["stage"] as? String, AuthManager.AuthFailureStage.googleSDK.rawValue)
        XCTAssertEqual(p["error_domain"] as? String, GIDSignInError.errorDomain)
        XCTAssertEqual(p["error_code"] as? Int, -2)
        XCTAssertEqual(p["underlying_domain"] as? String, "com.google.HTTPStatus")
        XCTAssertEqual(p["underlying_code"] as? Int, 503)

        // ASAuthorizationErrorDomain (26 dot-free chars) must pass intact, not become "[token]".
        captured.removeAll()
        let appleError = NSError(
            domain: ASAuthorizationError.errorDomain,
            code: ASAuthorizationError.failed.rawValue,
            userInfo: nil
        )
        AuthManager.handleAppleSDKFailureTelemetry(appleError)
        XCTAssertEqual(captured.count, 1)
        XCTAssertEqual(captured[0].params["method"] as? String, "apple")
        XCTAssertEqual(captured[0].params["stage"] as? String, AuthManager.AuthFailureStage.appleSDK.rawValue)
        XCTAssertEqual(captured[0].params["error_domain"] as? String, ASAuthorizationError.errorDomain)
        XCTAssertEqual(captured[0].params["error_code"] as? Int, ASAuthorizationError.failed.rawValue)
    }

    // 2. Emits nothing when consent is unknown, declined, or revoked.
    func testEmitsNothingWhenConsentUnknownDeclinedOrRevoked() async {
        let auth = AuthManager(restoreOnInit: false)
        let runFailure: () async -> Void = {
            await auth.performGoogleSignInFlow(
                checkNetwork: { false },
                clientIDProvider: { nil },
                configureClient: { _ in },
                presentGoogleSignIn: { nil },
                exchangeToken: { _ in fatalError("unused") },
                saveSessionToken: { _ in false },
                bindAuthTokenProvider: {},
                onSuccessAnalytics: { _ in }
            )
        }

        // Unknown (`nil`)
        XCTAssertFalse(TelemetryConsent.shared.isGranted)
        await runFailure()
        XCTAssertTrue(captured.isEmpty, "must emit nothing while consent is unknown")

        // Declined (`.none`)
        TelemetryConsent.shared.set(.none)
        await runFailure()
        XCTAssertTrue(captured.isEmpty, "must emit nothing when consent is declined")

        // Granted then revoked
        TelemetryConsent.shared.set(.analytics)
        TelemetryConsent.shared.set(.none)
        await runFailure()
        XCTAssertTrue(captured.isEmpty, "must emit nothing after consent revocation")
    }

    // 3. Drops/scrubs descriptions, URLs, emails, and tokens, and collapses invalid domains to "other".
    func testDropsHardDropKeysPIIAndInvalidErrorDomainsFailClosed() {
        let sanitized = AnalyticsPrivacy.sanitize(
            event: "auth_sign_in_failed",
            parameters: [
                "method": "google",
                "stage": "backend_exchange",
                "error_domain": "https://bainluck.com/user@example.com?token=abc1234567890",
                "error_code": 401,
                "underlying_domain": "secretTokenHeaderValue12345",
                "underlying_code": 401,
                "error_description": "Invalid credentials for user@example.com",
                "description": "raw failure detail",
                "message": "Bearer eyJhbGciOiJIUzI1NiJ9",
                "detail": "stack trace",
                "localized_description": "localized reason",
                "debug_description": "debug reason",
                "NSURLErrorFailingURLStringErrorKey": "https://api.bainluck.com/api/auth/google",
                "email": "user@example.com",
                "token": "eyJhbGciOiJIUzI1NiJ9",
                "user_id": "999",
            ]
        )

        let p = try! XCTUnwrap(sanitized)
        XCTAssertEqual(
            Set(p.keys),
            ["method", "stage", "error_domain", "error_code", "underlying_domain", "underlying_code"]
        )
        XCTAssertEqual(p["error_domain"] as? String, "other")
        XCTAssertEqual(p["underlying_domain"] as? String, "other")
        for key in [
            "error_description", "description", "message", "detail",
            "localized_description", "debug_description",
            "NSURLErrorFailingURLStringErrorKey", "email", "token", "user_id",
        ] {
            XCTAssertNil(p[key], "hard-drop / unapproved key \(key) must be stripped")
        }
    }

    // 4. User cancellation (GIDSignInError.canceled / ASAuthorizationError.canceled) emits nothing.
    func testUserCancellationEmitsNothing() async {
        TelemetryConsent.shared.set(.analytics)

        let gidCanceled = NSError(
            domain: GIDSignInError.errorDomain,
            code: GIDSignInError.canceled.rawValue,
            userInfo: nil
        )
        let auth = AuthManager(restoreOnInit: false)
        await auth.performGoogleSignInFlow(
            checkNetwork: { true },
            clientIDProvider: { "client-id.apps.googleusercontent.com" },
            configureClient: { _ in },
            presentGoogleSignIn: { throw gidCanceled },
            exchangeToken: { _ in fatalError("unused") },
            saveSessionToken: { _ in true },
            bindAuthTokenProvider: {},
            onSuccessAnalytics: { _ in }
        )

        AuthManager.handleAppleSDKFailureTelemetry(ASAuthorizationError(.canceled))
        XCTAssertTrue(captured.isEmpty, "user cancellations must never emit auth_sign_in_failed")
    }
}
