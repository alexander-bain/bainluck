import SwiftUI

/// Shared section-band header for `FeedView`, `LeagueGridView`, `SportCategoryView`,
/// and `MyStuffView` (`"Upcoming"`, `"Live Now"`, `"Just Happened"`, `"Pinned"`, etc.).
///
/// At `.accessibility5` on narrow phones (`320 pt`, `390 pt`), placing `Label(title, ...)`
/// inside a `List` section `HStack` caused UIKit/SwiftUI to hyphenate `"Upcoming"` across
/// multiple lines (`Up-com-ing`, `Upcom-ing`) and `"Just Happened"` (`Just / Hap-pened`).
/// Rendering an explicit `Image` + `ViewThatFits(in: .horizontal)` keeps the title on a
/// single line at ordinary sizes and scales individual words down cleanly instead of
/// breaking any word mid-syllable at extreme accessibility sizes.
struct SectionBandHeaderView: View {
    let title: String
    let systemImage: String
    let imageColor: Color
    let count: Int
    var countForeground: Color = DS.textSecondaryReadable

    nonisolated static func titleWords(_ title: String) -> [String] {
        title
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .split(whereSeparator: \.isWhitespace)
            .map(String.init)
    }

    nonisolated static func isSingleWord(_ title: String) -> Bool {
        titleWords(title).count <= 1
    }

    nonisolated static func splitTwoWordLines(for title: String) -> [String]? {
        let words = titleWords(title)
        guard words.count == 2 else { return nil }
        return words
    }

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: systemImage)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(imageColor)
                .dynamicTypeSize(...DynamicTypeSize.accessibility3)
                .accessibilityHidden(true)

            ViewThatFits(in: .horizontal) {
                titleLabel
                    .lineLimit(1)
                    .fixedSize(horizontal: true, vertical: false)

                narrowTitleView
            }
            .layoutPriority(1)

            Text("\(count)")
                .font(.caption2)
                .fontWeight(.medium)
                .foregroundStyle(countForeground)
                .dynamicTypeSize(...DynamicTypeSize.accessibility3)
                .padding(.horizontal, 5)
                .padding(.vertical, 1)
                .background(Color.secondary.opacity(0.12))
                .clipShape(Capsule())
                .fixedSize()

            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(title), \(count)")
        .accessibilityAddTraits(.isHeader)
    }

    private var titleLabel: some View {
        Text(title)
            .font(.subheadline)
            .fontWeight(.semibold)
            .foregroundStyle(imageColor)
            .textCase(nil)
    }

    @ViewBuilder
    private var narrowTitleView: some View {
        if let pair = Self.splitTwoWordLines(for: title) {
            VStack(alignment: .leading, spacing: 0) {
                ForEach(Array(pair.enumerated()), id: \.offset) { _, word in
                    Text(word)
                        .font(.subheadline)
                        .fontWeight(.semibold)
                        .foregroundStyle(imageColor)
                        .textCase(nil)
                        .lineLimit(1)
                        .allowsTightening(true)
                        .minimumScaleFactor(0.60)
                }
            }
        } else if Self.isSingleWord(title) {
            titleLabel
                .lineLimit(1)
                .allowsTightening(true)
                .minimumScaleFactor(0.60)
        } else {
            titleLabel
                .lineLimit(3)
                .allowsTightening(true)
                .minimumScaleFactor(0.65)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}
