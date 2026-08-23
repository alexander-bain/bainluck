import Combine
import Foundation

/// A snapshot of a submitted or skipped judgment, used for undo.
///
/// ── `judgmentId` IS WHAT MAKES THIS AN UNDO (#2060 item 3) ────────────────────
///
/// Before UX-P117 this struct carried no id, and `undo()` only moved
/// `currentIndex` back. The row stayed in the gold set, the card stayed marked
/// reviewed, and a re-vote wrote a SECOND row for the same card — so the corpus
/// kept the mis-tap AND gained its correction, both weighted equally. "Undo" that
/// leaves the thing it undid in the dataset is the worst of the three options,
/// because it is the one that reads as fixed.
///
/// Nil for a skip, which wrote nothing and therefore has nothing to delete.
private struct UndoEntry {
    let index: Int
    let label: String
    let reasonTags: Set<String>
    let notes: String
    let judgmentId: Int?
    /// The card, so `undo()` can reverse `markReviewed` — without that the next
    /// `load()` filters the card out and it can never be re-graded.
    let item: DiscoverLabelingDebugItem?
}

@MainActor
final class DiscoverLabelingViewModel: ObservableObject {
    @Published private(set) var items: [DiscoverLabelingDebugItem] = []
    @Published private(set) var currentIndex = 0
    @Published private(set) var loading = false
    @Published private(set) var submitting = false
    @Published private(set) var error: String?
    @Published private(set) var submittedCount = 0
    @Published private(set) var labelCounts: [String: Int] = [:]
    @Published private(set) var loadSummary: String?
    @Published private(set) var canUndo = false
    /// True while a background top-up is in flight. Deliberately NOT `loading`:
    /// `loading` blanks the card for a full-screen spinner, and the whole point
    /// of the prefetch is that Alex never sees one mid-session.
    @Published private(set) var prefetching = false
    /// Gold-set progress (#2060 item 4). Nil until the first fetch resolves, and
    /// nil again is never written — a transient failure keeps the last good
    /// numbers rather than blanking the header mid-session.
    @Published private(set) var progress: LabelingProgress?

    private var feedRequestId: String?
    private let batchId = "native-review-\(UUID().uuidString)"
    /// When the user is authenticated, reviewer is set to their email so
    /// the server tracks reviewed state per-user. Falls back to "native".
    private var reviewer: String = "native"
    private let reviewedStorageKey = "discover_labeling_reviewed_keys_v1"
    private let pageSize = 100
    private let targetQueueSize = 40
    private let maxPagesPerLoad = 8
    /// Top up when this few cards remain. Four is roughly ten seconds of grading
    /// at Alex's measured cadence, which is comfortably longer than the fetch.
    private let prefetchThreshold = 4
    private var reviewedItemKeys: Set<String>
    private var itemFeedRequestIds: [String: String] = [:]
    private var userEmail: String?
    private var undoStack: [UndoEntry] = []
    /// The server has told us it has nothing new — `has_more: false` AND every
    /// row on the final page already reviewed. An error path never sets this, so
    /// a failed fetch can never be mistaken for a finished queue (gotcha #53).
    ///
    /// Published because `queueExhausted` derives from it: a top-up that returns
    /// nothing changes no other observable state, so without this the honest-empty
    /// state would not redraw until the next vote.
    @Published private(set) var serverDry = false

    init() {
        let stored = UserDefaults.standard.stringArray(forKey: reviewedStorageKey) ?? []
        reviewedItemKeys = Set(stored)
    }

    /// Called when the authenticated user changes. The server resolves
    /// "native" to the Bearer-authenticated email, but passing it
    /// explicitly keeps the load summary diagnostic accurate.
    func updateUserEmail(_ email: String?) {
        userEmail = email
        reviewer = email ?? "native"
    }

    var currentItem: DiscoverLabelingDebugItem? {
        guard currentIndex < items.count else { return nil }
        return items[currentIndex]
    }

    var reviewedCount: Int { min(currentIndex, items.count) }
    var remainingCount: Int { max(items.count - currentIndex, 0) }
    var localReviewedCount: Int { reviewedItemKeys.count }

    /// "You have judged everything fresh today" — ruling 027's honest-empty
    /// state, and only ever a SUCCESS.
    ///
    /// Computed rather than stored so it cannot go stale against the two facts it
    /// is made of. An undo pushes a card back onto the queue, and a stored flag
    /// would have left the finished state on screen over a card waiting to be
    /// re-graded.
    var queueExhausted: Bool { serverDry && remainingCount == 0 }

    func load() async {
        loading = true
        error = nil
        loadSummary = nil
        // A reload is a fresh question to the server, so the previous answer
        // stops counting. Left set, a dry flag from a spent session would
        // suppress the top-up that refills the new one.
        serverDry = false
        await fetchInto(reset: true)
        loading = false
        await refreshProgress()
    }

    /// Top up the queue without blanking the card (#2060 item 5).
    ///
    /// Guarded on `prefetching` rather than on `loading` so a foreground reload
    /// and a background top-up cannot append the same page twice.
    func prefetchIfNeeded() async {
        guard !prefetching, !loading, !serverDry else { return }
        guard remainingCount <= prefetchThreshold else { return }
        prefetching = true
        await fetchInto(reset: false)
        prefetching = false
    }

    /// One fetch path for both the foreground load and the background top-up.
    ///
    /// Two paths would be two dedup rules, and the dedup is the part that decides
    /// whether Alex re-grades a card he just graded.
    private func fetchInto(reset: Bool) async {
        do {
            var offset = 0
            var pagesLoaded = 0
            var loadedItems: [DiscoverLabelingDebugItem] = []
            // On a top-up, the cards already in hand are part of the dedup set —
            // otherwise page 1 comes back and the queue grows a second copy of
            // everything currently on screen.
            var seenKeys: Set<String> = reset ? [] : Set(items.map(reviewKey(for:)))
            var feedRequestIds: [String: String] = reset ? [:] : itemFeedRequestIds
            var sawAnyDebugItems = false
            var apiItemCount = 0
            var filteredReviewedCount = 0
            var filteredDuplicateCount = 0
            var serverReviewedKeyCount = 0
            var serverFilteredReviewedCount = 0
            var latestTotal = 0
            var latestHasMore = false
            var reachedEnd = false

            while pagesLoaded < maxPagesPerLoad && loadedItems.count < targetQueueSize {
                let response = try await APIClient.shared.fetchDiscoverLabelingFeed(
                    reviewer: reviewer,
                    offset: offset,
                    limit: pageSize
                )
                feedRequestId = response.feedRequestId
                sawAnyDebugItems = sawAnyDebugItems || !response.debugItems.isEmpty
                apiItemCount += response.debugItems.count
                latestTotal = response.total
                latestHasMore = response.hasMore
                if let reviewedFilter = response.reviewedFilter {
                    serverReviewedKeyCount = reviewedFilter.reviewedKeyCount
                    serverFilteredReviewedCount = reviewedFilter.filteredCount
                }

                for item in response.debugItems {
                    let key = reviewKey(for: item)
                    if reviewedItemKeys.contains(key) {
                        filteredReviewedCount += 1
                        continue
                    }
                    if seenKeys.contains(key) {
                        filteredDuplicateCount += 1
                        continue
                    }
                    loadedItems.append(item)
                    seenKeys.insert(key)
                    if let feedRequestId = response.feedRequestId {
                        feedRequestIds[key] = feedRequestId
                    }
                }

                pagesLoaded += 1
                guard response.hasMore else {
                    reachedEnd = true
                    break
                }
                offset = response.offset + max(response.limit, pageSize)
            }

            let fresh = Array(loadedItems.prefix(targetQueueSize))
            if reset {
                items = fresh
                currentIndex = 0
                // A reload re-samples the queue, so the undo history points at
                // indices in a list that no longer exists. The judgments it
                // referenced are still deletable from the web surface; what is
                // gone is this session's pointer into them.
                undoStack.removeAll()
                canUndo = false
            } else {
                items.append(contentsOf: fresh)
            }
            itemFeedRequestIds = feedRequestIds
            // ** EXHAUSTED IS A CLAIM ABOUT THE SERVER, NOT ABOUT THE SCREEN. **
            // `reachedEnd` means the server said `has_more: false`; an error path
            // never reaches here at all, so a failed fetch can no longer be
            // mistaken for a finished queue (gotcha #53 — an empty result is a
            // response shape, not a fact).
            serverDry = reachedEnd && fresh.isEmpty
            let reviewerLabel = reviewer == "native" ? "native (anonymous)" : reviewer
            let mode = reset ? "Loaded" : "Topped up"
            loadSummary = "\(mode) \(fresh.count) of \(apiItemCount) fetched; server-side reviewed \(serverFilteredReviewedCount) filtered (\(serverReviewedKeyCount) known, reviewer: \(reviewerLabel)), local-side reviewed \(filteredReviewedCount) filtered (\(reviewedItemKeys.count) known), \(filteredDuplicateCount) duplicate; pages \(pagesLoaded), total \(latestTotal), more \(latestHasMore ? "yes" : "no")."
            if reset && items.isEmpty && !sawAnyDebugItems {
                // Only the genuinely-empty case is an error. "Everything fresh is
                // already judged" is a SUCCESS and gets the honest-empty state,
                // not a red banner.
                error = "No debug feed items returned."
            }
        } catch let apiError as APIError {
            switch apiError {
            case .httpError(let code, _) where code == 403:
                self.error = "Admin access required. Sign in with an admin account and try again."
            case .decodingError:
                self.error = "Failed to decode debug feed response. The backend response format may have changed."
            default:
                self.error = apiError.localizedDescription
            }
        } catch {
            self.error = error.localizedDescription
        }
    }

    /// Refresh the gold-set meter. Never surfaces its own failure.
    ///
    /// A progress header is decoration on the labelling task; a red banner over a
    /// failed decoration fetch would interrupt the work it exists to encourage.
    /// The stale numbers stay on screen instead.
    func refreshProgress() async {
        do {
            progress = try await APIClient.shared.fetchLabelingProgress(reviewer: reviewer)
        } catch {
            // Intentionally silent — see above.
        }
    }

    func resetLocalReviewedCards() async {
        reviewedItemKeys.removeAll()
        UserDefaults.standard.removeObject(forKey: reviewedStorageKey)
        await load()
    }

    func skip() {
        guard currentIndex < items.count else { return }
        undoStack.append(
            UndoEntry(
                index: currentIndex,
                label: "skip",
                reasonTags: [],
                notes: "",
                judgmentId: nil,
                item: nil
            )
        )
        canUndo = true
        currentIndex += 1
    }

    /// Undo the last vote — the ROW, not just the pointer (#2060 item 3).
    ///
    /// ── THE DRIFT GATE IS RE-CHECKED, AND IT IS RE-CHECKED BY DOING NOTHING ───
    ///
    /// The queue's requirement is that undo cannot smuggle a stale verdict past
    /// the fingerprint. It cannot, and the mechanism is that this method does not
    /// touch `cardFingerprint`: the card returns to screen still holding the
    /// digest it was SAMPLED with, so a re-vote posts that digest and the server
    /// re-derives the card from live rows and 409s if it moved. Undo is a new
    /// write path into the gate, and it enters through the same front door.
    ///
    /// The failure mode this is written against is the tempting "fix": refreshing
    /// the fingerprint on undo so the re-vote cannot be refused. That would make
    /// undo the one path on which a stale card is gradeable, which is precisely
    /// the bypass P111's mutation M6 exists to prevent.
    func undo() async {
        guard let entry = undoStack.last else { return }

        // Delete first, pop second. If the delete fails the entry stays on the
        // stack and the button stays live, so a failed undo can be retried
        // instead of silently becoming a pointer rewind over a surviving row.
        if let judgmentId = entry.judgmentId {
            do {
                _ = try await APIClient.shared.deleteRankingJudgment(id: judgmentId)
            } catch let apiError as APIError {
                switch apiError {
                case .httpError(let code, _) where code == 404:
                    // Already gone — deleted from another surface. The intent is
                    // satisfied, so fall through and rewind.
                    break
                case .httpError(let code, _) where code == 403:
                    error = "Admin access required to undo."
                    return
                default:
                    error = "Could not undo: \(apiError.localizedDescription)"
                    return
                }
            } catch {
                self.error = "Could not undo: \(error.localizedDescription)"
                return
            }
        }

        undoStack.removeLast()
        currentIndex = entry.index
        if let item = entry.item {
            unmarkReviewed(item)
        }
        if entry.label != "skip" {
            submittedCount = max(submittedCount - 1, 0)
            if let count = labelCounts[entry.label] {
                let next = count - 1
                if next <= 0 {
                    labelCounts.removeValue(forKey: entry.label)
                } else {
                    labelCounts[entry.label] = next
                }
            }
        }
        canUndo = !undoStack.isEmpty
        error = nil
        await refreshProgress()
    }

    func submit(
        label: String,
        reasonTags: Set<String>,
        notes: String,
        betterThanPrevious: Bool,
        worseThanNext: Bool
    ) async -> Bool {
        guard let item = currentItem else { return false }
        submitting = true
        error = nil
        let previousName = betterThanPrevious && currentIndex > 0 ? items[currentIndex - 1].name : nil
        let nextName = worseThanNext && currentIndex + 1 < items.count ? items[currentIndex + 1].name : nil
        let request = RankingJudgmentRequest(
            secret: nil,
            surface: "native_discover",
            rankSeen: item.rank,
            itemType: item.type,
            marketId: item.type == "futures" ? item.id : nil,
            eventId: item.type == "event" ? item.id : nil,
            marketName: item.name,
            label: label,
            reasonTags: Array(reasonTags).sorted(),
            betterThan: previousName,
            worseThan: nextName,
            notes: notes.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty,
            scoreAtReview: item.score,
            categoryAtReview: item.category,
            archetypeAtReview: item.archetype,
            qualityClassAtReview: item.qualityClass,
            headlineAtReview: item.headline,
            feedRequestId: itemFeedRequestIds[reviewKey(for: item)] ?? feedRequestId,
            cardSnapshot: snapshot(for: item),
            reviewer: reviewer,
            // Round-trip only — never computed here (#1933). `?? ""` is a real
            // claim, not a fallback: see `RankingJudgmentRequest.cardFingerprint`
            // for why an absent key and an empty one must mean different things.
            cardFingerprint: item.cardFingerprint ?? ""
        )
        do {
            let response = try await APIClient.shared.submitRankingJudgment(request)
            markReviewed(item)
            undoStack.append(
                UndoEntry(
                    index: currentIndex,
                    label: label,
                    reasonTags: reasonTags,
                    notes: notes,
                    // The id the undo deletes. Without it the previous build's
                    // "undo" left the row behind.
                    judgmentId: response.id,
                    item: item
                )
            )
            canUndo = true
            submittedCount += 1
            labelCounts[label, default: 0] += 1
            currentIndex += 1
            submitting = false
            await refreshProgress()
            await prefetchIfNeeded()
            return true
        } catch let apiError as APIError {
            switch apiError {
            case .httpError(let code, _) where code == 403:
                self.error = "Admin access required to submit labels. Sign in with an admin account."
            case .httpError(let code, let body) where code == 409:
                // The refusal reaches the screen. A guard whose whole purpose is
                // to protect Alex's label budget cannot spend one of his labels
                // and then decline to say why — the web pass learned this in
                // UX-P110 and native inherits the lesson, not just the gate.
                self.error = Self.driftRefusalMessage(body)
                // Nothing was written, so the card must NOT be marked reviewed
                // and the queue must not advance. It stays on screen with the
                // reason above it; a reload re-samples it at the current price.
            default:
                self.error = apiError.localizedDescription
            }
        } catch {
            self.error = error.localizedDescription
        }
        submitting = false
        return false
    }

    /// What to tell the person whose tap was refused (#1933).
    ///
    /// Substring, not `JSONDecoder` — the same reasoning as
    /// `verdictRefusal` on web: the body may be truncated by the transport, and
    /// a truncated JSON does not decode, so reaching for a decoder here is how
    /// this returns the generic message in exactly the case it exists for.
    ///
    /// `static` and `nonisolated` so a test can drive it without the view model
    /// or the main actor.
    nonisolated static func driftRefusalMessage(_ body: String?) -> String {
        let text = body ?? ""
        if text.contains("card_drifted") {
            return "This question re-priced while you were reading it — nothing was recorded. Reload to grade the current card."
        }
        if text.contains("card_fingerprint_missing") {
            return "This card was loaded before its current price — nothing was recorded. Reload to grade the current card."
        }
        return "This card went stale before the label landed — nothing was recorded. Reload and try again."
    }

    private func reviewKey(for item: DiscoverLabelingDebugItem) -> String {
        if let id = item.id {
            return "\(item.type):\(id)"
        }
        return "\(item.type):name:\(item.name.lowercased())"
    }

    private func markReviewed(_ item: DiscoverLabelingDebugItem) {
        reviewedItemKeys.insert(reviewKey(for: item))
        persistReviewedKeys()
    }

    /// Reverse of `markReviewed`, for undo. Without this the undone card is
    /// filtered out of the very next `load()` and can never be re-graded.
    private func unmarkReviewed(_ item: DiscoverLabelingDebugItem) {
        reviewedItemKeys.remove(reviewKey(for: item))
        persistReviewedKeys()
    }

    private func persistReviewedKeys() {
        UserDefaults.standard.set(
            Array(Array(reviewedItemKeys).suffix(1_000)),
            forKey: reviewedStorageKey
        )
    }

    private func snapshot(for item: DiscoverLabelingDebugItem) -> DiscoverLabelingCardSnapshot {
        DiscoverLabelingCardSnapshot(
            schemaVersion: "discover-card-v1",
            batchId: batchId,
            feedRequestId: feedRequestId,
            rank: item.rank,
            itemType: item.type,
            itemId: item.id,
            marketId: item.type == "futures" ? item.id : nil,
            eventId: item.type == "event" ? item.id : nil,
            name: item.name,
            source: item.source,
            category: item.category,
            archetype: item.archetype,
            qualityClass: item.qualityClass,
            headline: item.headline,
            reason: item.reason,
            context: item.context ?? item.reason,
            hookDescription: item.hookDescription,
            imageUrl: item.imageUrl,
            storyKey: item.storyKey,
            familyKey: item.familyKey,
            groupId: item.groupId,
            score: item.score,
            renderedProbability: item.renderedProbability,
            topOutcomes: Array((item.topOutcomes ?? []).prefix(5)),
            reasons: Array((item.reasons ?? []).prefix(12)),
            hasHook: item.hook ?? false,
            hasImage: item.image ?? false,
            explanationOk: item.explanationOk ?? false
        )
    }
}

private extension String {
    var nilIfEmpty: String? {
        isEmpty ? nil : self
    }
}
