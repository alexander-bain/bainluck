import Foundation

/// Additive #9636 reader contract, pinned to PR #9699's representative fixtures.
/// Publication and game lifecycle are separate: only `published` exposes members.
nonisolated struct ContainerHubResponse: Decodable, Sendable {
    enum Publication: String, Sendable {
        case published, unpublished, withdrawn, empty, unavailable
    }

    let state: Publication
    let slug: String
    let revision: Int?
    let reason: String?
    let subtitle: String?
    let edition: ContainerHubEdition?
    let container: ContainerHubHeader?
    let children: [ContainerHubChild]
    let sections: [ContainerHubSection]
    let memberCount: Int
    let withheld: [ContainerHubWithheld]
    let withheldCount: Int
    let assembled: Bool
    let knownClasses: [String]
    let counts: ContainerHubCounts?
    let page: ContainerHubPage?
    let revisionMoved: Bool
    let pairedMetricSet: PairedMetricSet?

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        state = Publication(rawValue: try c.decodeIfPresent(String.self, forKey: .state) ?? "") ?? .unpublished
        slug = try c.decode(String.self, forKey: .slug)
        revision = try c.decodeIfPresent(Int.self, forKey: .revision)
        if state == .published && revision == nil {
            throw DecodingError.dataCorruptedError(forKey: .revision, in: c, debugDescription: "Published membership requires its revision")
        }
        reason = try c.decodeIfPresent(String.self, forKey: .reason)
        subtitle = try c.decodeIfPresent(String.self, forKey: .subtitle)
        edition = try c.decodeIfPresent(ContainerHubEdition.self, forKey: .edition)
        container = try c.decodeIfPresent(ContainerHubHeader.self, forKey: .container)
        // Fail closed even if a future server accidentally includes members in a
        // withdrawal. Never retain or reopen a previously published revision.
        children = state == .published ? try c.decode([ContainerHubChild].self, forKey: .children) : []
        sections = state == .published ? try c.decode([ContainerHubSection].self, forKey: .sections) : []
        memberCount = try c.decodeIfPresent(Int.self, forKey: .memberCount) ?? 0
        withheld = try c.decodeIfPresent([ContainerHubWithheld].self, forKey: .withheld) ?? []
        withheldCount = try c.decodeIfPresent(Int.self, forKey: .withheldCount) ?? 0
        assembled = try c.decodeIfPresent(Bool.self, forKey: .assembled) ?? false
        knownClasses = try c.decodeIfPresent([String].self, forKey: .knownClasses) ?? []
        counts = try c.decodeIfPresent(ContainerHubCounts.self, forKey: .counts)
        page = try c.decodeIfPresent(ContainerHubPage.self, forKey: .page)
        revisionMoved = try c.decodeIfPresent(Bool.self, forKey: .revisionMoved) ?? false
        pairedMetricSet = (try? c.decodeIfPresent(PairedMetricSet.self, forKey: .pairedMetricSet)) ?? nil
        if state == .published {
            let isRoundupMemberHub = edition == nil && container?.kind == "roundup"
            guard revision.map({ $0 > 0 }) == true,
                  edition?.matches(slug: slug) == true || isRoundupMemberHub,
                  container?.slug == slug, memberCount >= 0, withheldCount >= 0 else {
                throw DecodingError.dataCorruptedError(forKey: .edition, in: c, debugDescription: "Published collection identity is invalid")
            }
            if edition?.isTheme == true {
                guard let counts, let page, counts.shownCount >= memberCount,
                      counts.eligibleCount >= counts.shownCount, counts.withheldCount.values.allSatisfy({ $0 >= 0 }),
                      (1...100).contains(page.limit), page.nextCursor.map(ContainerHubPage.validCursor) ?? true else {
                    throw DecodingError.dataCorruptedError(forKey: .counts, in: c, debugDescription: "Theme page requires valid full-inventory counts and cursor")
                }
            }
        }
    }

    private enum CodingKeys: String, CodingKey {
        case state, slug, revision, reason, subtitle, edition, container, children, sections
        case memberCount, withheld, withheldCount, assembled, knownClasses, counts, page, revisionMoved
        case pairedMetricSet
    }

    /// Preserve the accepted page inventory while replacing its fresh envelope.
    init(envelope: ContainerHubResponse, sections: [ContainerHubSection], memberCount: Int, page: ContainerHubPage?, withheld: [ContainerHubWithheld], withheldCount: Int) {
        state = envelope.state; slug = envelope.slug; revision = envelope.revision; reason = envelope.reason
        subtitle = envelope.subtitle
        edition = envelope.edition; container = envelope.container; children = envelope.children
        self.sections = sections; self.memberCount = memberCount; self.page = page
        self.withheld = withheld; self.withheldCount = withheldCount; assembled = envelope.assembled
        knownClasses = envelope.knownClasses; counts = envelope.counts; revisionMoved = envelope.revisionMoved
        pairedMetricSet = envelope.pairedMetricSet
    }

    var identity: Identity { Identity(slug: slug, revision: revision) }
    nonisolated struct Identity: Hashable, Sendable {
        let slug: String
        let revision: Int?
    }
}

nonisolated struct ContainerHubEdition: Decodable, Equatable, Sendable {
    let kind: String
    let league: String?
    let season: Int?
    let stage: String?
    let week: Int?
    let subject: String?
    let edition: Int?

    var isTheme: Bool { kind == "theme_continuing" || kind == "theme_edition" }
    func matches(slug: String) -> Bool {
        if isTheme {
            guard let subject, !subject.isEmpty else { return false }
            if kind == "theme_continuing" { return slug == subject }
            return edition.map { $0 > 0 && slug == "\(subject)-\($0)" } ?? false
        }
        guard let season, season > 0 else { return false }
        switch kind {
        case "nfl_season": return league == "nfl" && slug == "nfl-\(season)"
        case "mlb_postseason": return league == "mlb" && slug == "mlb-\(season)-postseason"
        case "nfl_week":
            guard league == "nfl", let week, (1...99).contains(week) else { return false }
            let prefix: String
            switch stage {
            case "Regular Season": prefix = ""
            case "Pre Season": prefix = "preseason-"
            case "Post Season": prefix = "postseason-"
            default: return false
            }
            return slug == "nfl-\(season)-\(prefix)week-\(week)"
        default: return false
        }
    }
}

nonisolated struct ContainerHubCounts: Decodable, Sendable {
    let shownCount: Int
    let eligibleCount: Int
    let withheldCount: [String: Int]
    let inventoryComplete: Bool
}

nonisolated struct ContainerHubPage: Decodable, Sendable {
    let limit: Int
    let nextCursor: String?
    static func validCursor(_ value: String) -> Bool {
        !value.isEmpty && value.count <= 64 && value.unicodeScalars.allSatisfy {
            CharacterSet(charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-").contains($0)
        }
    }
}

nonisolated struct ContainerHubHeader: Decodable, Sendable {
    let id: Int
    let kind: String?
    let name: String
    let slug: String
    let category: String?
    let status: String?
    let windowStart: String?
    let windowEnd: String?
    let parentContainerId: Int?
}

nonisolated struct ContainerHubDestination: Decodable, Sendable {
    let kind: String
    let id: Int?
    let slug: String?
    let web: String?
    let api: String

    func matches(type: String, id: Int) -> Bool {
        guard id > 0, self.kind == type, self.id == id else { return false }
        switch type {
        case "event": return api == "/api/events/\(id)"
        case "market": return api == "/api/futures/\(id)"
        default: return false
        }
    }

    func matchesContainer(slug: String) -> Bool {
        kind == "container" && self.slug == slug && api == "/api/containers/\(slug)"
    }
}

nonisolated struct ContainerHubChild: Decodable, Identifiable, Sendable {
    let id: Int
    let name: String
    let slug: String
    let status: String?
    let publicationState: String?
    let edition: ContainerHubEdition?
    let destination: ContainerHubDestination?

    var canOpen: Bool {
        publicationState == "published" && destination?.matchesContainer(slug: slug) == true
    }
}

nonisolated struct ContainerHubSection: Decodable, Sendable {
    let sectionClass: String
    let title: String?
    let note: String?
    let layout: String?
    let count: Int
    let slots: [ContainerHubMemberSlot]
    let visualBlock: MachineryVisualBlock?

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        sectionClass = try c.decode(String.self, forKey: .sectionClass)
        title = try c.decodeIfPresent(String.self, forKey: .title)
        note = try c.decodeIfPresent(String.self, forKey: .note)
        layout = try c.decodeIfPresent(String.self, forKey: .layout)
        slots = try c.decode([ContainerHubMemberSlot].self, forKey: .members)
        count = try c.decodeIfPresent(Int.self, forKey: .count) ?? slots.count
        visualBlock = (try? c.decodeIfPresent(MachineryVisualBlock.self, forKey: .visualBlock))
            ?? (try? c.decodeIfPresent(MachineryVisualBlock.self, forKey: .visualBlockSnake))
    }

    private enum CodingKeys: String, CodingKey {
        case sectionClass = "class"
        case title, note, layout, count, members
        case visualBlock
        case visualBlockSnake = "visual_block"
    }

    init(
        sectionClass: String,
        title: String? = nil,
        note: String? = nil,
        layout: String? = nil,
        count: Int,
        slots: [ContainerHubMemberSlot],
        visualBlock: MachineryVisualBlock? = nil
    ) {
        self.sectionClass = sectionClass
        self.title = title
        self.note = note
        self.layout = layout
        self.count = count
        self.slots = slots
        self.visualBlock = visualBlock
    }

    var members: [ContainerHubMember] { slots.compactMap(\.member).filter(\.canOpen) }
    var unavailableCount: Int { slots.count - members.count }
}

/// One malformed or newer card must not erase healthy siblings, or masquerade
/// as an empty collection. Its absence is counted by the presentation.
nonisolated struct ContainerHubMemberSlot: Decodable, Sendable {
    let member: ContainerHubMember?
    init(from decoder: Decoder) throws {
        member = try? ContainerHubMember(from: decoder)
    }
}

nonisolated struct ContainerHubMember: Decodable, Identifiable, Sendable {
    enum Card: Sendable {
        case event(FeedEventData)
        // Search carries verdicts; feed carries imagery, hooks and familiar-card fields.
        // Both are decoded from the SAME card, not from a second endpoint or name match.
        case question(FeedFuturesData, SearchFuturesMarket)
        case unsupported
    }

    let type: String
    let memberId: Int
    let containerId: Int?
    let source: String?
    let confidence: Double?
    let destination: ContainerHubDestination?
    let card: Card
    let questionIds: [Int]
    let eventId: Int?

    var id: String { "\(type):\(memberId)" }
    var canOpen: Bool {
        guard destination?.matches(type: type, id: memberId) == true else { return false }
        switch card {
        case .event(let event): return type == "event" && event.id == memberId
        case .question(let feed, let search): return type == "market" && feed.id == memberId && search.id == memberId
        case .unsupported: return false
        }
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        type = try c.decode(String.self, forKey: .type)
        memberId = try c.decode(Int.self, forKey: .id)
        containerId = try c.decodeIfPresent(Int.self, forKey: .containerId)
        source = try c.decodeIfPresent(String.self, forKey: .source)
        confidence = try c.decodeIfPresent(Double.self, forKey: .confidence)
        destination = try c.decodeIfPresent(ContainerHubDestination.self, forKey: .destination)
        questionIds = try c.decodeIfPresent([Int].self, forKey: .questionIds) ?? []
        eventId = try c.decodeIfPresent(Int.self, forKey: .eventId)
        switch type {
        case "event": card = .event(try c.decode(FeedEventData.self, forKey: .card))
        case "market":
            card = .question(try c.decode(FeedFuturesData.self, forKey: .card), try c.decode(SearchFuturesMarket.self, forKey: .card))
        default: card = .unsupported
        }
    }

    private enum CodingKeys: String, CodingKey {
        case type, id, containerId, source, confidence, destination, card, questionIds, eventId
    }
}

nonisolated struct ContainerHubWithheld: Decodable, Sendable {
    let type: String?
    let id: Int?
    let reason: String
}

/// Exact #9653 producer card. This is NOT a fabricated Browse endpoint: Search,
/// Browse or Discover can hand this additive card to ContainerHubCollectionLink.
nonisolated struct ContainerHubCollection: Decodable, Identifiable, Sendable {
    let type: String
    let id: Int
    let name: String
    let text: String
    let slug: String
    let state: String
    let revision: Int
    let edition: ContainerHubEdition
    let status: String?
    let gameCount: Int
    let questionCount: Int
    let matchedEventIds: [Int]
    let destination: ContainerHubDestination

    var canOpen: Bool {
        type == "collection" && state == "published" && destination.matchesContainer(slug: slug)
    }
}
