import Combine
import SwiftUI

// MARK: - Decision 364: A — Single-Screen Five-Row First-Run Checklist (#11934)

private enum ChecklistColumn364A {
    static let maxWidth: CGFloat = 680
}

private extension View {
    func checklistReadableColumn364A(alignment: Alignment = .leading) -> some View {
        self
            .frame(maxWidth: ChecklistColumn364A.maxWidth, alignment: alignment)
            .frame(maxWidth: .infinity)
    }
}

/// Shared live thumbnail helper that checks `machineryPreloadedImages12288` first
/// (making offline simulator renders crisp and network-free), then falls back to
/// `AsyncImage` over HTTPS, or a tinted SF Symbol badge when no URL is served.
struct ChecklistThumbnail364A: View {
    let urlString: String?
    let sfSymbol: String
    let accentHex: String
    var size: CGFloat = 38

    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.machineryPreloadedImages12288) private var preloadedImages

    private var tint: Color {
        Color(hex: MyStuffTeamTextColour.probabilityHex(accentHex, colorScheme: colorScheme))
    }

    var body: some View {
        Group {
            if let urlString, let url = URL(string: urlString), let preloaded = preloadedImages[url.absoluteString] {
                #if canImport(UIKit)
                Image(uiImage: preloaded)
                    .resizable()
                    .scaledToFill()
                #elseif canImport(AppKit)
                Image(nsImage: preloaded)
                    .resizable()
                    .scaledToFill()
                #endif
            } else if let urlString, let url = URL(string: urlString), url.scheme?.lowercased() == "https" {
                AsyncImage(url: url) { phase in
                    if case .success(let image) = phase {
                        image
                            .resizable()
                            .scaledToFill()
                    } else {
                        fallbackIcon
                    }
                }
            } else {
                fallbackIcon
            }
        }
        .frame(width: size, height: size)
        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .stroke(DS.border, lineWidth: 1)
        )
    }

    private var fallbackIcon: some View {
        ZStack {
            tint.opacity(colorScheme == .dark ? 0.22 : 0.12)
            Image(systemName: sfSymbol)
                .font(.system(size: max(13, size * 0.38), weight: .semibold))
                .foregroundStyle(tint)
        }
    }
}

/// Main first screen under Decision 364: A & 398: A — five optional rows on one screen (any order)
/// and one `"Skip"` exit.
struct FirstRunChecklistView364A: View {
    let content: FirstRunChecklistContent364A
    @Binding var state: FirstRunChecklistState364A
    var onSkipOrFinish: () -> Void = {}
    var onOpenRow: (FirstRunChecklistRowID364A) -> Void = { _ in }

    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    private var solidButtonForeground: Color {
        colorScheme == .dark ? Color(hex: "#0F172A") : .white
    }

    var body: some View {
        VStack(spacing: 0) {
            VStack(alignment: .leading, spacing: 8) {
                topBar
                if !dynamicTypeSize.isAccessibilitySize {
                    headerBlock
                }
            }
            .padding(.horizontal, 16)
            .padding(.top, 8)
            .padding(.bottom, 8)
            .frame(maxWidth: 680, alignment: .leading)
            .frame(maxWidth: .infinity)
            .background(DS.surface)

            #if os(iOS)
            GeometryReader { proxy in
                checklistScrollBody(columnWidth: min(680, max(1, proxy.size.width)))
            }
            #else
            checklistScrollBody(columnWidth: nil)
            #endif

            if state.completedCount >= state.totalCount {
                doneFooter
            }
        }
        .background(DS.surface)
        #if os(iOS)
        .toolbar(.hidden, for: .navigationBar)
        #endif
        .accessibilityIdentifier("checklist364A.root")
    }

    @ViewBuilder
    private func checklistScrollBody(columnWidth: CGFloat?) -> some View {
        ScrollView {
            let column = VStack(alignment: .leading, spacing: 11) {
                if dynamicTypeSize.isAccessibilitySize {
                    headerBlock
                }
                rowsCard
            }
            .padding(.horizontal, 16)
            .padding(.top, 2)
            .padding(.bottom, 14)

            if let columnWidth {
                column
                    .frame(width: columnWidth, alignment: .leading)
                    .frame(maxWidth: .infinity)
            } else {
                column
                    .frame(maxWidth: 680, alignment: .leading)
                    .frame(maxWidth: .infinity)
            }
        }
        .scrollBounceBehavior(.basedOnSize)
    }

    private var topBar: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 10) {
                brandWordmark
                    .fixedSize(horizontal: true, vertical: false)
                Spacer(minLength: 8)
                topBarTrailingControls
            }

            VStack(alignment: .leading, spacing: 6) {
                HStack(spacing: 10) {
                    brandWordmark
                        .fixedSize(horizontal: true, vertical: false)
                    Spacer(minLength: 6)
                    if state.completedCount < state.totalCount {
                        skipButton
                    }
                }
                if state.completedCount > 0 {
                    progressBadgeView
                }
            }

            VStack(alignment: .leading, spacing: 6) {
                brandWordmark
                    .fixedSize(horizontal: true, vertical: false)
                HStack(spacing: 8) {
                    topBarTrailingControls
                }
            }
        }
    }

    private var brandWordmark: some View {
        HStack(spacing: 6) {
            BainLuckMarkView(size: 20)
            Text("Bain Luck")
                .font(.headline.weight(.bold))
                .foregroundStyle(DS.textPrimary)
                .lineLimit(1)
        }
    }

    @ViewBuilder
    private var topBarTrailingControls: some View {
        if state.completedCount > 0 {
            progressBadgeView
        }
        if state.completedCount < state.totalCount {
            skipButton
        }
    }

    private var progressBadgeView: some View {
        Text(state.progressText)
            .font(.caption.weight(.semibold))
            .foregroundStyle(DS.blueReadable)
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(DS.blueReadable.opacity(colorScheme == .dark ? 0.18 : 0.10), in: Capsule())
            .fixedSize(horizontal: true, vertical: false)
            .accessibilityIdentifier("checklist364A.progressBadge")
    }

    private var skipButton: some View {
        Button("Skip", action: onSkipOrFinish)
            .font(.subheadline.weight(.semibold))
            .foregroundStyle(DS.textSecondaryReadable)
            .padding(.horizontal, 14)
            .frame(minHeight: 34)
            .background(DS.cardBg, in: Capsule())
            .overlay(Capsule().stroke(DS.border, lineWidth: 1))
            .buttonStyle(.plain)
            .fixedSize(horizontal: true, vertical: false)
            .accessibilityIdentifier("checklist364A.skipButton")
    }

    private var headerBlock: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Start anywhere")
                .font(.title2.weight(.bold))
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)

            if dynamicTypeSize < .accessibility4 {
                Text(FirstRunChecklistContent364A.butlerQuote)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondaryReadable)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("checklist364A.butlerQuote")
            }
        }
    }

    private var rowsCard: some View {
        let syncLit = state.isSyncLitUp
        let syncPreview = FirstRunChecklistRowPreview364A(
            subtitle: syncLit ? "Sign in to sync across devices" : "Follow something first",
            percentText: nil,
            imageUrl: syncLit ? (content.followRowPreview?.imageUrl ?? content.setsRowPreview?.imageUrl) : nil,
            sfSymbol: "laptopcomputer.and.iphone",
            accentHex: "#005CC2"
        )
        return VStack(spacing: 0) {
            standardRow(
                row: .lookUp,
                preview: content.lookupRowPreview,
                lit: true,
                mutedNote: nil,
                badgePillText: nil
            )
            Divider().padding(.leading, 14)
            standardRow(
                row: .follow,
                preview: content.followRowPreview,
                lit: true,
                mutedNote: nil,
                badgePillText: nil
            )
            Divider().padding(.leading, 14)
            standardRow(
                row: .exploreSets,
                preview: content.setsRowPreview,
                lit: true,
                mutedNote: nil,
                badgePillText: nil
            )
            Divider().padding(.leading, 14)
            standardRow(
                row: .syncDevices,
                preview: syncPreview,
                lit: syncLit,
                mutedNote: syncPreview.subtitle,
                badgePillText: syncLit ? "\(max(1, state.savedCount)) followed" : nil
            )
            Divider().padding(.leading, 14)
            standardRow(
                row: .alerts,
                preview: content.alertsRowPreview,
                lit: true,
                mutedNote: nil,
                badgePillText: nil
            )
        }
        .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(DS.border, lineWidth: 1)
        )
    }

    private func standardRow(
        row: FirstRunChecklistRowID364A,
        preview: FirstRunChecklistRowPreview364A?,
        lit: Bool,
        mutedNote: String?,
        badgePillText: String?
    ) -> some View {
        let isDone = state.completedRows.contains(row)
        let isRowLit = lit || isDone
        return Button {
            onOpenRow(row)
        } label: {
            HStack(spacing: 10) {
                ChecklistThumbnail364A(
                    urlString: preview?.imageUrl,
                    sfSymbol: preview?.sfSymbol ?? "checkmark",
                    accentHex: preview?.accentHex ?? "#005CC2",
                    size: 34
                )
                .opacity(isRowLit ? 1.0 : 0.42)

                VStack(alignment: .leading, spacing: 2) {
                    Text(row.title)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(isRowLit ? DS.textPrimary : DS.textSecondaryReadable)
                        .lineLimit(dynamicTypeSize.isAccessibilitySize ? nil : 1)
                        .minimumScaleFactor(dynamicTypeSize.isAccessibilitySize ? 1.0 : 0.84)
                        .fixedSize(horizontal: false, vertical: dynamicTypeSize.isAccessibilitySize)
                        .layoutPriority(1)

                    HStack(spacing: 6) {
                        if let note = mutedNote ?? preview?.subtitle, !note.isEmpty {
                            Text(note)
                                .font(.caption)
                                .foregroundStyle(isRowLit && row == .syncDevices ? DS.blueReadable : DS.textSecondaryReadable)
                                .lineLimit(dynamicTypeSize.isAccessibilitySize ? nil : 1)
                                .minimumScaleFactor(dynamicTypeSize.isAccessibilitySize ? 1.0 : 0.84)
                                .fixedSize(horizontal: false, vertical: dynamicTypeSize.isAccessibilitySize)
                        }
                        if let badgePillText {
                            Text(badgePillText)
                                .font(.caption2.weight(.bold).monospacedDigit())
                                .foregroundStyle(DS.blueReadable)
                                .padding(.horizontal, 7)
                                .padding(.vertical, 2)
                                .background(DS.blueReadable.opacity(colorScheme == .dark ? 0.18 : 0.10), in: Capsule())
                                .fixedSize(horizontal: true, vertical: false)
                        }
                    }
                }

                Spacer(minLength: 6)

                rowStatusIcon(isDone: isDone, enabled: isRowLit)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 9)
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier(row.accessibilityIdentifier)
    }

    @ViewBuilder
    private func rowStatusIcon(isDone: Bool, enabled: Bool = true) -> some View {
        if isDone {
            Image(systemName: "checkmark.circle.fill")
                .font(.title3.weight(.semibold))
                .foregroundStyle(DS.greenReadable)
        } else {
            Image(systemName: "chevron.right")
                .font(.footnote.weight(.semibold))
                .foregroundStyle(enabled ? DS.textSecondaryReadable : DS.textMuted)
        }
    }

    private var doneFooter: some View {
        VStack(spacing: 0) {
            Divider()
            Button(action: onSkipOrFinish) {
                Text("Go to Discover \u{2192}")
                    .font(.headline)
                    .foregroundStyle(solidButtonForeground)
                    .lineLimit(1)
                    .minimumScaleFactor(0.8)
                    .padding(.horizontal, 12)
                    .frame(maxWidth: .infinity, minHeight: 46)
                    .background(DS.blueReadable, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            }
            .buttonStyle(.plain)
            .padding(.horizontal, 16)
            .padding(.vertical, 9)
            .checklistReadableColumn364A(alignment: .center)
            .accessibilityIdentifier("checklist364A.goToDiscoverButton")
        }
        .background(DS.surface)
    }
}

/// Compact dismissible checklist sitting at the top of `My Stuff` (`"2 of 5 done"`)
/// until all 5 rows are finished or dismissed (`364: A`).
struct MyStuffChecklistBanner364A: View {
    @Binding var state: FirstRunChecklistState364A
    var onOpenRow: (FirstRunChecklistRowID364A) -> Void = { _ in }
    var onDismiss: (() -> Void)? = nil

    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    var body: some View {
        if state.showsInMyStuff {
            VStack(alignment: .leading, spacing: 10) {
                HStack(alignment: dynamicTypeSize.isAccessibilitySize ? .top : .center, spacing: 8) {
                    Text("Getting started \u{00B7} \(state.progressText)")
                        .font(.subheadline.weight(.bold))
                        .foregroundStyle(DS.textPrimary)
                        .lineLimit(dynamicTypeSize.isAccessibilitySize ? nil : 1)
                        .minimumScaleFactor(dynamicTypeSize.isAccessibilitySize ? 1.0 : 0.85)
                        .multilineTextAlignment(.leading)
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 4)
                    Button {
                        state.dismissedFromMyStuff = true
                        onDismiss?()
                    } label: {
                        Image(systemName: "xmark")
                            .font(.caption.weight(.bold))
                            .foregroundStyle(DS.textSecondaryReadable)
                            .frame(width: 28, height: 28)
                            .background(DS.trackBg, in: Circle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Dismiss checklist")
                    .accessibilityIdentifier("checklist364A.myStuffDismiss")
                }

                VStack(spacing: 6) {
                    ForEach(FirstRunChecklistRowID364A.allCases) { row in
                        let isDone = state.completedRows.contains(row)
                        let lit = (row != .syncDevices) || state.isSyncLitUp || isDone
                        Button {
                            onOpenRow(row)
                        } label: {
                            HStack(alignment: dynamicTypeSize.isAccessibilitySize ? .firstTextBaseline : .center, spacing: 8) {
                                Image(systemName: isDone ? "checkmark.circle.fill" : "circle")
                                    .font(.subheadline.weight(.semibold))
                                    .foregroundStyle(isDone ? DS.greenReadable : (lit ? DS.blueReadable : DS.textMuted))
                                Text(row.title)
                                    .font(.footnote.weight(isDone ? .medium : .semibold))
                                    .foregroundStyle(isDone ? DS.textSecondaryReadable : (lit ? DS.textPrimary : DS.textMuted))
                                    .lineLimit(dynamicTypeSize.isAccessibilitySize ? nil : 1)
                                    .minimumScaleFactor(dynamicTypeSize.isAccessibilitySize ? 1.0 : 0.84)
                                    .multilineTextAlignment(.leading)
                                    .fixedSize(horizontal: false, vertical: true)
                                Spacer(minLength: 4)
                                if !isDone {
                                    Image(systemName: "chevron.right")
                                        .font(.caption2.weight(.semibold))
                                        .foregroundStyle(DS.textSecondaryReadable)
                                }
                            }
                            .padding(.vertical, 4)
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .accessibilityIdentifier("checklist364A.myStuffRow.\(row.rawValue)")
                    }
                }
            }
            .padding(14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(DS.border, lineWidth: 1))
            .accessibilityIdentifier("checklist364A.myStuffBanner")
        }
    }
}

/// Sheet composite showing `MyStuffChecklistBanner364A` cleanly at the top of `MyStuffLandingView295A`.
struct MyStuffWithChecklistPreview364A: View {
    @Binding var state: FirstRunChecklistState364A
    @ObservedObject var landingVM: MyStuffLandingViewModel295A

    @State private var path = NavigationPath()

    var body: some View {
        NavigationStack(path: $path) {
            VStack(spacing: 0) {
                MyStuffChecklistBanner364A(state: $state)
                    .padding(.horizontal, 16)
                    .padding(.top, 12)
                    .padding(.bottom, 4)

                MyStuffLandingView295A(
                    landingVM: landingVM,
                    path: $path,
                    onOpenDiscover: {},
                    onManagePins: {},
                    onRefresh: {}
                )
            }
            .background(DS.surface)
        }
    }
}

// MARK: - Step 1: Look anything up

struct FirstRunLookupStepView364A: View {
    let examples: [FirstRunLookupExample364A]
    @Binding var query: String
    let results: [FirstRunLookupResult364A]
    var isSearching: Bool = false
    var hasSearched: Bool = false
    var searchFailed: Bool = false
    var onTapExample: (FirstRunLookupExample364A) -> Void = { _ in }
    var onSelectResult: (FirstRunLookupResult364A) -> Void = { _ in }
    var onRetrySearch: () -> Void = {}
    var onBack: () -> Void = {}
    var onDone: () -> Void = {}

    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @Environment(\.dismiss) private var dismiss

    private var trimmedQuery: String {
        query.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    var body: some View {
        VStack(spacing: 0) {
            StepTopBar364A(
                title: FirstRunChecklistRowID364A.lookUp.title,
                actionTitle: results.isEmpty && trimmedQuery.isEmpty ? "Skip" : "Done",
                onBack: {
                    onBack()
                    dismiss()
                },
                onAction: onDone
            )

            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    Text("No account needed \u{2014} search any game, team, award, or election.")
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondaryReadable)
                        .fixedSize(horizontal: false, vertical: true)

                    HStack(spacing: 8) {
                        Image(systemName: "magnifyingglass")
                            .font(.subheadline)
                            .foregroundStyle(DS.textSecondaryReadable)
                        TextField("Search anything", text: $query)
                            .textFieldStyle(.plain)
                            .submitLabel(.search)
                            .accessibilityIdentifier("checklist364A.lookup.searchField")
                        if !query.isEmpty {
                            Button {
                                query = ""
                            } label: {
                                Image(systemName: "xmark.circle.fill")
                                    .font(.subheadline)
                                    .foregroundStyle(DS.textSecondaryReadable)
                            }
                            .buttonStyle(.plain)
                            .accessibilityLabel("Clear search")
                        }
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 12)
                    .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(DS.blueReadable.opacity(0.45), lineWidth: 1.5))

                    // Fix d: show examples ONLY when the query is empty; once typing/example-tapped, the list IS the search result.
                    if trimmedQuery.isEmpty && !examples.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Try tonight\u{2019}s examples")
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(DS.textSecondaryReadable)

                            ForEach(examples.prefix(3)) { ex in
                                Button {
                                    onTapExample(ex)
                                } label: {
                                    HStack(spacing: 10) {
                                        ChecklistThumbnail364A(
                                            urlString: ex.imageUrl,
                                            sfSymbol: ex.sfSymbol,
                                            accentHex: "#005CC2",
                                            size: 32
                                        )
                                        VStack(alignment: .leading, spacing: 1) {
                                            Text(ex.badgeText.uppercased())
                                                .font(.caption2.weight(.bold))
                                                .foregroundStyle(DS.blueReadable)
                                            Text(ex.percent.map { "\(ex.title) \($0)%" } ?? ex.title)
                                                .font(.subheadline.weight(.medium))
                                                .foregroundStyle(DS.textPrimary)
                                                .multilineTextAlignment(.leading)
                                                .fixedSize(horizontal: false, vertical: true)
                                        }
                                        Spacer(minLength: 8)
                                        Image(systemName: "chevron.right")
                                            .font(.caption.weight(.semibold))
                                            .foregroundStyle(DS.textSecondaryReadable)
                                    }
                                    .padding(10)
                                    .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                                    .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(DS.border, lineWidth: 1))
                                }
                                .buttonStyle(.plain)
                                .accessibilityIdentifier("checklist364A.lookup.example.\(ex.kind.rawValue)")
                            }
                        }
                    }

                    if !trimmedQuery.isEmpty {
                        if isSearching && results.isEmpty {
                            HStack(spacing: 10) {
                                ProgressView()
                                Text("Searching\u{2026}")
                                    .font(.subheadline)
                                    .foregroundStyle(DS.textSecondaryReadable)
                            }
                            .frame(maxWidth: .infinity, alignment: .center)
                            .padding(.vertical, 24)
                        } else if !results.isEmpty {
                            VStack(spacing: 0) {
                                ForEach(Array(results.enumerated()), id: \.element.id) { idx, row in
                                    Button {
                                        onSelectResult(row)
                                    } label: {
                                        lookupResultRow(row)
                                            .padding(.horizontal, 12)
                                            .padding(.vertical, 10)
                                            .contentShape(Rectangle())
                                    }
                                    .buttonStyle(.plain)
                                    .accessibilityIdentifier("checklist364A.lookup.result.\(row.id)")
                                    if idx < results.count - 1 {
                                        Divider().padding(.leading, 56)
                                    }
                                }
                            }
                            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                            .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(DS.border, lineWidth: 1))
                        } else if searchFailed {
                            HStack(spacing: 12) {
                                Text("Search timed out or failed.")
                                    .font(.subheadline)
                                    .foregroundStyle(DS.textSecondaryReadable)
                                Spacer(minLength: 8)
                                Button("Try again", action: onRetrySearch)
                                    .font(.subheadline.weight(.semibold))
                                    .foregroundStyle(DS.blueReadable)
                                    .buttonStyle(.plain)
                            }
                            .padding(14)
                            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                            .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(DS.border, lineWidth: 1))
                        } else if hasSearched {
                            Text("No open markets matched \u{201C}\(trimmedQuery)\u{201D}.")
                                .font(.subheadline)
                                .foregroundStyle(DS.textSecondaryReadable)
                                .padding(14)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                                .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(DS.border, lineWidth: 1))
                        }
                    }
                }
                .padding(16)
                .checklistReadableColumn364A()
            }
        }
        .background(DS.surface)
        #if os(iOS)
        .toolbar(.hidden, for: .navigationBar)
        #endif
    }

    @ViewBuilder
    private func lookupResultRow(_ row: FirstRunLookupResult364A) -> some View {
        let subtitleLine = row.subtitle.isEmpty ? row.badgeText : "\(row.badgeText) \u{00B7} \(row.subtitle)"
        if dynamicTypeSize.isAccessibilitySize {
            stackedLookupRow(row, subtitleLine: subtitleLine)
        } else {
            ViewThatFits(in: .horizontal) {
                sideBySideLookupRow(row, subtitleLine: subtitleLine)
                stackedLookupRow(row, subtitleLine: subtitleLine)
            }
        }
    }

    private func sideBySideLookupRow(_ row: FirstRunLookupResult364A, subtitleLine: String) -> some View {
        HStack(spacing: 12) {
            ChecklistThumbnail364A(
                urlString: row.imageUrl,
                sfSymbol: row.sfSymbol,
                accentHex: row.accentHex,
                size: 36
            )
            VStack(alignment: .leading, spacing: 2) {
                Text(row.title)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .lineLimit(1)
                    .fixedSize(horizontal: true, vertical: false)
                Text(subtitleLine)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondaryReadable)
                    .lineLimit(1)
                    .fixedSize(horizontal: true, vertical: false)
            }
            Spacer(minLength: 8)
            lookupAnswerView(row, multiline: false)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func stackedLookupRow(_ row: FirstRunLookupResult364A, subtitleLine: String) -> some View {
        HStack(alignment: .top, spacing: 12) {
            ChecklistThumbnail364A(
                urlString: row.imageUrl,
                sfSymbol: row.sfSymbol,
                accentHex: row.accentHex,
                size: 36
            )
            VStack(alignment: .leading, spacing: 4) {
                Text(row.title)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .multilineTextAlignment(.leading)
                    .fixedSize(horizontal: false, vertical: true)
                Text(subtitleLine)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondaryReadable)
                    .fixedSize(horizontal: false, vertical: true)
                lookupAnswerView(row, multiline: true)
                    .padding(.top, 2)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func lookupAnswerView(_ row: FirstRunLookupResult364A, multiline: Bool) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 5) {
            if !row.subjectLabel.isEmpty {
                Text(row.subjectLabel)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DS.textSecondaryReadable)
                    .lineLimit(multiline ? nil : 1)
                    .multilineTextAlignment(.leading)
                    .fixedSize(horizontal: !multiline, vertical: true)
            }
            Text("\(row.percent)%")
                .font(.headline.weight(.bold).monospacedDigit())
                .foregroundStyle(DS.blueReadable)
                .fixedSize(horizontal: true, vertical: false)
        }
    }
}

// MARK: - Step 2: Follow what you care about (teams, cities, schools, subjects w/ pictures + 359:A)

struct FirstRunFollowStepView364A: View {
    @ObservedObject var vm: FirstRunViewModel212A
    let subjectArtByCategory: [String: String]
    var onBack: () -> Void = {}
    var onDone: () -> Void = {}

    @Environment(\.followManager295A) private var followManager
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.dismiss) private var dismiss

    private var solidButtonForeground: Color {
        colorScheme == .dark ? Color(hex: "#0F172A") : .white
    }

    private var picturedSuggestions: [FirstRunSuggestion212A] {
        FirstRunSubjectArt364A.attachingPictures(to: vm.suggestions, subjectArt: subjectArtByCategory)
    }

    private var picturedPickedItems: [FirstRunSuggestion212A] {
        FirstRunSubjectArt364A.attachingPictures(to: vm.pickedItems, subjectArt: subjectArtByCategory)
    }

    var body: some View {
        VStack(spacing: 0) {
            StepTopBar364A(
                title: FirstRunChecklistRowID364A.follow.title,
                actionTitle: nil,
                onBack: {
                    onBack()
                    dismiss()
                },
                onAction: {}
            )

            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    Text("Teams, cities, schools, or just type what you like \u{2014} everything you follow lives in My Stuff.")
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondaryReadable)
                        .fixedSize(horizontal: false, vertical: true)

                    if !picturedPickedItems.isEmpty {
                        FirstRunPickedChipFlow212A(spacing: 8) {
                            ForEach(picturedPickedItems) { picked in
                                Button {
                                    vm.toggleSuggestion(picked, followManager: followManager)
                                } label: {
                                    HStack(spacing: 6) {
                                        ChecklistThumbnail364A(
                                            urlString: picked.logoUrl,
                                            sfSymbol: FirstRunCard212A.sfSymbol(forCategory: picked.affinityCategory ?? picked.sportOrCategoryLabel, isSports: picked.sportKey != nil),
                                            accentHex: picked.primaryColorHex ?? "#005CC2",
                                            size: 20
                                        )
                                        Text(picked.chipDisplayText)
                                            .font(.footnote.weight(.semibold))
                                            .foregroundStyle(solidButtonForeground)
                                            .fixedSize(horizontal: false, vertical: true)
                                        Image(systemName: "xmark")
                                            .font(.caption2.weight(.bold))
                                            .foregroundStyle(solidButtonForeground.opacity(0.8))
                                    }
                                    .padding(.horizontal, 10)
                                    .padding(.vertical, 6)
                                    .background(DS.textPrimary, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }

                    HStack(spacing: 8) {
                        Image(systemName: "magnifyingglass")
                            .font(.subheadline)
                            .foregroundStyle(DS.textSecondaryReadable)
                        TextField("Type a city, school, team, or topic", text: $vm.searchQuery, axis: .vertical)
                            .textFieldStyle(.plain)
                            .lineLimit(1...3)
                            .onChange(of: vm.searchQuery) { _, _ in
                                vm.onQueryChange(followManager: followManager)
                            }
                            .accessibilityIdentifier("checklist364A.follow.searchField")
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 12)
                    .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(DS.blueReadable.opacity(0.45), lineWidth: 1.5))

                    if vm.searchQuery.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !vm.servedExamples.isEmpty {
                        ScrollView(.horizontal, showsIndicators: false) {
                            HStack(spacing: 8) {
                                ForEach(vm.servedExamples) { ex in
                                    Button {
                                        vm.applyExampleQuery(ex.query)
                                    } label: {
                                        Text(ex.displayText)
                                            .font(.caption.weight(.semibold))
                                            .foregroundStyle(DS.blueReadable)
                                            .padding(.horizontal, 10)
                                            .padding(.vertical, 6)
                                            .background(DS.trackBg, in: Capsule())
                                            .overlay(Capsule().stroke(DS.border, lineWidth: 1))
                                    }
                                    .buttonStyle(.plain)
                                }
                            }
                        }
                    }

                    if FirstRunSentenceMode359A.isEnabledInBuild {
                        sentenceCardSection
                    }

                    if vm.isSearching && picturedSuggestions.isEmpty {
                        HStack(spacing: 10) {
                            ProgressView()
                            Text("Finding teams and subjects\u{2026}")
                                .font(.subheadline)
                                .foregroundStyle(DS.textSecondaryReadable)
                        }
                        .frame(maxWidth: .infinity, alignment: .center)
                        .padding(.vertical, 16)
                    } else if !picturedSuggestions.isEmpty {
                        VStack(spacing: 0) {
                            ForEach(Array(picturedSuggestions.enumerated()), id: \.element.id) { idx, item in
                                let picked = vm.isPicked(item)
                                Button {
                                    vm.toggleSuggestion(item, followManager: followManager)
                                } label: {
                                    HStack(spacing: 10) {
                                        ChecklistThumbnail364A(
                                            urlString: item.logoUrl,
                                            sfSymbol: FirstRunCard212A.sfSymbol(forCategory: item.affinityCategory ?? item.sportOrCategoryLabel, isSports: item.sportKey != nil),
                                            accentHex: item.primaryColorHex ?? "#005CC2",
                                            size: 32
                                        )
                                        VStack(alignment: .leading, spacing: 2) {
                                            Text(item.name)
                                                .font(.subheadline.weight(.semibold))
                                                .foregroundStyle(DS.textPrimary)
                                                .multilineTextAlignment(.leading)
                                                .fixedSize(horizontal: false, vertical: true)
                                            Text(item.rowSubtitleText)
                                                .font(.caption)
                                                .foregroundStyle(DS.textSecondaryReadable)
                                                .fixedSize(horizontal: false, vertical: true)
                                        }
                                        Spacer(minLength: 8)
                                        HStack(spacing: 4) {
                                            Image(systemName: picked ? "checkmark" : "plus")
                                                .font(.caption2.weight(.bold))
                                            Text(picked ? "Following" : "Follow")
                                                .font(.caption.weight(.bold))
                                        }
                                        .foregroundStyle(picked ? solidButtonForeground : DS.blueReadable)
                                        .padding(.horizontal, 12)
                                        .padding(.vertical, 6)
                                        .background(picked ? DS.textPrimary : DS.trackBg, in: Capsule())
                                    }
                                    .padding(.horizontal, 12)
                                    .padding(.vertical, 10)
                                    .contentShape(Rectangle())
                                }
                                .buttonStyle(.plain)
                                if idx < picturedSuggestions.count - 1 {
                                    Divider().padding(.leading, 54)
                                }
                            }
                        }
                        .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(DS.border, lineWidth: 1))
                    }
                }
                .padding(16)
                .checklistReadableColumn364A()
            }

            Divider()
            Button(action: onDone) {
                Text(vm.pickedItems.isEmpty ? "Skip" : "Done")
                    .font(.headline)
                    .foregroundStyle(solidButtonForeground)
                    .frame(maxWidth: .infinity, minHeight: 50)
                    .background(DS.blueReadable, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            }
            .buttonStyle(.plain)
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .checklistReadableColumn364A(alignment: .center)
            .background(DS.surface)
        }
        .background(DS.surface)
        #if os(iOS)
        .toolbar(.hidden, for: .navigationBar)
        #endif
    }

    @ViewBuilder
    private var sentenceCardSection: some View {
        if case .chips(let chips, let selectedIds, _) = vm.sentenceState {
            let clearChips = chips.filter { $0.ambiguityGroup == nil }
            let ambiguousGroups = Dictionary(grouping: chips.filter { $0.ambiguityGroup != nil }) { $0.ambiguityGroup ?? "" }
            VStack(alignment: .leading, spacing: 10) {
                Text("Confirm your picks")
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(DS.textPrimary)
                if !clearChips.isEmpty {
                    FirstRunPickedChipFlow212A(spacing: 8) {
                        ForEach(clearChips) { chip in
                            sentenceChipView(chip: chip, selected: selectedIds.contains(chip.id))
                        }
                    }
                }
                ForEach(ambiguousGroups.keys.sorted(), id: \.self) { groupName in
                    if let list = ambiguousGroups[groupName] {
                        Text("Which \u{201C}\(groupName)\u{201D}?")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(DS.textSecondaryReadable)
                        FirstRunPickedChipFlow212A(spacing: 8) {
                            ForEach(list) { chip in
                                sentenceChipView(chip: chip, selected: selectedIds.contains(chip.id))
                            }
                        }
                    }
                }
            }
            .padding(12)
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(DS.border, lineWidth: 1))
        }
    }

    private func sentenceChipView(chip: FirstRunSentenceChip359A, selected: Bool) -> some View {
        let art = FirstRunSubjectArt364A.imageURL(for: chip.suggestion, subjectArt: subjectArtByCategory)
        return Button {
            vm.toggleSentenceChip(chip, followManager: followManager)
        } label: {
            HStack(spacing: 6) {
                ChecklistThumbnail364A(
                    urlString: art,
                    sfSymbol: FirstRunCard212A.sfSymbol(forCategory: chip.suggestion.affinityCategory ?? chip.suggestion.sportOrCategoryLabel, isSports: chip.suggestion.sportKey != nil),
                    accentHex: chip.suggestion.primaryColorHex ?? "#005CC2",
                    size: 18
                )
                Text(chip.suggestion.chipDisplayText)
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(selected ? solidButtonForeground : DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                Image(systemName: selected ? "checkmark" : "plus")
                    .font(.caption2.weight(.bold))
                    .foregroundStyle(selected ? solidButtonForeground : DS.blueReadable)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(selected ? DS.textPrimary : DS.trackBg, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Step 3: See what the world expects (4–6 sets drawn in their real native forms)

struct FirstRunExploreSetsStepView364A: View {
    let sets: [FirstRunSetChoice364A]
    @Binding var selectedSlugs: Set<String>
    var isLoading: Bool = false
    var loadFailed: Bool = false
    var onRetry: () -> Void = {}
    var onBack: () -> Void = {}
    var onDone: () -> Void = {}

    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.dismiss) private var dismiss

    private var solidButtonForeground: Color {
        colorScheme == .dark ? Color(hex: "#0F172A") : .white
    }

    var body: some View {
        VStack(spacing: 0) {
            StepTopBar364A(
                title: FirstRunChecklistRowID364A.exploreSets.title,
                actionTitle: nil,
                onBack: {
                    onBack()
                    dismiss()
                },
                onAction: {}
            )

            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    Text("Pick a few to shape your Discover.")
                        .font(.subheadline.weight(.medium))
                        .foregroundStyle(DS.textSecondaryReadable)
                        .fixedSize(horizontal: false, vertical: true)

                    if isLoading && sets.isEmpty {
                        ProgressView("Loading sets\u{2026}")
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 32)
                    } else if sets.isEmpty && loadFailed {
                        HStack {
                            Text("Couldn\u{2019}t load sets right now.")
                                .font(.subheadline)
                                .foregroundStyle(DS.textSecondaryReadable)
                            Spacer()
                            Button("Try again", action: onRetry)
                                .font(.subheadline.weight(.semibold))
                                .foregroundStyle(DS.blueReadable)
                                .buttonStyle(.plain)
                        }
                        .padding(14)
                        .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                    } else {
                        ForEach(sets) { choice in
                            let selected = selectedSlugs.contains(choice.slug)
                            VStack(spacing: 6) {
                                Button {
                                    toggle(choice.slug)
                                } label: {
                                    HStack(spacing: 8) {
                                        Text(selected ? "Picked" : "Tap to pick")
                                            .font(.caption.weight(.semibold))
                                            .foregroundStyle(selected ? DS.blueReadable : DS.textSecondaryReadable)
                                        Spacer()
                                        Image(systemName: selected ? "checkmark.circle.fill" : "circle")
                                            .font(.title3.weight(.semibold))
                                            .foregroundStyle(selected ? DS.blueReadable : DS.textMuted)
                                            .accessibilityHidden(true)
                                    }
                                    .padding(.horizontal, 12)
                                    .padding(.vertical, 8)
                                    .background(selected ? DS.blueReadable.opacity(0.08) : DS.cardBg, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                                    .overlay(
                                        RoundedRectangle(cornerRadius: 10, style: .continuous)
                                            .stroke(selected ? DS.blueReadable : DS.border, lineWidth: selected ? 1.5 : 1)
                                    )
                                    .contentShape(Rectangle())
                                }
                                .buttonStyle(.plain)

                                MachineryDiscoverEntryCardView(
                                    card: choice.machineryCard,
                                    pairedMetricSet: choice.pairedMetricSet,
                                    onOpenContainer: { _, _ in toggle(choice.slug) },
                                    onOpenMarket: { _ in toggle(choice.slug) }
                                )
                                .overlay(
                                    RoundedRectangle(cornerRadius: 12, style: .continuous)
                                        .stroke(selected ? DS.blueReadable : Color.clear, lineWidth: 2.5)
                                )
                            }
                            .accessibilityIdentifier("checklist364A.set.\(choice.slug)")
                        }
                    }
                }
                .padding(16)
                .checklistReadableColumn364A()
            }

            Divider()
            Button(action: onDone) {
                Text(selectedSlugs.isEmpty ? "Skip" : "Done (\(selectedSlugs.count) picked)")
                    .font(.headline)
                    .foregroundStyle(solidButtonForeground)
                    .frame(maxWidth: .infinity, minHeight: 50)
                    .background(DS.blueReadable, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            }
            .buttonStyle(.plain)
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .checklistReadableColumn364A(alignment: .center)
            .background(DS.surface)
        }
        .background(DS.surface)
        #if os(iOS)
        .toolbar(.hidden, for: .navigationBar)
        #endif
    }

    private func toggle(_ slug: String) {
        if selectedSlugs.contains(slug) {
            selectedSlugs.remove(slug)
        } else {
            selectedSlugs.insert(slug)
        }
    }
}

// MARK: - Step 4 & Step 5: Sync Devices & Get a Heads-Up

struct FirstRunSignInStepView364A: View {
    var isSignedIn: Bool = false
    var isSigningIn: Bool = false
    var errorMessage: String? = nil
    var onAppleSignIn: () -> Void = {}
    var onGoogleSignIn: () -> Void = {}
    var onBackOrSkip: () -> Void = {}

    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(spacing: 0) {
            StepTopBar364A(
                title: FirstRunChecklistRowID364A.syncDevices.title,
                actionTitle: nil,
                onBack: {
                    onBackOrSkip()
                    dismiss()
                },
                onAction: {}
            )
            ScrollView {
                VStack(spacing: 16) {
                    if isSignedIn {
                        VStack(alignment: .leading, spacing: 10) {
                            HStack(spacing: 8) {
                                Image(systemName: "checkmark.circle.fill")
                                    .font(.title3.weight(.semibold))
                                    .foregroundStyle(DS.greenReadable)
                                Text("Signed in and syncing across your devices")
                                    .font(.headline.weight(.bold))
                                    .foregroundStyle(DS.textPrimary)
                            }
                            Text("Everything you follow on this iPhone stays backed up to your account.")
                                .font(.footnote)
                                .foregroundStyle(DS.textSecondaryReadable)
                            Button("Back to checklist", action: onBackOrSkip)
                                .font(.subheadline.weight(.semibold))
                                .foregroundStyle(DS.blueReadable)
                                .buttonStyle(.plain)
                        }
                        .padding(16)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(DS.border, lineWidth: 1))
                    } else {
                        EarnedSignInCard212A(
                            onAppleSignIn: onAppleSignIn,
                            onGoogleSignIn: onGoogleSignIn,
                            onDismissLocalOnly: onBackOrSkip,
                            isSigningIn: isSigningIn,
                            errorMessage: errorMessage
                        )
                    }
                }
                .padding(16)
                .checklistReadableColumn364A()
            }
        }
        .background(DS.surface)
        #if os(iOS)
        .toolbar(.hidden, for: .navigationBar)
        #endif
    }
}

struct FirstRunAlertsStepView364A: View {
    static let bigMoveThresholdPoints = 15

    var previewMover: FirstRunTonightCard364A? = nil
    var previewUpcomingGame: FirstRunTonightCard364A? = nil
    var alertsAlreadyOn: Bool = false
    var isBusy: Bool = false
    var onTurnOnAlerts: (() -> Void)? = nil
    var onNotNow: (() -> Void)? = nil
    var onBack: () -> Void = {}
    var onDone: () -> Void = {}

    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.dismiss) private var dismiss

    private var solidButtonForeground: Color {
        colorScheme == .dark ? Color(hex: "#0F172A") : .white
    }

    private var amberAccent: Color {
        Color(hex: MyStuffTeamTextColour.probabilityHex("#D97706", colorScheme: colorScheme))
    }

    private var qualifyingBigMover: FirstRunTonightCard364A? {
        guard let mover = previewMover,
              let pts = mover.deltaPoints,
              abs(pts) >= Self.bigMoveThresholdPoints,
              mover.deltaText != nil else {
            return nil
        }
        return mover
    }

    private var displayedExampleCard: FirstRunTonightCard364A? {
        qualifyingBigMover ?? previewUpcomingGame
    }

    private var exampleTitle: String {
        displayedExampleCard?.title ?? "Pistons at Magic"
    }

    private var exampleBody: String {
        if let mover = qualifyingBigMover, let shift = mover.deltaText {
            let subject = mover.subjectLabel.isEmpty ? mover.title : mover.subjectLabel
            let capitalizedShift = shift.prefix(1).uppercased() + shift.dropFirst()
            return "\(capitalizedShift) \u{00B7} \(subject) now \(mover.percent)%"
        }
        if let game = previewUpcomingGame {
            let subject = game.subjectLabel.isEmpty ? game.title : game.subjectLabel
            let timing = game.startTimeText.map { "Tipoff \($0)" } ?? "Starting soon"
            return "\(timing) \u{00B7} \(subject) \(game.percent)%"
        }
        return "Up 33 points since pregame \u{00B7} San Francisco now 60%"
    }

    var body: some View {
        VStack(spacing: 0) {
            StepTopBar364A(
                title: FirstRunChecklistRowID364A.alerts.title,
                actionTitle: nil,
                onBack: {
                    onBack()
                    dismiss()
                },
                onAction: {}
            )

            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    // Show, do not describe: lock-screen style heads-up preview (Fix b & c: zero lab words, explicit window + subject)
                    HStack(spacing: 12) {
                        ChecklistThumbnail364A(
                            urlString: displayedExampleCard?.imageUrl,
                            sfSymbol: qualifyingBigMover != nil ? "bell.badge.fill" : "sportscourt.fill",
                            accentHex: qualifyingBigMover != nil ? "#D97706" : "#047857",
                            size: 40
                        )
                        VStack(alignment: .leading, spacing: 2) {
                            HStack(spacing: 6) {
                                Text("HEADS-UP EXAMPLE")
                                    .font(.caption2.weight(.bold))
                                    .tracking(0.6)
                                    .foregroundStyle(amberAccent)
                                Spacer(minLength: 4)
                                Text("now")
                                    .font(.caption2)
                                    .foregroundStyle(DS.textSecondaryReadable)
                            }
                            Text(exampleTitle)
                                .font(.subheadline.weight(.semibold))
                                .foregroundStyle(DS.textPrimary)
                                .fixedSize(horizontal: false, vertical: true)
                            Text(exampleBody)
                                .font(.caption.weight(.medium))
                                .foregroundStyle(DS.greenReadable)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                    .padding(12)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: 14, style: .continuous)
                            .stroke(DS.border, lineWidth: 1)
                    )

                    VStack(alignment: .leading, spacing: 0) {
                        headsUpFeatureRow(
                            symbol: "sportscourt.fill",
                            tint: DS.greenReadable,
                            title: "Game starts",
                            subtitle: "Tipoff and kickoff for teams you follow."
                        )
                        Divider().padding(.leading, 48)
                        headsUpFeatureRow(
                            symbol: "chart.line.uptrend.xyaxis",
                            tint: amberAccent,
                            title: "Big moves",
                            subtitle: "Swings of 15 points or more."
                        )
                    }
                    .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: 14, style: .continuous)
                            .stroke(DS.border, lineWidth: 1)
                    )

                    Text("We\u{2019}ll ask before any alert. Offered again when you follow a team with a game coming.")
                        .font(.footnote)
                        .foregroundStyle(DS.textSecondaryReadable)
                        .fixedSize(horizontal: false, vertical: true)

                    VStack(spacing: 10) {
                        Button {
                            if let onTurnOnAlerts {
                                onTurnOnAlerts()
                            } else {
                                onDone()
                            }
                        } label: {
                            Text(alertsAlreadyOn ? "Heads-up is on \u{2014} back" : "Turn on heads-up")
                                .font(.headline)
                                .foregroundStyle(solidButtonForeground)
                                .frame(maxWidth: .infinity, minHeight: 50)
                                .background(DS.blueReadable, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                        }
                        .buttonStyle(.plain)
                        .disabled(isBusy)
                        .accessibilityIdentifier("checklist364A.alerts.turnOn")

                        if !alertsAlreadyOn {
                            Button {
                                if let onNotNow {
                                    onNotNow()
                                } else {
                                    onDone()
                                }
                            } label: {
                                Text("Not now")
                                    .font(.subheadline.weight(.medium))
                                    .foregroundStyle(DS.textSecondaryReadable)
                                    .frame(maxWidth: .infinity, minHeight: 40)
                            }
                            .buttonStyle(.plain)
                            .disabled(isBusy)
                            .accessibilityIdentifier("checklist364A.alerts.notNow")
                        }
                    }
                    .padding(.top, 4)
                }
                .padding(16)
                .checklistReadableColumn364A()
            }
        }
        .background(DS.surface)
        #if os(iOS)
        .toolbar(.hidden, for: .navigationBar)
        #endif
    }

    private func headsUpFeatureRow(symbol: String, tint: Color, title: String, subtitle: String) -> some View {
        HStack(spacing: 12) {
            Image(systemName: symbol)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(tint)
                .frame(width: 28, height: 28)
                .background(tint.opacity(colorScheme == .dark ? 0.18 : 0.10), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                Text(subtitle)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondaryReadable)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 4)
        }
        .padding(12)
    }
}

// MARK: - Tap-nothing & leave destination: real Discover feed directly

struct FirstRunLeaveToDiscoverPreview364A: View {
    let sets: [FirstRunSetChoice364A]

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Discover")
                    .font(.title3.weight(.bold))
                    .foregroundStyle(DS.textPrimary)
                Spacer(minLength: 8)
                Image(systemName: "magnifyingglass")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textSecondaryReadable)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .checklistReadableColumn364A()

            Divider()

            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    ForEach(sets.prefix(3)) { choice in
                        MachineryDiscoverEntryCardView(
                            card: choice.machineryCard,
                            pairedMetricSet: choice.pairedMetricSet,
                            onOpenContainer: { _, _ in },
                            onOpenMarket: { _ in }
                        )
                    }
                }
                .padding(16)
                .checklistReadableColumn364A()
            }
        }
        .background(DS.surface)
        .accessibilityIdentifier("checklist364A.discoverDefaultLanding")
    }
}

private struct StepTopBar364A: View {
    let title: String
    let actionTitle: String?
    var onBack: () -> Void = {}
    let onAction: () -> Void

    var body: some View {
        HStack(spacing: 8) {
            Button(action: onBack) {
                Image(systemName: "chevron.left")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.blueReadable)
                    .frame(width: 28, height: 28, alignment: .leading)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Back")
            Text(title)
                .font(.headline.weight(.bold))
                .foregroundStyle(DS.textPrimary)
                .lineLimit(1)
                .minimumScaleFactor(0.85)
            Spacer(minLength: 8)
            if let actionTitle {
                Button(actionTitle, action: onAction)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textSecondaryReadable)
                    .padding(.horizontal, 12)
                    .frame(minHeight: 32)
                    .background(DS.cardBg, in: Capsule())
                    .overlay(Capsule().stroke(DS.border, lineWidth: 1))
                    .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .checklistReadableColumn364A()
    }
}

/// Flow wrapping layout for picked-team and example chips so long names never clip (`#13517`, `364: A`).
struct FirstRunPickedChipFlow212A: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(
        proposal: ProposedViewSize,
        subviews: Subviews,
        cache: inout ()
    ) -> CGSize {
        let hasFiniteWidth = (proposal.width ?? .infinity).isFinite
        let maxWidth = hasFiniteWidth ? max(1, proposal.width!) : 280
        var x: CGFloat = 0
        var y: CGFloat = 0
        var rowHeight: CGFloat = 0
        var usedWidth: CGFloat = 0

        for subview in subviews {
            let size = subview.sizeThatFits(ProposedViewSize(width: maxWidth, height: nil))
            if x > 0 && x + size.width > maxWidth {
                x = 0
                y += rowHeight + spacing
                rowHeight = 0
            }
            usedWidth = max(usedWidth, min(maxWidth, x + size.width))
            rowHeight = max(rowHeight, size.height)
            x += size.width + spacing
        }
        return CGSize(width: hasFiniteWidth ? maxWidth : usedWidth, height: y + rowHeight)
    }

    func placeSubviews(
        in bounds: CGRect,
        proposal: ProposedViewSize,
        subviews: Subviews,
        cache: inout ()
    ) {
        let maxWidth = bounds.width
        var x = bounds.minX
        var y = bounds.minY
        var rowHeight: CGFloat = 0

        for subview in subviews {
            let size = subview.sizeThatFits(ProposedViewSize(width: maxWidth, height: nil))
            if x > bounds.minX && x + size.width > bounds.maxX {
                x = bounds.minX
                y += rowHeight + spacing
                rowHeight = 0
            }
            subview.place(
                at: CGPoint(x: x, y: y),
                anchor: .topLeading,
                proposal: ProposedViewSize(width: min(size.width, maxWidth), height: size.height)
            )
            rowHeight = max(rowHeight, size.height)
            x += size.width + spacing
        }
    }
}
