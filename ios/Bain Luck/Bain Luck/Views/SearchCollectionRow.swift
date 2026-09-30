import SwiftUI

/// Search relevance and the two-card bound belong to the server. Validate only
/// the supplied edition/destination, using the unchanged Browse contract.
nonisolated enum SearchCollectionRows {
    static func entries(in response: SearchResponse) -> [ContainerDiscoveryEntry] {
        guard let discovery = response.collectionDiscovery else { return [] }
        var seen = Set<String>()
        return discovery.collections.compactMap { card in
            guard let league = ContainerDiscoveryLeague(rawValue: card.edition.league) else { return nil }
            let request = ContainerDiscoveryRequest(league: league, season: card.edition.season)
            guard let entry = request.entries(in: discovery).first(where: {
                $0.collection.id == card.id && $0.collection.slug == card.slug
            }), seen.insert(entry.id).inserted else { return nil }
            return entry
        }
    }

    static func editionLabel(for entry: ContainerDiscoveryEntry) -> String {
        let edition = entry.collection.edition
        if edition.league == "mlb" { return "MLB \(edition.season) · Postseason" }
        let stage: String
        switch edition.stage {
        case "Pre Season": stage = "Preseason "
        case "Post Season": stage = "Postseason "
        default: stage = ""
        }
        return "NFL \(edition.season) · \(stage)Week \(edition.week ?? 0)"
    }
}

struct SearchCollectionRow: View {
    let entry: ContainerDiscoveryEntry

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(entry.collection.name)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
            // The producer name ordinarily already states the edition. Spend a
            // second line on it only when the supplied name doesn't say it.
            let edition = SearchCollectionRows.editionLabel(for: entry)
            if entry.collection.name != edition {
                Text(edition).font(.caption).foregroundStyle(.secondary)
            }
            Text(entry.subtitle).font(.caption).foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .contentShape(Rectangle())
        .accessibilityIdentifier("search-collection-\(entry.id)")
    }
}
