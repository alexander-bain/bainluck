import Foundation

/// #9653 consumes the server's placed collection card. No inventory, clock-based
/// edition selection, score bonus or additional network read belongs here.
enum DiscoverCollectionFeed {
    nonisolated static func entry(for card: ContainerHubCollection?) -> ContainerDiscoveryEntry? {
        guard let card, card.canOpen, card.id > 0, card.revision >= 1,
              !card.name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              card.edition.season > 0, card.gameCount >= 0, card.questionCount >= 0,
              card.gameCount > 0 || card.questionCount > 0 else { return nil }
        let season = card.edition.season
        guard let league = ContainerDiscoveryLeague(rawValue: card.edition.league) else { return nil }
        switch league {
        case .mlb:
            guard card.edition.kind == "mlb_postseason", card.edition.stage == nil,
                  card.edition.week == nil, card.slug == "mlb-\(season)-postseason" else { return nil }
        case .nfl:
            guard card.edition.kind == "nfl_week", let week = card.edition.week,
                  (1...99).contains(week) else { return nil }
            let prefix: String
            switch card.edition.stage {
            case "Regular Season": prefix = ""
            case "Pre Season": prefix = "preseason-"
            case "Post Season": prefix = "postseason-"
            default: return nil
            }
            guard card.slug == "nfl-\(season)-\(prefix)week-\(week)" else { return nil }
        }
        return ContainerDiscoveryEntry(collection: card)
    }

    nonisolated static func editionLabel(for entry: ContainerDiscoveryEntry) -> String {
        let edition = entry.collection.edition
        var parts = [edition.league.uppercased(), String(edition.season)]
        if let stage = edition.stage { parts.append(stage) }
        if let week = edition.week { parts.append("Week \(week)") }
        if edition.kind == "mlb_postseason" { parts.append("Postseason") }
        return parts.joined(separator: " · ")
    }

    // The two Discover consumers share this additive classification. Existing
    // cards still delegate to their unchanged canonical classifier.
    static func category(
        of item: FeedItem,
        bundleChild: (FeedBundle) -> FeedItem? = { $0.items.first }
    ) -> String {
        if let collection = item.collection {
            return collection.edition.league == "nfl" ? "americanfootball" : "baseball"
        }
        return DiscoverCategory.of(item, bundleChild: bundleChild)
    }

    static func family(
        of item: FeedItem,
        bundleChild: (FeedBundle) -> FeedItem? = { $0.items.first }
    ) -> String {
        if item.collection != nil { return category(of: item, bundleChild: bundleChild) }
        return DiscoverCategory.family(item, bundleChild: bundleChild)
    }

    static func isSportsFeedback(
        _ item: FeedItem,
        bundleChild: (FeedBundle) -> FeedItem? = { $0.items.first }
    ) -> Bool {
        item.collection != nil || DiscoverCategory.isSportsFeedback(item, bundleChild: bundleChild)
    }
}
