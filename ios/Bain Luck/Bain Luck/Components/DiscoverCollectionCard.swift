import SwiftUI

/// A hub entry among ordinary Discover cards, using the same supplied name,
/// counts and canonical route as Browse. The feed owns relevance and placement.
struct DiscoverCollectionCard: View {
    let entry: ContainerDiscoveryEntry
    @Binding var navigationPath: NavigationPath
    var onOpen: (() -> Void)? = nil

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top, spacing: 12) {
                VStack(alignment: .leading, spacing: 6) {
                    Text("COLLECTION")
                        .font(.caption2.weight(.bold))
                        .tracking(0.8)
                        .foregroundStyle(DS.textSecondary)
                    Text(entry.collection.name)
                        .font(.headline.weight(.bold))
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                Image(systemName: "chevron.right")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DS.textMuted)
                    .accessibilityHidden(true)
            }
            Text(DiscoverCollectionFeed.editionLabel(for: entry))
                .font(.caption)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            Text(entry.subtitle)
                .font(.subheadline)
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 16))
        .overlay(RoundedRectangle(cornerRadius: 16).stroke(DS.border, lineWidth: 0.5))
        .contentShape(Rectangle())
        // As with group rows, a tap gesture lets a swipe finish as feedback
        // rather than navigating on touch-up through a NavigationLink.
        .onTapGesture {
            onOpen?()
            navigationPath.append(entry.route)
        }
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(.isButton)
        .accessibilityIdentifier("discover-collection-\(entry.id)")
    }
}
