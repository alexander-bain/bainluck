import Foundation

/// Sends bug reports that could not be delivered when they were written (#1847).
///
/// There is ONE implementation, called from the app lifecycle (foreground) and
/// from the report sheet. Before this existed, the retry lived privately inside
/// `BugReportView.retryPendingDrafts()`, so a queued report was only ever
/// attempted when the user opened the bug-report sheet again — i.e. it required
/// the user to shake a second time before their first report was even tried.
enum BugReportOutbox {
    /// Injected by tests. Production always talks to the real client.
    nonisolated(unsafe) static var send: @Sendable (BugReportSubmission) async throws -> BugReportResponse = {
        try await APIClient.shared.submitBugReport($0)
    }

    nonisolated struct FlushResult: Equatable, Sendable {
        /// Reports that reached the server during this flush.
        let sent: Int
        /// Reports still queued afterwards.
        let remaining: Int

        var isEmpty: Bool { sent == 0 && remaining == 0 }
    }

    /// Upper bound on sends per flush. Guards the loop, which re-reads the
    /// queue each pass rather than holding indices across an await.
    private static let maxPerFlush = 10

    /// Attempt to deliver every queued report, oldest first.
    ///
    /// FIFO on purpose: the oldest report is the one the user has been waiting
    /// on. Stops at the first failure and leaves the remainder queued — a
    /// server that just refused one report will refuse the next.
    ///
    /// A delivered report gets a receipt exactly like a live submission, so a
    /// report recovered days later is still answerable with an id.
    @discardableResult
    static func flush() async -> FlushResult {
        var sent = 0

        for _ in 0..<maxPerFlush {
            // Re-read rather than hold an index across the await: the sheet can
            // enqueue while a flush is in flight.
            guard let draft = BugReportDraftStore.loadDrafts().first else { break }

            do {
                let response = try await send(draft)
                BugReportReceiptStore.record(
                    id: response.id,
                    description: draft.description,
                    page: draft.appState?["current_page"]
                )
                BugReportDraftStore.removeDraft(at: 0)
                sent += 1
            } catch {
                break
            }
        }

        return FlushResult(sent: sent, remaining: BugReportDraftStore.pendingCount)
    }
}
