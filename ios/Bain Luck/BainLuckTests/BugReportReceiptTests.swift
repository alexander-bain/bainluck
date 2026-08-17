import XCTest

@testable import Bain_Luck

/// UX-P076 (#1847) — the rage-shake RECEIPT.
///
/// The named failure: Alex shook twice on 2026-08-13, neither report landed,
/// and he spent three days unable to find out. The reports were either queued
/// on his device or nowhere, and nothing could tell him which.
///
/// These pin the durable half — the stores and the outbox. The view wiring
/// (receipt panel, outbox panel, save-before-alert) is covered by the
/// `xcodebuild` gate and rendered evidence, and is called out as such in the
/// report rather than claimed here.
final class BugReportReceiptTests: XCTestCase {
    private var defaults: UserDefaults!
    private var suiteName: String!

    override func setUp() {
        super.setUp()
        suiteName = "bugreport.tests.\(UUID().uuidString)"
        defaults = UserDefaults(suiteName: suiteName)
        BugReportReceiptStore.defaults = defaults
        BugReportDraftStore.defaults = defaults
        BugReportRejectionStore.defaults = defaults
    }

    override func tearDown() {
        defaults.removePersistentDomain(forName: suiteName)
        BugReportReceiptStore.defaults = .standard
        BugReportDraftStore.defaults = .standard
        BugReportRejectionStore.defaults = .standard
        BugReportOutbox.send = { try await APIClient.shared.submitBugReport($0) }
        super.tearDown()
    }

    /// The real production answer to a 5,001-character description, captured
    /// on 2026-08-17 against `POST /api/feedback/bug-report`. Used verbatim so
    /// these tests are pinned to what the server actually says, not to a
    /// plausible-looking invention (fixture-from-production standard).
    private static let productionOversizeBody = """
    {"detail":[{"type":"value_error","loc":["body","description"],\
    "msg":"Value error, Description too long (max 5000 chars)"}]}
    """

    private func oversizeRefusal() -> APIError {
        .httpError(statusCode: 422, body: Self.productionOversizeBody)
    }

    private func submission(
        description: String? = "something broke",
        page: String = "Discover",
        shot: String? = nil
    ) -> BugReportSubmission {
        BugReportSubmission(
            description: description,
            screenshotBase64: shot,
            appState: ["current_page": page, "timestamp": UUID().uuidString],
            notifyOnFix: false
        )
    }

    // MARK: - The receipt survives the toast

    func testRecordedReceiptCarriesTheServerId() {
        BugReportReceiptStore.record(id: 147, description: "cards are stale", page: "Discover")

        let receipt = BugReportReceiptStore.mostRecent
        XCTAssertEqual(receipt?.id, 147, "the server-assigned id IS the receipt")
        XCTAssertEqual(receipt?.summary, "cards are stale")
        XCTAssertEqual(receipt?.page, "Discover")
    }

    func testReceiptsPersistAcrossStoreReads() {
        BugReportReceiptStore.record(id: 200, description: "a", page: nil)
        // A fresh read is what the NEXT launch does. The old success state was
        // in-memory only and died with the sheet.
        XCTAssertEqual(BugReportReceiptStore.loadReceipts().count, 1)
        XCTAssertEqual(BugReportReceiptStore.loadReceipts().first?.id, 200)
    }

    func testReceiptsAreNewestFirst() {
        BugReportReceiptStore.record(id: 1, description: "oldest", page: nil)
        BugReportReceiptStore.record(id: 2, description: "middle", page: nil)
        BugReportReceiptStore.record(id: 3, description: "newest", page: nil)

        XCTAssertEqual(BugReportReceiptStore.loadReceipts().map(\.id), [3, 2, 1])
        XCTAssertEqual(BugReportReceiptStore.mostRecent?.summary, "newest")
    }

    func testScreenshotOnlyReportGetsAReadableSummary() {
        // The form's own placeholder says "the screenshot may be enough!", so a
        // description-less report is normal, not degenerate.
        BugReportReceiptStore.record(id: 5, description: "   ", page: nil)
        XCTAssertEqual(
            BugReportReceiptStore.mostRecent?.summary,
            BugReportReceipt.screenshotOnlySummary
        )

        BugReportReceiptStore.record(id: 6, description: nil, page: nil)
        XCTAssertEqual(
            BugReportReceiptStore.mostRecent?.summary,
            BugReportReceipt.screenshotOnlySummary
        )
    }

    func testLongSummaryIsTruncatedNotDropped() {
        let long = String(repeating: "x", count: 300)
        BugReportReceiptStore.record(id: 7, description: long, page: nil)

        let summary = try! XCTUnwrap(BugReportReceiptStore.mostRecent?.summary)
        XCTAssertEqual(summary.count, 80, "79 chars + ellipsis")
        XCTAssertTrue(summary.hasSuffix("…"))
    }

    func testRecordingTheSameIdTwiceKeepsOneReceipt() {
        BugReportReceiptStore.record(id: 42, description: "first", page: nil)
        BugReportReceiptStore.record(id: 42, description: "first", page: nil)

        XCTAssertEqual(BugReportReceiptStore.count, 1, "a retry must not duplicate a receipt")
    }

    func testReceiptsAreCappedButKeepTheNewest() {
        for id in 1...30 { BugReportReceiptStore.record(id: id, description: "r\(id)", page: nil) }

        let receipts = BugReportReceiptStore.loadReceipts()
        XCTAssertEqual(receipts.count, 20)
        XCTAssertEqual(receipts.first?.id, 30, "newest survives")
        XCTAssertEqual(receipts.last?.id, 11, "oldest is evicted")
    }

    // MARK: - Drafts: the outbox the user can finally see

    func testPendingCountReflectsSavedDrafts() {
        XCTAssertEqual(BugReportDraftStore.pendingCount, 0)
        XCTAssertFalse(BugReportDraftStore.hasPendingDrafts)

        BugReportDraftStore.saveDraft(submission(description: "one"))

        // These two properties existed from the beginning with ZERO call sites
        // — the whole "you have an unsent report" affordance was built and
        // never wired. They are now the outbox panel's data source.
        XCTAssertEqual(BugReportDraftStore.pendingCount, 1)
        XCTAssertTrue(BugReportDraftStore.hasPendingDrafts)
    }

    func testSavingTheSameReportTwiceQueuesItOnce() {
        // Reachable now that failure ALWAYS persists: submit fails (saves),
        // Try Again fails (saves again). Without dedup that is two reports.
        let first = submission(description: "same report", page: "Discover")
        let second = submission(description: "same report", page: "Discover")

        BugReportDraftStore.saveDraft(first)
        BugReportDraftStore.saveDraft(second)

        XCTAssertEqual(BugReportDraftStore.pendingCount, 1)
    }

    func testDifferentReportsBothQueue() {
        BugReportDraftStore.saveDraft(submission(description: "first"))
        BugReportDraftStore.saveDraft(submission(description: "second"))

        XCTAssertEqual(BugReportDraftStore.pendingCount, 2)
    }

    func testDraftKeyIgnoresTheRegeneratedTimestamp() {
        // app_state carries a fresh `timestamp` on every build, so a whole
        // payload comparison would never match itself.
        let a = submission(description: "x", page: "Discover")
        let b = submission(description: "x", page: "Discover")
        XCTAssertNotEqual(a.appState?["timestamp"], b.appState?["timestamp"])
        XCTAssertEqual(a.draftKey, b.draftKey)
    }

    func testDraftKeySeparatesReportsFromDifferentPages() {
        XCTAssertNotEqual(
            submission(description: "x", page: "Discover").draftKey,
            submission(description: "x", page: "Search").draftKey
        )
    }

    // MARK: - The outbox

    func testFlushDeliversQueuedReportsAndRecordsReceipts() async {
        BugReportDraftStore.saveDraft(submission(description: "queued one"))
        BugReportDraftStore.saveDraft(submission(description: "queued two"))

        var ids = [10, 11]
        BugReportOutbox.send = { _ in
            BugReportResponse(status: "ok", id: ids.removeFirst())
        }

        let result = await BugReportOutbox.flush()

        XCTAssertEqual(result.sent, 2)
        XCTAssertEqual(result.remaining, 0)
        XCTAssertEqual(BugReportDraftStore.pendingCount, 0, "delivered drafts leave the queue")
        // A report recovered days later must still be answerable with an id.
        XCTAssertEqual(Set(BugReportReceiptStore.loadReceipts().map(\.id)), [10, 11])
    }

    func testFlushIsFifo() async {
        BugReportDraftStore.saveDraft(submission(description: "oldest"))
        BugReportDraftStore.saveDraft(submission(description: "newest"))

        var seen: [String] = []
        var nextId = 1
        BugReportOutbox.send = { sub in
            seen.append(sub.description ?? "")
            defer { nextId += 1 }
            return BugReportResponse(status: "ok", id: nextId)
        }

        await BugReportOutbox.flush()

        XCTAssertEqual(seen, ["oldest", "newest"], "the oldest report is the one being waited on")
    }

    func testFlushStopsAtFirstFailureAndKeepsTheRemainder() async {
        BugReportDraftStore.saveDraft(submission(description: "will fail"))
        BugReportDraftStore.saveDraft(submission(description: "never attempted"))

        var attempts = 0
        BugReportOutbox.send = { _ in
            attempts += 1
            throw APIError.networkError(underlying: NSError(domain: "t", code: 1))
        }

        let result = await BugReportOutbox.flush()

        XCTAssertEqual(attempts, 1, "a server that just refused one report will refuse the next")
        XCTAssertEqual(result.sent, 0)
        XCTAssertEqual(result.remaining, 2)
        XCTAssertEqual(BugReportDraftStore.pendingCount, 2, "a failed send must NEVER drop the report")
    }

    func testFailedFlushRecordsNoReceipt() async {
        BugReportDraftStore.saveDraft(submission(description: "will fail"))
        BugReportOutbox.send = { _ in
            throw APIError.networkError(underlying: NSError(domain: "t", code: 1))
        }

        await BugReportOutbox.flush()

        XCTAssertEqual(BugReportReceiptStore.count, 0, "no receipt without an acknowledgment")
    }

    func testFlushOnEmptyQueueIsANoOp() async {
        var called = false
        BugReportOutbox.send = { _ in
            called = true
            return BugReportResponse(status: "ok", id: 1)
        }

        let result = await BugReportOutbox.flush()

        XCTAssertFalse(called)
        XCTAssertEqual(result, BugReportOutbox.FlushResult(sent: 0, remaining: 0))
    }

    func testFlushIsBoundedEvenIfDeliveryNeverDrainsTheQueue() async {
        // Guards the re-read loop: if a send "succeeded" without the draft
        // leaving the queue, an unbounded loop would spin forever.
        BugReportDraftStore.saveDraft(submission(description: "sticky"))
        var attempts = 0
        BugReportOutbox.send = { sub in
            attempts += 1
            // Re-queue behind our back, simulating a store that won't drain.
            BugReportDraftStore.saveDraft(sub)
            return BugReportResponse(status: "ok", id: attempts)
        }

        await BugReportOutbox.flush()

        XCTAssertLessThanOrEqual(attempts, 10, "flush must be bounded")
    }

    // MARK: - The poison pill (#1847, UX-P088)

    func testAPermanentRefusalDoesNotBlockTheReportsBehindIt() async {
        // THE BUG, stated as a test. A 5,001-char description returns a
        // deterministic 422. Queued at the head of a FIFO outbox that stopped
        // at the first failure, it blocked every later report forever — on
        // every foreground, until the cap silently deleted it.
        BugReportDraftStore.saveDraft(submission(description: "the over-long one"))
        BugReportDraftStore.saveDraft(submission(description: "queued behind it"))

        var delivered: [String] = []
        BugReportOutbox.send = { [self] sub in
            if sub.description == "the over-long one" { throw oversizeRefusal() }
            delivered.append(sub.description ?? "")
            return BugReportResponse(status: "ok", id: 147)
        }

        let result = await BugReportOutbox.flush()

        XCTAssertEqual(delivered, ["queued behind it"],
                       "the report behind a refused one must still be delivered")
        XCTAssertEqual(result.sent, 1)
        XCTAssertEqual(result.rejected, 1)
        XCTAssertEqual(result.remaining, 0, "the queue drains rather than jamming")
        XCTAssertEqual(BugReportReceiptStore.mostRecent?.id, 147)
    }

    func testARefusedReportIsKeptWithItsReasonNotDestroyed() async {
        BugReportDraftStore.saveDraft(submission(description: "way too long"))
        BugReportOutbox.send = { [self] _ in throw oversizeRefusal() }

        await BugReportOutbox.flush()

        XCTAssertEqual(BugReportDraftStore.pendingCount, 0, "it leaves the queue")
        let rejection = try! XCTUnwrap(BugReportRejectionStore.mostRecent)
        XCTAssertEqual(rejection.statusCode, 422)
        XCTAssertEqual(rejection.description, "way too long",
                       "the rejection list holds the only surviving copy of the text")
        XCTAssertTrue(rejection.reason.contains("5,000"),
                      "the reason names the actual limit, not a status number")
    }

    func testATransientFailureStillStopsTheFlushAndKeepsEverything() async {
        // Both directions (gotcha #43): draining past a refusal must NOT turn
        // into draining past a dead network, which would burn the whole queue
        // against a server that is merely down.
        BugReportDraftStore.saveDraft(submission(description: "first"))
        BugReportDraftStore.saveDraft(submission(description: "second"))

        var attempts = 0
        BugReportOutbox.send = { _ in
            attempts += 1
            throw APIError.httpError(statusCode: 503, body: nil)
        }

        let result = await BugReportOutbox.flush()

        XCTAssertEqual(attempts, 1, "a 5xx is 'not now' — stop and keep the queue")
        XCTAssertEqual(result.rejected, 0)
        XCTAssertEqual(result.remaining, 2)
        XCTAssertEqual(BugReportRejectionStore.count, 0, "nothing was refused")
    }

    func testRateLimitAndTimeoutAreTransientDespiteBeing4xx() {
        // 429 and 408 are the two 4xx that mean "come back", not "never".
        // Treating them as refusals would throw away a perfectly good report
        // during exactly the burst #1909 documented.
        XCTAssertFalse(BugReportOutbox.isPermanentRefusal(
            APIError.httpError(statusCode: 429, body: nil)))
        XCTAssertFalse(BugReportOutbox.isPermanentRefusal(
            APIError.httpError(statusCode: 408, body: nil)))
        XCTAssertFalse(BugReportOutbox.isPermanentRefusal(
            APIError.networkError(underlying: NSError(domain: "t", code: 1))))
        XCTAssertFalse(BugReportOutbox.isPermanentRefusal(
            APIError.httpError(statusCode: 500, body: nil)))

        XCTAssertTrue(BugReportOutbox.isPermanentRefusal(
            APIError.httpError(statusCode: 422, body: nil)))
        XCTAssertTrue(BugReportOutbox.isPermanentRefusal(
            APIError.httpError(statusCode: 413, body: nil)))
    }

    func testTheSameReportRefusedTwiceKeepsOneEntry() async {
        BugReportDraftStore.saveDraft(submission(description: "too long"))
        BugReportOutbox.send = { [self] _ in throw oversizeRefusal() }
        await BugReportOutbox.flush()

        // Re-filed identically after the user taps Submit again.
        BugReportDraftStore.saveDraft(submission(description: "too long"))
        await BugReportOutbox.flush()

        XCTAssertEqual(BugReportRejectionStore.count, 1)
    }

    func testDiscardingARejectionRequiresAnExplicitId() async {
        BugReportDraftStore.saveDraft(submission(description: "too long"))
        BugReportOutbox.send = { [self] _ in throw oversizeRefusal() }
        await BugReportOutbox.flush()

        let rejection = try! XCTUnwrap(BugReportRejectionStore.mostRecent)
        BugReportRejectionStore.discard(id: "some-other-report")
        XCTAssertEqual(BugReportRejectionStore.count, 1, "only the named one goes")

        BugReportRejectionStore.discard(id: rejection.id)
        XCTAssertEqual(BugReportRejectionStore.count, 0)
    }

    // MARK: - The cap no longer loses a report in silence

    func testCapEvictionIsCounted() {
        for i in 1...(BugReportDraftStore.maxDrafts + 2) {
            BugReportDraftStore.saveDraft(submission(description: "report \(i)"))
        }

        XCTAssertEqual(BugReportDraftStore.pendingCount, BugReportDraftStore.maxDrafts)
        XCTAssertEqual(BugReportDraftStore.droppedCount, 2,
                       "an eviction the user is never told about is a lost report")
    }

    func testStayingUnderTheCapDropsNothing() {
        for i in 1...BugReportDraftStore.maxDrafts {
            BugReportDraftStore.saveDraft(submission(description: "report \(i)"))
        }
        XCTAssertEqual(BugReportDraftStore.droppedCount, 0)
    }

    // MARK: - Clock independence (gotcha #44, sweep class)

    func testRejectionStoreBehavesIdenticallyAtEveryPointInAYear() {
        // Gotcha #44's sweep, in Swift. Every date-carrying store here is
        // checked against 12 monthly instants plus a far-future one, because a
        // fixture that only ever runs "now" hides anything that branches on the
        // clock — and three of this repo's four instances of that bug were
        // found only by sweeping.
        let base = Date(timeIntervalSince1970: 1_770_000_000)
        var instants = (0..<12).map { base.addingTimeInterval(Double($0) * 30 * 86_400) }
        instants.append(base.addingTimeInterval(400 * 86_400))

        for (index, instant) in instants.enumerated() {
            BugReportRejectionStore.clear()
            BugReportReceiptStore.clear()

            let rejection = BugReportRejectionStore.record(
                draftKey: "k", description: "text", page: "Discover",
                statusCode: 422, rejectedAt: instant
            )
            let receipt = BugReportReceiptStore.record(
                id: 1, description: "text", page: "Discover", submittedAt: instant
            )

            XCTAssertEqual(rejection.rejectedAt, instant, "instant \(index) round-trips")
            XCTAssertEqual(receipt.submittedAt, instant, "instant \(index) round-trips")
            XCTAssertEqual(BugReportRejectionStore.count, 1,
                           "storage must not depend on when it happened (instant \(index))")
            XCTAssertEqual(rejection.reason,
                           BugReportRejectionStore.reason(forStatus: 422),
                           "the sentence shown must not vary with the clock (instant \(index))")
        }
    }

    // MARK: - The client-side limit that prevents the refusal at source

    func testClientLimitMatchesTheServerValidator() {
        // If these drift, the app either blocks reports the server would have
        // accepted, or mints the poison report this whole section is about.
        // Server: `check_description_length` rejects `len(v) > 5000`.
        XCTAssertEqual(BugReportView.maxDescriptionLength, 5_000)
        XCTAssertLessThan(
            BugReportView.descriptionSoftWarningLength,
            BugReportView.maxDescriptionLength,
            "the counter has to appear BEFORE the limit to be any use"
        )
    }

    // MARK: - The shake entry point

    func testScreenshotWrapperAcceptsNoImage() {
        // The shake handler used to be `if let image = captureScreenshot()`,
        // making the PRIMARY report gesture a silent no-op whenever capture
        // failed. The sheet must be presentable without an image.
        let wrapper = ScreenshotWrapper(image: nil)
        XCTAssertNil(wrapper.image)
    }
}
