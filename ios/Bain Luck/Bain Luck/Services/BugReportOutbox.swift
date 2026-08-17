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
        /// Reports the server refused outright and that are now in the
        /// rejection store rather than the queue (#1847, UX-P088).
        let rejected: Int
        /// Reports still queued afterwards.
        let remaining: Int

        init(sent: Int, rejected: Int = 0, remaining: Int) {
            self.sent = sent
            self.rejected = rejected
            self.remaining = remaining
        }

        var isEmpty: Bool { sent == 0 && rejected == 0 && remaining == 0 }
    }

    /// Whether the server's answer means "never", as opposed to "not now".
    ///
    /// UX-P088 (#1847). This distinction is the whole fix. The original outbox
    /// treated every failure as transient and stopped at the first one, which
    /// is right for a dead network and catastrophic for a deterministic `422`:
    /// the refused report never leaves the head of the queue, so nothing behind
    /// it is ever sent again.
    ///
    /// Measured on production while writing this: a 5,001-character description
    /// returns `422 {"detail":[{"type":"value_error", ... "Description too long
    /// (max 5000 chars)"}]}`. Retrying it changes nothing, on any schedule, ever.
    ///
    /// `408` and `429` are 4xx that explicitly mean "come back" — the server is
    /// declining to answer NOW, not refusing the report — so they stay
    /// transient. Everything else in 4xx is the server saying the payload
    /// itself is unacceptable.
    static func isPermanentRefusal(_ error: Error) -> Bool {
        guard let api = error as? APIError,
              case .httpError(let code, _) = api else { return false }
        if code == 408 || code == 429 { return false }
        return (400..<500).contains(code)
    }

    /// Upper bound on sends per flush. Guards the loop, which re-reads the
    /// queue each pass rather than holding indices across an await.
    private static let maxPerFlush = 10

    /// Attempt to deliver every queued report, oldest first.
    ///
    /// FIFO on purpose: the oldest report is the one the user has been waiting
    /// on.
    ///
    /// Stops at the first TRANSIENT failure and leaves the remainder queued — a
    /// server that just timed out on one report will time out on the next.
    ///
    /// A PERMANENT refusal is handled the opposite way, and that asymmetry is
    /// the point (UX-P088). Waiting does not help a report the server has
    /// already judged unacceptable, so it is moved out of the queue into
    /// `BugReportRejectionStore` and the flush CONTINUES to the report behind
    /// it. Before this, one over-long description at the head of the queue
    /// blocked every later report permanently and was then silently deleted by
    /// the five-draft cap.
    ///
    /// A delivered report gets a receipt exactly like a live submission, so a
    /// report recovered days later is still answerable with an id.
    @discardableResult
    static func flush() async -> FlushResult {
        var sent = 0
        var rejected = 0

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
                guard isPermanentRefusal(error) else { break }

                // Record BEFORE removing. If the process dies between the two,
                // the report is duplicated (queue + rejection list), never
                // lost — and `record` de-duplicates on the draft key, so the
                // next flush collapses it back to one.
                let statusCode: Int
                if case .httpError(let code, _)? = error as? APIError {
                    statusCode = code
                } else {
                    statusCode = 400
                }
                BugReportRejectionStore.record(
                    draftKey: draft.draftKey,
                    description: draft.description,
                    page: draft.appState?["current_page"],
                    statusCode: statusCode
                )
                BugReportDraftStore.removeDraft(at: 0)
                rejected += 1
            }
        }

        return FlushResult(
            sent: sent,
            rejected: rejected,
            remaining: BugReportDraftStore.pendingCount
        )
    }
}
