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
    }

    override func tearDown() {
        defaults.removePersistentDomain(forName: suiteName)
        BugReportReceiptStore.defaults = .standard
        BugReportDraftStore.defaults = .standard
        BugReportOutbox.send = { try await APIClient.shared.submitBugReport($0) }
        super.tearDown()
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

    // MARK: - The shake entry point

    func testScreenshotWrapperAcceptsNoImage() {
        // The shake handler used to be `if let image = captureScreenshot()`,
        // making the PRIMARY report gesture a silent no-op whenever capture
        // failed. The sheet must be presentable without an image.
        let wrapper = ScreenshotWrapper(image: nil)
        XCTAssertNil(wrapper.image)
    }
}
