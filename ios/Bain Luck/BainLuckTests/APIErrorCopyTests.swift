import XCTest
@testable import Bain_Luck

/// native/141 — #5849: the shared failure copy stops naming a gesture.
///
/// THE PHOTOGRAPH. The Accuracy screen, iPhone 17 against production,
/// 2026-09-13 08:09Z, while `/api/calibration` served its accepted 503 dark
/// window — `artifacts-native-020/cal-503-before.png`:
///
///     ⚠
///     Server is temporarily unavailable. Pull to refresh.
///     [ Retry ]
///
/// `CalibrationView`'s error branch is a bare `VStack`, not a `ScrollView`, and
/// the file holds no `.refreshable` — so the one instruction on that screen did
/// nothing, and the affordance that worked was the button the copy never named.
///
/// The rule this pins is about the LAYER, not about that one sentence.
/// `APIError.errorDescription` is transport-layer text rendered verbatim by 19
/// error call sites; some of those surfaces are `.refreshable` and several are
/// not, and the enum cannot tell which one it is being drawn on. So no case of
/// it may tell a reader to perform a gesture — the surface owns its own
/// affordances. A ban alone would pass if the sentence were deleted outright,
/// which is a worse screen, so the guidance is pinned positively beside it.
final class APIErrorCopyTests: XCTestCase {

    /// Every shape the enum reaches a reader in, including both sides of each
    /// status-code branch. `decodingError`/`networkError` carry an underlying
    /// error that the copy never quotes; any error will do.
    private static let all: [APIError] = [
        .invalidURL,
        .httpError(statusCode: 400, body: nil),
        .httpError(statusCode: 404, body: nil),
        .httpError(statusCode: 429, body: nil),
        .httpError(statusCode: 500, body: nil),
        .httpError(statusCode: 502, body: nil),
        .httpError(statusCode: 503, body: "{\"reason\":\"no_trustworthy_snapshot\"}"),
        .decodingError(underlying: URLError(.cannotParseResponse)),
        .networkError(underlying: URLError(.notConnectedToInternet)),
    ]

    /// Words that name something a reader must do WITH THE SCREEN. A sentence
    /// containing one is a claim about the surface, which this layer cannot make.
    private static let gestures = ["pull", "swipe", "drag", "shake", "scroll", "long press"]

    // MARK: - #5849: the defect

    /// 🔴 THE DEFECT, generalised past its own case: no failure copy instructs a
    /// gesture. The photographed sentence fails this on "pull".
    func testNoFailureCopyTellsAReaderToPerformAGesture() {
        for error in Self.all {
            let copy = (error.errorDescription ?? "").lowercased()
            for gesture in Self.gestures {
                XCTAssertFalse(
                    copy.contains(gesture),
                    "\(error) tells the reader to \(gesture) a screen this layer knows nothing about: "
                        + "\(error.errorDescription ?? "nil")"
                )
            }
        }
    }

    /// The rendered path, not just the property. Views read
    /// `error.localizedDescription`, which reaches `errorDescription` only
    /// through `LocalizedError`'s bridging — a conformance that can be lost.
    func testTheGestureBanHoldsOnThePathTheViewsActuallyRead() {
        for error in Self.all {
            let rendered = (error as Error).localizedDescription.lowercased()
            for gesture in Self.gestures {
                XCTAssertFalse(
                    rendered.contains(gesture),
                    "\(error) renders a gesture instruction through localizedDescription: "
                        + "\((error as Error).localizedDescription)"
                )
            }
        }
    }

    /// 🔴 THE SECOND DEFECT, photographed on the after-shot of the first.
    /// `cal-503-after.png` (08:19Z, same screen, same session) caught the OTHER
    /// branch during a rate-limit burst and read `Request failed (429).` — a
    /// number a reader can do nothing with, on the page rather than in a log.
    /// The status code stays in the enum's payload, where callers switch on it;
    /// it does not belong in the sentence.
    func testNoFailureCopyPutsAStatusCodeOnAReadersScreen() {
        for error in Self.all {
            let copy = error.errorDescription ?? ""
            XCTAssertNil(
                copy.rangeOfCharacter(from: .decimalDigits),
                "\(error) prints plumbing at the reader: \(copy)"
            )
        }
    }

    // MARK: - The regression that would be worse than the bug

    /// 🔴 A BAN CANNOT SEE AN OMISSION. Deleting the clause passes the test
    /// above and leaves a reader with a dead end, so the 503 — the case that is
    /// live on the Accuracy screen right now — keeps saying what will help.
    func testTheUnavailableCopyStillTellsAReaderWhatWillHelp() {
        let copy = APIError.httpError(statusCode: 503, body: nil).errorDescription ?? ""
        XCTAssertEqual(copy, "Server is temporarily unavailable. Try again in a moment.")
        XCTAssertTrue(
            copy.lowercased().contains("try again"),
            "the unavailable state leaves the reader with nothing to do: \(copy)"
        )
    }

    /// No case may render as nothing. An empty string draws an icon and a Retry
    /// button over a blank line, which reads as a rendering bug rather than as a
    /// server that is briefly down.
    func testEveryFailureSaysSomething() {
        for error in Self.all {
            let copy = error.errorDescription ?? ""
            XCTAssertFalse(
                copy.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                "\(error) renders an empty error line"
            )
        }
    }
}
