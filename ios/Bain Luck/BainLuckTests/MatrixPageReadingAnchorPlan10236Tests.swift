import XCTest
@testable import Bain_Luck

private typealias AnchorPlan = MatrixPageReadingAnchorPlan10236
private typealias AnchorToken = MatrixPageReadingAnchorToken10236
private typealias AnchorReading = MatrixPageReadingAnchorMeasurement10236
private typealias AnchorDecision = MatrixPageReadingAnchorDecision10236
private typealias AnchorScroll = MatrixPageReadingAnchorScrollGeometry10236
private typealias AnchorMarker = MatrixPageReadingAnchorMarkerGeometry10236

/// #10236 — the restore decision behind "Close returns the reader to the same
/// visible player question while scores and prices keep updating".
///
/// The specimen is the issue's own: the marker is captured at content y 1000
/// with the page scrolled to 500, so it sits 500 points down the screen. A
/// header grows 22 points while the sheet is open (1022 / 500 ⇒ 522 on screen);
/// the page must move to 522, and the next reading (1022 / 522 ⇒ 500) must stop.
///
/// Each case is aimed at one wrong implementation: remembering `contentY`
/// instead of the on-screen position, the wrong sign, restoring the old absolute
/// offset, a fixed tolerance instead of one physical pixel, a missing clamp (or
/// a clamp that inverts when content is shorter than the page), and accepting a
/// stale presentation.
final class MatrixPageReadingAnchorPlan10236Tests: XCTestCase {
    private let eventID = 4242
    private let markerID = UUID(uuidString: "10236000-0000-4000-8000-000000010488")!
    private let otherMarkerID = UUID(uuidString: "10236000-0000-4000-8000-000000010489")!
    private let generation = 7

    private func captured(contentY: Double = 1000, boundsMinY: Double = 500,
                          host: MatrixPageReadingAnchorHost10236 = .during) throws -> AnchorToken {
        try XCTUnwrap(AnchorPlan.capture(eventID: eventID, host: host, markerInstanceID: markerID,
                                   presentationGeneration: generation,
                                   marker: AnchorMarker(contentY: contentY, boundsMinY: boundsMinY)))
    }

    private func scroll(offsetX: Double = 0, offsetY: Double, contentHeight: Double = 4000,
                        viewportHeight: Double = 800, top: Double = 0, bottom: Double = 0,
                        scale: Double = 3) -> AnchorScroll {
        AnchorScroll(offsetX: offsetX, offsetY: offsetY, contentHeight: contentHeight, viewportHeight: viewportHeight,
               adjustedTopInset: top, adjustedBottomInset: bottom, screenScale: scale)
    }

    /// A reading on the page as captured, with `bounds.minY == contentOffset.y`.
    private func reading(contentY: Double, boundsMinY: Double, offsetX: Double = 0,
                         contentHeight: Double = 4000, viewportHeight: Double = 800,
                         top: Double = 0, bottom: Double = 0, scale: Double = 3,
                         eventID: Int? = nil, host: MatrixPageReadingAnchorHost10236 = .during,
                         markerID: UUID? = nil, generation: Int? = nil,
                         condition: MatrixPageReadingAnchorPageCondition10236 = .intact) -> AnchorReading {
        AnchorReading(eventID: eventID ?? self.eventID, host: host, markerInstanceID: markerID ?? self.markerID,
                    presentationGeneration: generation ?? self.generation, condition: condition,
                    marker: AnchorMarker(contentY: contentY, boundsMinY: boundsMinY),
                    scroll: scroll(offsetX: offsetX, offsetY: boundsMinY, contentHeight: contentHeight,
                                   viewportHeight: viewportHeight, top: top, bottom: bottom, scale: scale))
    }

    private func move(_ x: Double, _ y: Double) -> AnchorDecision {
        .move(to: MatrixPageReadingAnchorOffset10236(x: x, y: y))
    }

    // MARK: - The issue's specimen

    func testCaptureRemembersTheOnScreenPositionNotTheContentPosition() throws {
        let token = try captured()
        XCTAssertEqual(token.viewportY, 500, "1000 content − 500 bounds = 500 on screen; 1000 means contentY was kept")
        XCTAssertEqual(token.phase, .held)
        XCTAssertEqual(token.eventID, eventID)
        XCTAssertEqual(token.host, .during)
        XCTAssertEqual(token.markerInstanceID, markerID)
        XCTAssertEqual(token.presentationGeneration, generation)
    }

    func testHeaderGrowthMovesThePageByTheGrowthAndThenStops() throws {
        let token = try captured()
        // contentY substitution proposes 522 here too, but 544 on the next reading;
        // the old absolute offset proposes 500 (a hold) here.
        XCTAssertEqual(AnchorPlan.reconcile(token, reading(contentY: 1022, boundsMinY: 500)), move(0, 522))
        XCTAssertEqual(AnchorPlan.reconcile(token, reading(contentY: 1022, boundsMinY: 522)), .hold(.restored))
    }

    func testHeaderShrinkMovesThePageUpAndThenStops() throws {
        let token = try captured()
        XCTAssertEqual(AnchorPlan.reconcile(token, reading(contentY: 970, boundsMinY: 500)), move(0, 470))
        XCTAssertEqual(AnchorPlan.reconcile(token, reading(contentY: 970, boundsMinY: 470)), .hold(.restored))
    }

    func testDestinationIsRelativeToTheCurrentOffsetNotTheCapturedOne() throws {
        let token = try captured()
        // The page itself sits at 600 now and the header grew 22: marker at 1022 − 600 = 422
        // on screen, 78 too high. Restoring the captured offset would answer 500.
        XCTAssertEqual(AnchorPlan.reconcile(token, reading(contentY: 1022, boundsMinY: 600)), move(0, 522))
    }

    func testAPageThatDidNotMoveIsAskedAgainForTheSameDestination() throws {
        let token = try captured()
        let first = AnchorPlan.reconcile(token, reading(contentY: 1022, boundsMinY: 500))
        let again = AnchorPlan.reconcile(token, reading(contentY: 1022, boundsMinY: 500))
        XCTAssertEqual(first, move(0, 522))
        XCTAssertEqual(again, first, "the token is never rebased to the drift it observed")
        XCTAssertEqual(token.viewportY, 500)
    }

    func testHorizontalOffsetIsCarriedThroughUnchanged() throws {
        let token = try captured()
        XCTAssertEqual(AnchorPlan.reconcile(token, reading(contentY: 1022, boundsMinY: 500, offsetX: 37.5)), move(37.5, 522))
    }

    func testAfterHostRestoresTheSameWay() throws {
        let token = try captured(host: .after)
        XCTAssertEqual(AnchorPlan.reconcile(token, reading(contentY: 1022, boundsMinY: 500, host: .after)), move(0, 522))
    }

    func testDismissalKeepsIdentityAndPositionAndStillReconciles() throws {
        let held = try captured()
        let dismissed = held.dismissed()
        XCTAssertEqual(dismissed.phase, .postDismissal)
        XCTAssertEqual(dismissed.viewportY, held.viewportY)
        XCTAssertEqual(dismissed.eventID, held.eventID)
        XCTAssertEqual(dismissed.host, held.host)
        XCTAssertEqual(dismissed.markerInstanceID, held.markerInstanceID)
        XCTAssertEqual(dismissed.presentationGeneration, held.presentationGeneration)
        XCTAssertEqual(AnchorPlan.reconcile(dismissed, reading(contentY: 1022, boundsMinY: 500)), move(0, 522))
    }

    // MARK: - One physical pixel

    func testToleranceIsOnePhysicalPixelAtTheSuppliedScale() throws {
        let token = try captured()
        // scale 2: half a point is one pixel.
        XCTAssertEqual(AnchorPlan.reconcile(token, reading(contentY: 1000.49, boundsMinY: 500, scale: 2)), .hold(.restored))
        XCTAssertEqual(AnchorPlan.reconcile(token, reading(contentY: 1000.5, boundsMinY: 500, scale: 2)), move(0, 500.5))
        XCTAssertEqual(AnchorPlan.reconcile(token, reading(contentY: 999.51, boundsMinY: 500, scale: 2)), .hold(.restored))
        XCTAssertEqual(AnchorPlan.reconcile(token, reading(contentY: 999.5, boundsMinY: 500, scale: 2)), move(0, 499.5))
        // scale 3: a third of a point.
        XCTAssertEqual(AnchorPlan.reconcile(token, reading(contentY: 1000.3, boundsMinY: 500, scale: 3)), .hold(.restored))
        guard case .move(let to) = AnchorPlan.reconcile(token, reading(contentY: 1000.34, boundsMinY: 500, scale: 3)) else {
            return XCTFail("0.34 pt is more than one pixel at 3x")
        }
        XCTAssertEqual(to.y, 500.34, accuracy: 1e-9)
        // scale 1: just under a point holds.
        XCTAssertEqual(AnchorPlan.reconcile(token, reading(contentY: 1000.9, boundsMinY: 500, scale: 1)), .hold(.restored))
    }

    // MARK: - Clamps

    func testBottomLimitClampsAndThenHoldsInsteadOfChasing() throws {
        let token = try captured()
        // 1200 content − 800 page + 34 inset = 434 is the deepest offset.
        let short = { (contentY: Double, offset: Double) in
            self.reading(contentY: contentY, boundsMinY: offset, contentHeight: 1200, bottom: 34)
        }
        XCTAssertEqual(AnchorPlan.reconcile(token, short(942, 420)), move(0, 434))
        // Arrived at the limit, still 8 short: hold, every time.
        XCTAssertEqual(AnchorPlan.reconcile(token, short(942, 434)), .hold(.clampedAtLimit))
        XCTAssertEqual(AnchorPlan.reconcile(token, short(942, 434)), .hold(.clampedAtLimit))
    }

    func testTopLimitIsTheNegativeAdjustedTopInset() throws {
        let token = try captured()
        // offset −90, marker 478 on screen ⇒ 22 too high; −112 is past the −100 limit.
        XCTAssertEqual(AnchorPlan.reconcile(token, reading(contentY: 388, boundsMinY: -90, top: 100)), move(0, -100))
        XCTAssertEqual(AnchorPlan.reconcile(token, reading(contentY: 388, boundsMinY: -100, top: 100)), .hold(.clampedAtLimit))
    }

    func testContentShorterThanThePageHasOneValidOffset() throws {
        let token = try captured()
        // 300 − 800 + 34 = −466 < −100, so both limits are −100.
        let tiny = { (contentY: Double) in
            self.reading(contentY: contentY, boundsMinY: -100, contentHeight: 300, top: 100, bottom: 34)
        }
        XCTAssertEqual(AnchorPlan.reconcile(token, tiny(422)), .hold(.clampedAtLimit))
        XCTAssertEqual(AnchorPlan.reconcile(token, tiny(378)), .hold(.clampedAtLimit))
    }

    // MARK: - Non-finite geometry

    func testCaptureRefusesNonFiniteMarkerGeometry() {
        let cases: [(Double, Double)] = [(.nan, 500), (.infinity, 500), (1000, -.infinity), (1000, .nan)]
        for (contentY, boundsMinY) in cases {
            XCTAssertNil(AnchorPlan.capture(eventID: eventID, host: .during, markerInstanceID: markerID,
                                      presentationGeneration: generation,
                                      marker: AnchorMarker(contentY: contentY, boundsMinY: boundsMinY)),
                         "\(contentY) / \(boundsMinY)")
        }
    }

    func testReconcileRefusesNonFiniteOrUnusableGeometry() throws {
        let token = try captured()
        let bad: [Double] = [.nan, .infinity, -.infinity]
        var readings: [AnchorReading] = []
        for value in bad {
            readings.append(reading(contentY: value, boundsMinY: 500))
            readings.append(reading(contentY: 1022, boundsMinY: value))
            readings.append(reading(contentY: 1022, boundsMinY: 500, offsetX: value))
            readings.append(reading(contentY: 1022, boundsMinY: 500, contentHeight: value))
            readings.append(reading(contentY: 1022, boundsMinY: 500, viewportHeight: value))
            readings.append(reading(contentY: 1022, boundsMinY: 500, top: value))
            readings.append(reading(contentY: 1022, boundsMinY: 500, bottom: value))
            readings.append(reading(contentY: 1022, boundsMinY: 500, scale: value))
            // offsetY alone (bounds.minY finite).
            readings.append(AnchorReading(eventID: eventID, host: .during, markerInstanceID: markerID,
                                        presentationGeneration: generation,
                                        marker: AnchorMarker(contentY: 1022, boundsMinY: 500),
                                        scroll: scroll(offsetY: value)))
        }
        readings.append(reading(contentY: 1022, boundsMinY: 500, scale: 0))
        readings.append(reading(contentY: 1022, boundsMinY: 500, scale: -2))
        for (index, measurement) in readings.enumerated() {
            XCTAssertEqual(AnchorPlan.reconcile(token, measurement), .invalidate(.nonFiniteGeometry), "reading \(index)")
        }
    }

    // MARK: - Identity

    func testMismatchedIdentityInvalidatesEvenWhenTheGeometryWantsToMove() throws {
        let token = try captured()
        XCTAssertEqual(AnchorPlan.reconcile(token, reading(contentY: 1022, boundsMinY: 500, eventID: 4243)),
                       .invalidate(.eventMismatch))
        XCTAssertEqual(AnchorPlan.reconcile(token, reading(contentY: 1022, boundsMinY: 500, host: .after)),
                       .invalidate(.hostMismatch))
        XCTAssertEqual(AnchorPlan.reconcile(token, reading(contentY: 1022, boundsMinY: 500, markerID: otherMarkerID)),
                       .invalidate(.markerMismatch))
        XCTAssertEqual(AnchorPlan.reconcile(token, reading(contentY: 1022, boundsMinY: 500, generation: 8)),
                       .invalidate(.staleGeneration), "the token is older than the presentation")
        XCTAssertEqual(AnchorPlan.reconcile(token, reading(contentY: 1022, boundsMinY: 500, generation: 6)),
                       .invalidate(.staleGeneration), "the reading is older than the token")
    }

    // MARK: - Withdrawal, route and drag

    func testAMissingTokenOrPageNeverScrolls() throws {
        XCTAssertEqual(AnchorPlan.reconcile(nil, reading(contentY: 1022, boundsMinY: 500)), .invalidate(.noToken))
        let token = try captured()
        XCTAssertEqual(AnchorPlan.reconcile(token, nil), .invalidate(.unavailable))
    }

    func testEveryPageConditionOtherThanIntactInvalidates() throws {
        let token = try captured()
        let expected: [(MatrixPageReadingAnchorPageCondition10236, MatrixPageReadingAnchorInvalidation10236)] = [
            (.detached, .detached), (.inactive, .inactive), (.routeChanged, .routeChanged), (.verticalDrag, .verticalDrag)
        ]
        for (condition, reason) in expected {
            XCTAssertEqual(AnchorPlan.reconcile(token, reading(contentY: 1022, boundsMinY: 500, condition: condition)),
                           .invalidate(reason))
            XCTAssertEqual(AnchorPlan.reconcile(token.dismissed(),
                                          reading(contentY: 1022, boundsMinY: 500, condition: condition)),
                           .invalidate(reason))
        }
    }
}
