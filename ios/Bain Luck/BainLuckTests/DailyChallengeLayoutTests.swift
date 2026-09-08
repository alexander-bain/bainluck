import XCTest
@testable import Bain_Luck

/// #3865 — the Daily Challenge question was an iPhone layout with its container
/// widened. These pin the two ways a fix for that goes wrong.
final class DailyChallengeLayoutTests: XCTestCase {

    // Device widths in points.
    private let iPhoneSE: CGFloat = 375
    private let iPhone16: CGFloat = 393
    private let iPhone17: CGFloat = 402
    private let iPhoneMax: CGFloat = 430
    private let iPadPro11: CGFloat = 834
    private let iPadPro13: CGFloat = 1024

    // MARK: - The cap must not narrow the phone

    /// The first way this fix goes wrong: capping the column at a number that
    /// also bites on a phone, so the iPad is repaired by making every iPhone
    /// worse. Every phone must come back untouched.
    func testTheCapNeverNarrowsAnyIPhone() {
        for width in [iPhoneSE, iPhone16, iPhone17, iPhoneMax] {
            XCTAssertEqual(
                DailyChallengeLayout.contentWidth(inViewportWidth: width),
                width,
                "the \(Int(width))pt phone must draw its full width, not a capped column"
            )
        }
    }

    /// Measured off `artifacts-native-064/BEFORE-3865-daily-phone-f813a705.png`:
    /// each button spanned 176pt (a raster scan of the saturated fill, so ~1pt
    /// under the true capsule width once the antialiased ends are counted).
    /// The phone's buttons must be exactly as wide after the fix as before it.
    func testThePhoneAnswerButtonsAreUnchangedByTheFix() {
        let measuredBeforeTheFix: CGFloat = 176
        let after = DailyChallengeLayout.answerButtonWidth(inViewportWidth: iPhone17)
        XCTAssertEqual(after, 177, accuracy: 0.01)
        XCTAssertEqual(
            after, measuredBeforeTheFix, accuracy: 1.5,
            "the iPhone 17 button was 176pt on the BEFORE frame and must stay there"
        )
    }

    // MARK: - The cap must actually bite on the iPad it was filed against

    /// The second way this fix goes wrong, and the more likely one: reaching
    /// for the constant the house already has. `PoliticsView`, `WeatherView`,
    /// `EconomicsView` and `EntertainmentView` all cap regular width at 900pt.
    /// The iPad in this issue is 834pt wide, so 900 never binds — the change
    /// would compile, review cleanly, and ship a screen identical to the one
    /// photographed in the bug report.
    func testTheHouse900ptDashboardCapWouldBeInertOnThisIPad() {
        let houseDashboardCap: CGFloat = 900
        XCTAssertGreaterThan(
            houseDashboardCap, iPadPro11,
            "premise of this test: 900 does not bind at 834pt"
        )
        XCTAssertLessThan(
            DailyChallengeLayout.maxContentWidth, iPadPro11,
            "the cap must be narrower than the 834pt iPad this issue was filed "
            + "against, or the fix is a no-op on the exact screen it is for"
        )
    }

    func testTheIPadColumnIsCapped() {
        for width in [iPadPro11, iPadPro13] {
            let column = DailyChallengeLayout.contentWidth(inViewportWidth: width)
            XCTAssertEqual(column, DailyChallengeLayout.maxContentWidth)
            XCTAssertLessThan(column, width)
        }
    }

    /// The user-visible claim, stated as arithmetic: a one-bit answer stops
    /// being offered on a tap target the size of a whole phone. Measured at
    /// 392pt per button on the BEFORE iPad frame, against a 402pt iPhone 17.
    func testTheIPadAnswerButtonIsNoLongerAsWideAsAnEntirePhone() {
        let measuredBeforeTheFix: CGFloat = 392
        XCTAssertEqual(
            measuredBeforeTheFix, (iPadPro11 - 32 - 16) / 2, accuracy: 1.5,
            "premise: 392pt is what an uncapped 834pt page produces"
        )
        let after = DailyChallengeLayout.answerButtonWidth(inViewportWidth: iPadPro11)
        XCTAssertEqual(after, 256, accuracy: 0.01)
        XCTAssertLessThan(
            after, iPhone17,
            "an answer button must be narrower than an iPhone 17 is wide"
        )
        XCTAssertLessThan(after, measuredBeforeTheFix)
    }

    // MARK: - Degenerate widths

    /// A viewport narrower than the padding must not produce a negative button.
    func testAbsurdlyNarrowViewportsClampAtZero() {
        for width in [CGFloat(0), 8, 32, 40] {
            XCTAssertGreaterThanOrEqual(
                DailyChallengeLayout.answerButtonWidth(inViewportWidth: width), 0,
                "a \(Int(width))pt viewport must not yield a negative button width"
            )
        }
    }
}
