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

    private var feedRequestId: String?
    private let batchId = "native-review-\(UUID().uuidString)"
    private let reviewer = "native"
    private let reviewedStorageKey = "discover_labeling_reviewed_keys_v1"
    private var reviewedItemKeys: Set<String>

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

    func load(secret: String) async {
        guard !secret.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            error = "Enter an admin secret."
            return
        }
        loading = true
        error = nil
        do {
            let response = try await APIClient.shared.fetchDiscoverLabelingFeed(secret: secret)
            feedRequestId = response.feedRequestId
            items = response.debugItems.filter { !reviewedItemKeys.contains(reviewKey(for: $0)) }
            currentIndex = 0
            if items.isEmpty {
                error = response.debugItems.isEmpty ? "No debug feed items returned." : "No new debug feed items returned."
            }
        } catch {
            self.error = error.localizedDescription
        }
        loading = false
    }

    func skip() {
        guard currentIndex < items.count else { return }
        currentIndex += 1
    }

    func submit(
        secret: String,
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
            secret: secret,
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
            feedRequestId: feedRequestId,
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
