import Foundation

/// Sensible groups, in the server's order. No bracket, favorite inference,
/// synthesized membership or assembly-result-to-reader-state translation.
nonisolated struct ContainerHubPresentation: Sendable {
    let response: ContainerHubResponse

    var title: String? {
        response.state == .published || response.state == .empty ? response.container?.name : nil
    }
    var sections: [ContainerHubSection] { response.sections }
    var children: [ContainerHubChild] { response.children.filter(\.canOpen) }
    var members: [ContainerHubMember] { sections.flatMap(\.members) }
    var isPartial: Bool {
        response.state == .published && (response.withheldCount > 0 || !response.withheld.isEmpty || sections.contains { $0.unavailableCount > 0 || $0.count != $0.members.count } || members.count != response.memberCount)
    }

    var note: String? {
        switch response.state {
        case .unpublished: return "This collection isn't available yet."
        case .withdrawn: return "This collection is no longer available."
        case .empty: return "There are no games or questions in this collection right now."
        case .unavailable: return "This collection isn't available right now."
        case .published:
            if isPartial { return "Some games or questions aren't available right now." }
            return members.isEmpty && children.isEmpty ? "No games or questions are available right now." : nil
        }
    }

    static func sectionTitle(_ sectionClass: String) -> String {
        switch sectionClass {
        case "match_winner": return "Games and winners"
        case "prop": return "Player and game questions"
        case "title": return "Championship"
        case "advancement": return "Advancement"
        case "side_question": return "More questions"
        case "doubles": return "Doubles"
        default: return "More"
        }
    }

    /// A related question is present AND linked to THIS event on both sides of
    /// the published contract. Season-long questions stay in their own section.
    func relatedQuestions(for member: ContainerHubMember) -> [ContainerHubMember] {
        guard case .event = member.card else { return [] }
        let ids = Set(member.questionIds)
        return members.filter { $0.type == "market" && ids.contains($0.memberId) && $0.eventId == member.memberId }
    }

    static func questionNeedsVerdictRows(_ market: SearchFuturesMarket) -> Bool {
        market.status == "resolved" || market.topOutcomes?.contains { $0.verdict(in: market) != nil } == true
    }

    @MainActor
    static func outcomeLabel(_ outcome: SearchFuturesOutcome, market: SearchFuturesMarket) -> String {
        if let verdict = outcome.verdict(in: market) { return verdict.label }
        if market.status == "resolved" { return "Result unavailable" }
        return outcome.probability.map { formatProbability($0) } ?? "Price unavailable"
    }
}

/// Held per screen, never globally by slug. Returning revalidates without
/// rebuilding the parent; revision changes only clear a removed anchor.
nonisolated struct ContainerHubReadingContext: Equatable, Sendable {
    private(set) var identity: ContainerHubResponse.Identity?
    var scrollMemberId: String?
    private(set) var selectedMemberId: String?

    mutating func open(_ member: ContainerHubMember) {
        selectedMemberId = member.id
    }

    mutating func accept(_ presentation: ContainerHubPresentation) {
        identity = presentation.response.identity
        let ids = Set(presentation.members.map(\.id) + presentation.children.map { "container:\($0.slug)" })
        if let scrollMemberId, !ids.contains(scrollMemberId) { self.scrollMemberId = nil }
        if let selectedMemberId, !ids.contains(selectedMemberId) { self.selectedMemberId = nil }
    }
}
