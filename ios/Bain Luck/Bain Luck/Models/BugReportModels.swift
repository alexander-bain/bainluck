import Foundation

/// Client payload submitted when a user files an in-app bug report.
nonisolated struct BugReportSubmission: Codable, Sendable {
    let description: String?
    let screenshotBase64: String?
    let appState: [String: String]?
    let notifyOnFix: Bool
}

/// Backend acknowledgment for a submitted bug report.
nonisolated struct BugReportResponse: Decodable, Sendable {
    let status: String
    let id: Int
}

extension BugReportSubmission {
    /// Identity used to de-duplicate queued drafts.
    ///
    /// Deliberately NOT the whole payload: `app_state` carries a `timestamp`
    /// regenerated on every build, so two saves of the same report would
    /// otherwise queue twice and submit twice (#1847 defect C's repair path
    /// makes a double-save reachable — Save for Later after a Try Again that
    /// also failed).
    var draftKey: String {
        let page = appState?["current_page"] ?? ""
        return "\(description ?? "")|\(page)|\(screenshotBase64?.count ?? 0)"
    }
}

// MARK: - Local Draft Persistence

/// Manages saving and retrying failed bug report submissions.
enum BugReportDraftStore {
    private static let draftsKey = "bainluck_bug_report_drafts"
    private static let droppedKey = "bainluck_bug_report_drafts_dropped"
    static let maxDrafts = 5

    /// Injectable for tests; production always uses `.standard`.
    nonisolated(unsafe) static var defaults: UserDefaults = .standard

    /// Save a failed submission locally for later retry.
    ///
    /// De-duplicates on `draftKey` so retrying-then-saving the same report
    /// cannot queue it twice.
    static func saveDraft(_ submission: BugReportSubmission) {
        var drafts = loadDrafts()
        let key = submission.draftKey
        if let existing = drafts.firstIndex(where: { $0.draftKey == key }) {
            drafts[existing] = submission
        } else {
            drafts.append(submission)
        }
        // Keep only the most recent drafts to avoid unbounded storage growth.
        //
        // UX-P088 (#1847): the cap stays — five reports can carry five ~1.5MB
        // screenshots, and UserDefaults is the wrong place for tens of
        // megabytes. What changes is that the eviction is COUNTED. `suffix`
        // drops from the front, and `flush` is FIFO from the front, so the
        // report thrown away here is precisely the one that has been waiting
        // longest. Doing that silently is the acceptance criterion "no path
        // loses a report" failing quietly, which is the whole complaint this
        // issue was filed about.
        if drafts.count > maxDrafts {
            let dropped = drafts.count - maxDrafts
            drafts = Array(drafts.suffix(maxDrafts))
            defaults.set(droppedCount + dropped, forKey: droppedKey)
        }
        if let data = try? JSONEncoder().encode(drafts) {
            defaults.set(data, forKey: draftsKey)
        }
    }

    /// How many queued reports have been evicted by the cap and never sent.
    ///
    /// Surfaced in the sheet. A number the user can see is not a lost report;
    /// an eviction nobody is told about is.
    static var droppedCount: Int {
        defaults.integer(forKey: droppedKey)
    }

    /// Acknowledge the dropped-report notice so it stops being shown.
    static func clearDroppedCount() {
        defaults.removeObject(forKey: droppedKey)
    }

    /// Load all saved drafts.
    static func loadDrafts() -> [BugReportSubmission] {
        guard let data = defaults.data(forKey: draftsKey),
              let drafts = try? JSONDecoder().decode([BugReportSubmission].self, from: data) else {
            return []
        }
        return drafts
    }

    /// Remove all saved drafts (after successful retry).
    static func clearDrafts() {
        defaults.removeObject(forKey: draftsKey)
    }

    /// Remove a specific draft by index.
    static func removeDraft(at index: Int) {
        var drafts = loadDrafts()
        guard index < drafts.count else { return }
        drafts.remove(at: index)
        if drafts.isEmpty {
            clearDrafts()
        } else if let data = try? JSONEncoder().encode(drafts) {
            defaults.set(data, forKey: draftsKey)
        }
    }

    /// Whether there are unsent drafts waiting to be retried.
    static var hasPendingDrafts: Bool {
        !loadDrafts().isEmpty
    }

    /// Number of pending drafts.
    static var pendingCount: Int {
        loadDrafts().count
    }
}

// MARK: - Receipts (#1847)

/// A durable local record that a report REACHED THE SERVER, carrying the
/// server-assigned `bug_reports.id`.
///
/// The whole point is that it outlives the 1.5-second success toast. Alex shook
/// twice on 2026-08-13, neither report landed, and there was no artifact
/// anywhere — on the device or in his memory — that could answer "did it send?"
nonisolated struct BugReportReceipt: Codable, Sendable, Identifiable, Equatable {
    /// Server-assigned `bug_reports.id` — the thing you can quote to check.
    let id: Int
    let submittedAt: Date
    /// Short human handle so a list of receipts is readable.
    let summary: String
    let page: String?

    /// What to show when the user wrote no description. A screenshot-only
    /// report is normal and explicitly encouraged by the form's placeholder.
    static let screenshotOnlySummary = "Screenshot only"

    init(id: Int, submittedAt: Date, description: String?, page: String?) {
        self.id = id
        self.submittedAt = submittedAt
        let trimmed = (description ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty {
            self.summary = Self.screenshotOnlySummary
        } else if trimmed.count > 80 {
            self.summary = String(trimmed.prefix(79)) + "…"
        } else {
            self.summary = trimmed
        }
        self.page = page
    }
}

/// Durable local log of reports the server acknowledged.
enum BugReportReceiptStore {
    private static let receiptsKey = "bainluck_bug_report_receipts"
    private static let maxReceipts = 20

    /// Injectable for tests; production always uses `.standard`.
    nonisolated(unsafe) static var defaults: UserDefaults = .standard

    /// Record a server acknowledgment. Newest first.
    @discardableResult
    static func record(
        id: Int,
        description: String?,
        page: String?,
        submittedAt: Date = Date()
    ) -> BugReportReceipt {
        let receipt = BugReportReceipt(
            id: id, submittedAt: submittedAt, description: description, page: page
        )
        var receipts = loadReceipts()
        // A retry that duplicates an id must not duplicate the receipt.
        receipts.removeAll { $0.id == id }
        receipts.insert(receipt, at: 0)
        if receipts.count > maxReceipts {
            receipts = Array(receipts.prefix(maxReceipts))
        }
        if let data = try? JSONEncoder().encode(receipts) {
            defaults.set(data, forKey: receiptsKey)
        }
        return receipt
    }

    /// All recorded receipts, newest first.
    static func loadReceipts() -> [BugReportReceipt] {
        guard let data = defaults.data(forKey: receiptsKey),
              let receipts = try? JSONDecoder().decode([BugReportReceipt].self, from: data) else {
            return []
        }
        return receipts
    }

    /// The most recent acknowledged report, if any.
    static var mostRecent: BugReportReceipt? { loadReceipts().first }

    /// Number of acknowledged reports on record.
    static var count: Int { loadReceipts().count }

    static func clear() {
        defaults.removeObject(forKey: receiptsKey)
    }
}

// MARK: - Rejections (#1847, UX-P088)

/// A report the server will NEVER accept, kept where the user can see it.
///
/// ── Why this type exists ──
///
/// UX-P076 gave the outbox a rule: "stops at the first failure and leaves the
/// remainder queued — a server that just refused one report will refuse the
/// next." That is correct for the failure it was written against (no network,
/// a 5xx, a rate limit) and wrong for the one failure that was actually
/// MEASURED on production while filing this issue: a description over 5,000
/// characters returns a deterministic `422`, forever.
///
/// A permanently-refused report sitting at index 0 of a FIFO queue therefore
/// blocked every report queued behind it, on every foreground, indefinitely —
/// while the sheet said "N reports are waiting to send", offered a "Try
/// Sending Now" button that could not succeed, and an alert that promised
/// "your report is saved on this device and will send automatically". Three
/// statements, none of them true for that report. Then, after five more saves,
/// the cap silently deleted it.
///
/// A permanent refusal is a real answer from the server, so the report leaves
/// the queue immediately — and lands here, with the reason, rather than in the
/// bin.
nonisolated struct BugReportRejection: Codable, Sendable, Identifiable, Equatable {
    /// Stable identity for a list row. Derived from the draft key, so the same
    /// report rejected twice does not stack up two entries.
    let id: String
    /// The full text the user wrote, so it is recoverable by copy/paste. This
    /// is the ONLY surviving copy once the draft leaves the queue.
    let description: String?
    let page: String?
    /// HTTP status the server answered with.
    let statusCode: Int
    /// What to tell the user, in their terms.
    let reason: String
    let rejectedAt: Date
}

/// Durable local log of reports the server refused outright.
enum BugReportRejectionStore {
    private static let rejectionsKey = "bainluck_bug_report_rejections"
    private static let maxRejections = 5

    /// Injectable for tests; production always uses `.standard`.
    nonisolated(unsafe) static var defaults: UserDefaults = .standard

    /// Human-readable reason for a permanent refusal.
    ///
    /// Mirrors the server's own validators in `backend/app/routes/feedback.py`
    /// so the sentence names the actual limit rather than a status number.
    static func reason(forStatus code: Int) -> String {
        switch code {
        case 413:
            return "The screenshot was too large for the server to accept."
        case 422:
            return "The report was longer than the 5,000 characters the server accepts."
        case 401, 403:
            return "The server would not accept this report from this device."
        default:
            return "The server refused this report (error \(code))."
        }
    }

    @discardableResult
    static func record(
        draftKey: String,
        description: String?,
        page: String?,
        statusCode: Int,
        rejectedAt: Date = Date()
    ) -> BugReportRejection {
        let rejection = BugReportRejection(
            id: draftKey,
            description: description,
            page: page,
            statusCode: statusCode,
            reason: reason(forStatus: statusCode),
            rejectedAt: rejectedAt
        )
        var rejections = loadRejections()
        // Re-rejecting the same report replaces its entry rather than stacking.
        rejections.removeAll { $0.id == rejection.id }
        rejections.insert(rejection, at: 0)
        if rejections.count > maxRejections {
            rejections = Array(rejections.prefix(maxRejections))
        }
        if let data = try? JSONEncoder().encode(rejections) {
            defaults.set(data, forKey: rejectionsKey)
        }
        return rejection
    }

    /// All refused reports, newest first.
    static func loadRejections() -> [BugReportRejection] {
        guard let data = defaults.data(forKey: rejectionsKey),
              let rejections = try? JSONDecoder().decode([BugReportRejection].self, from: data) else {
            return []
        }
        return rejections
    }

    static var count: Int { loadRejections().count }

    static var mostRecent: BugReportRejection? { loadRejections().first }

    /// Discard one refused report. Only ever called from an explicit user tap —
    /// nothing in this file deletes a rejection on its own.
    static func discard(id: String) {
        var rejections = loadRejections()
        rejections.removeAll { $0.id == id }
        if rejections.isEmpty {
            clear()
        } else if let data = try? JSONEncoder().encode(rejections) {
            defaults.set(data, forKey: rejectionsKey)
        }
    }

    static func clear() {
        defaults.removeObject(forKey: rejectionsKey)
    }
}
