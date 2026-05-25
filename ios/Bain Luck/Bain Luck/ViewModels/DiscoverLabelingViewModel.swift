import Combine
import Foundation

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

    private var feedRequestId: String?
    private let batchId = "native-review-\(UUID().uuidString)"
    private let reviewer = "native"
    private let reviewedStorageKey = "discover_labeling_reviewed_keys_v1"
    private let pageSize = 100
    private let targetQueueSize = 40
    private let maxPagesPerLoad = 8
    private var reviewedItemKeys: Set<String>
    private var itemFeedRequestIds: [String: String] = [:]

    init() {
        let stored = UserDefaults.standard.stringArray(forKey: reviewedStorageKey) ?? []
        reviewedItemKeys = Set(stored)
    }

    var currentItem: DiscoverLabelingDebugItem? {
        guard currentIndex < items.count else { return nil }
        return items[currentIndex]
    }

    var reviewedCount: Int { min(currentIndex, items.count) }
    var remainingCount: Int { max(items.count - currentIndex, 0) }
    var localReviewedCount: Int { reviewedItemKeys.count }

    func load() async {
        loading = true
        error = nil
        loadSummary = nil
        do {
            var offset = 0
            var pagesLoaded = 0
            var loadedItems: [DiscoverLabelingDebugItem] = []
            var seenKeys: Set<String> = []
            var feedRequestIds: [String: String] = [:]
            var sawAnyDebugItems = false
            var apiItemCount = 0
            var filteredReviewedCount = 0
            var filteredDuplicateCount = 0
            var serverReviewedKeyCount = 0
            var serverFilteredReviewedCount = 0
            var latestTotal = 0
            var latestHasMore = false

            while pagesLoaded < maxPagesPerLoad && loadedItems.count < targetQueueSize {
                let response = try await APIClient.shared.fetchDiscoverLabelingFeed(
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
                guard response.hasMore else { break }
                offset = response.offset + max(response.limit, pageSize)
            }

            items = Array(loadedItems.prefix(targetQueueSize))
            itemFeedRequestIds = feedRequestIds
            currentIndex = 0
            loadSummary = "Loaded \(items.count) of \(apiItemCount) fetched; server filtered \(serverFilteredReviewedCount) reviewed (\(serverReviewedKeyCount) known), local filtered \(filteredReviewedCount) reviewed, \(filteredDuplicateCount) duplicate; pages \(pagesLoaded), total \(latestTotal), more \(latestHasMore ? "yes" : "no"). Local reviewed: \(reviewedItemKeys.count)."
            if items.isEmpty {
                error = sawAnyDebugItems ? "No new debug feed items returned." : "No debug feed items returned."
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
        loading = false
    }

    func resetLocalReviewedCards() async {
        reviewedItemKeys.removeAll()
        UserDefaults.standard.removeObject(forKey: reviewedStorageKey)
        await load()
    }

    func skip() {
        guard currentIndex < items.count else { return }
        currentIndex += 1
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
            reviewer: reviewer
        )
        do {
            _ = try await APIClient.shared.submitRankingJudgment(request)
            markReviewed(item)
            submittedCount += 1
            labelCounts[label, default: 0] += 1
            currentIndex += 1
            submitting = false
            return true
        } catch let apiError as APIError {
            switch apiError {
            case .httpError(let code, _) where code == 403:
                self.error = "Admin access required to submit labels. Sign in with an admin account."
            default:
                self.error = apiError.localizedDescription
            }
        } catch {
            self.error = error.localizedDescription
        }
        submitting = false
        return false
    }

    private func reviewKey(for item: DiscoverLabelingDebugItem) -> String {
        if let id = item.id {
            return "\(item.type):\(id)"
        }
        return "\(item.type):name:\(item.name.lowercased())"
    }

    private func markReviewed(_ item: DiscoverLabelingDebugItem) {
        reviewedItemKeys.insert(reviewKey(for: item))
        UserDefaults.standard.set(Array(Array(reviewedItemKeys).suffix(1_000)), forKey: reviewedStorageKey)
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
