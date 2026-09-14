//
//  AccountDeletionIsReachableAndHonest678Tests.swift
//  BainLuckTests
//
//  #678 — App Store Guideline 5.1.1(v). Apple reviewed version 1.0(7) on an
//  iPad Air 11-inch (M3) on 2026-05-25 and rejected it: account creation
//  exists, "no option to initiate account deletion was found".
//
//  Two separate defects sat behind that sentence, and this file gates both.
//
//  1. REACHABILITY. On iPhone there is no Preferences tab — the five tabs are
//     Discover, Sports, Browse, Search, My Stuff — so the gear in My Stuff's
//     toolbar is the only route to Preferences, and Delete Account lives in
//     Preferences. That gear was gated on
//     `isAuthenticated && onboardingCompleted == true`. A reviewer who creates
//     a new account and does not finish onboarding therefore sees no gear, no
//     Preferences, and no way to delete the account they just made.
//
//  2. HONESTY ON FAILURE. The delete button's catch block reset the spinner
//     and said nothing at all. A failed deletion looked exactly like a tap
//     that did nothing, and the reader was never told their account still
//     exists.
//
//  Both are asserted against real functions rather than by scanning source:
//  a grep for "isAuthenticated" would have passed on the broken version too.
//

import XCTest
@testable import Bain_Luck

final class AccountDeletionIsReachableAndHonest678Tests: XCTestCase {

    // MARK: - 1. The route to deletion exists for every signed-in account

    /// The regression itself. This is the account App Review creates: signed
    /// in seconds ago, onboarding not finished. Before #678 this returned
    /// false and the gear was absent.
    func testSettingsEntryIsOfferedToASignedInAccountThatSkippedOnboarding() {
        XCTAssertTrue(
            MyStuffView.showsSettingsEntry(
                isAuthenticated: true,
                onboardingCompleted: false
            ),
            "A signed-in account that has not finished onboarding must still be able to reach Preferences — on iPhone that gear is the only route to Delete Account."
        )
    }

    func testSettingsEntryIsOfferedToASignedInOnboardedAccount() {
        XCTAssertTrue(
            MyStuffView.showsSettingsEntry(
                isAuthenticated: true,
                onboardingCompleted: true
            )
        )
    }

    /// The other direction, so the fix is "signed in", not "always on":
    /// a signed-out reader has no account to delete and is offered no gear.
    func testSettingsEntryIsWithheldWhenSignedOut() {
        XCTAssertFalse(
            MyStuffView.showsSettingsEntry(
                isAuthenticated: false,
                onboardingCompleted: false
            )
        )
        XCTAssertFalse(
            MyStuffView.showsSettingsEntry(
                isAuthenticated: false,
                onboardingCompleted: true
            ),
            "Onboarding state must not be able to resurrect the entry for a signed-out reader."
        )
    }

    /// Onboarding is irrelevant in BOTH auth states. Stated as its own
    /// assertion because the whole defect was one extra condition here, and a
    /// future edit that re-adds a gate on onboarding fails this.
    func testOnboardingStateNeverChangesTheAnswer() {
        for signedIn in [true, false] {
            XCTAssertEqual(
                MyStuffView.showsSettingsEntry(isAuthenticated: signedIn, onboardingCompleted: true),
                MyStuffView.showsSettingsEntry(isAuthenticated: signedIn, onboardingCompleted: false),
                "Reaching account deletion must not depend on onboarding (isAuthenticated: \(signedIn))."
            )
        }
    }

    // MARK: - 2. A failed deletion says so, and says the account still exists

    /// Every failure message must tell the reader the deletion did NOT happen.
    /// Silence here is what made the old catch block a defect: the reader
    /// could not tell a failure from a success.
    func testEveryFailureMessageIsNonEmptyAndActionable() {
        let failures: [Error] = [
            APIError.httpError(statusCode: 401, body: nil),
            APIError.httpError(statusCode: 403, body: nil),
            APIError.httpError(statusCode: 500, body: nil),
            APIError.httpError(statusCode: 503, body: nil),
            APIError.httpError(statusCode: 404, body: nil),
            APIError.networkError(underlying: URLError(.notConnectedToInternet)),
            APIError.decodingError(underlying: URLError(.cannotParseResponse)),
            APIError.invalidURL,
            NSError(domain: "something.unexpected", code: -1),
        ]

        for failure in failures {
            let message = PreferencesView.deletionFailureMessage(for: failure)
            XCTAssertFalse(
                message.isEmpty,
                "A failure with no words is the bug this fixes: \(failure)"
            )
            XCTAssertTrue(
                message.hasSuffix("."),
                "Message should read as a sentence: \(message)"
            )
        }
    }

    /// An expired session is the one failure the reader can actually fix, so
    /// it gets its own instruction rather than the generic sentence.
    func testExpiredSessionTellsTheReaderToSignInAgain() {
        for code in [401, 403] {
            let message = PreferencesView.deletionFailureMessage(
                for: APIError.httpError(statusCode: code, body: nil)
            )
            XCTAssertTrue(
                message.lowercased().contains("sign"),
                "A \(code) should tell the reader to sign in again, got: \(message)"
            )
        }
    }

    /// A server-side failure must not leave the reader believing their account
    /// is gone when it is not.
    func testServerFailureSaysTheAccountWasNotDeleted() {
        let message = PreferencesView.deletionFailureMessage(
            for: APIError.httpError(statusCode: 500, body: nil)
        )
        XCTAssertTrue(
            message.lowercased().contains("not been deleted"),
            "Got: \(message)"
        )
    }

    func testOfflineFailureNamesTheConnection() {
        let message = PreferencesView.deletionFailureMessage(
            for: APIError.networkError(underlying: URLError(.notConnectedToInternet))
        )
        XCTAssertTrue(
            message.lowercased().contains("connection"),
            "Got: \(message)"
        )
    }

    /// No message may leak a status code, an error domain or a type name at a
    /// reader (D102 — no diagnostic jargon on a reader's screen).
    func testNoFailureMessageLeaksJargon() {
        let failures: [Error] = [
            APIError.httpError(statusCode: 500, body: "Internal Server Error"),
            APIError.decodingError(underlying: URLError(.cannotParseResponse)),
            NSError(domain: "something.unexpected", code: -1),
        ]
        let banned = ["500", "401", "http", "APIError", "NSError", "nil", "Optional", "Error Domain"]

        for failure in failures {
            let message = PreferencesView.deletionFailureMessage(for: failure)
            for token in banned {
                XCTAssertFalse(
                    message.contains(token),
                    "'\(token)' is diagnostic prose, not something a reader should see: \(message)"
                )
            }
        }
    }
}
