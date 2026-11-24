import Combine
import SwiftUI

// MARK: - Decision 364: A — Single-Screen Five-Row First-Run Checklist (#11934)

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

/// Main first screen under Decision 364: A — five optional rows on one screen (any order)
/// plus `"Start with tonight"` under the rows and one `"Skip"` exit.
struct FirstRunChecklistView364A: View {
    let content: FirstRunChecklistContent364A
    @Binding var state: FirstRunChecklistState364A
    @Binding var inlineSearchQuery: String
    var onSkipOrFinish: () -> Void = {}
    var onTapLookupExample: (FirstRunLookupExample364A) -> Void = { _ in }
    var onOpenRow: (FirstRunChecklistRowID364A) -> Void = { _ in }
    var onSelectTonightCard: (FirstRunTonightCard364A) -> Void = { _ in }

    @Environment(\.colorScheme) private var colorScheme

    private var solidButtonForeground: Color {
        colorScheme == .dark ? Color(hex: "#0F172A") : .white
    }

    var body: some View {
        VStack(spacing: 0) {
            topBar
                .padding(.horizontal, 16)
                .padding(.top, 8)
                .padding(.bottom, 4)

            ScrollView {
                VStack(alignment: .leading, spacing: 11) {
                    headerBlock
                    rowsCard
                    startWithTonightBlock
                }
                .padding(.horizontal, 16)
                .padding(.top, 2)
                .padding(.bottom, 14)
                .frame(maxWidth: 680)
                .frame(maxWidth: .infinity)
            }

            if state.completedCount >= state.totalCount {
                doneFooter
            }
        }
        .background(DS.surface)
        .accessibilityIdentifier("checklist364A.root")
    }

    private var topBar: some View {
        HStack(spacing: 10) {
            HStack(spacing: 6) {
                Image(systemName: "sparkle")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(DS.greenReadable)
                Text("Bain Luck")
                    .font(.headline.weight(.bold))
                    .foregroundStyle(DS.textPrimary)
            }

            Spacer(minLength: 8)

            if state.completedCount > 0 {
                Text(state.progressText)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DS.blueReadable)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 5)
                    .background(DS.blueReadable.opacity(colorScheme == .dark ? 0.18 : 0.10), in: Capsule())
                    .fixedSize(horizontal: true, vertical: false)
                    .accessibilityIdentifier("checklist364A.progressBadge")
            }

            if state.completedCount < state.totalCount {
                Button("Skip", action: onSkipOrFinish)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textSecondaryReadable)
                    .padding(.horizontal, 14)
                    .frame(minHeight: 34)
                    .background(DS.cardBg, in: Capsule())
                    .overlay(Capsule().stroke(DS.border, lineWidth: 1))
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("checklist364A.skipButton")
            }
        }
    }

    private var headerBlock: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Start anywhere")
                .font(.title2.weight(.bold))
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)

            Text(FirstRunChecklistContent364A.butlerQuote)
                .font(.caption)
                .foregroundStyle(DS.textSecondaryReadable)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("checklist364A.butlerQuote")
        }
    }

    private var rowsCard: some View {
        let syncLit = state.isSyncLitUp
        let syncPreview = FirstRunChecklistRowPreview364A(
            subtitle: syncLit ? "Sign in to sync across devices" : "Follow or pick first",
            percentText: nil,
            imageUrl: syncLit ? (content.followRowPreview?.imageUrl ?? content.setsRowPreview?.imageUrl) : nil,
            sfSymbol: "iphone.and.ipad",
            accentHex: "#005CC2"
        )
        return VStack(spacing: 0) {
            lookUpRow
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
                badgePillText: syncLit ? "\(max(1, state.savedCount)) saved" : nil
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

    private var lookUpRow: some View {
        let isDone = state.completedRows.contains(.lookUp)
        let preview = content.lookupRowPreview
        return VStack(alignment: .leading, spacing: 7) {
            Button {
                onOpenRow(.lookUp)
            } label: {
                HStack(spacing: 10) {
                    ChecklistThumbnail364A(
                        urlString: preview?.imageUrl,
                        sfSymbol: preview?.sfSymbol ?? "magnifyingglass",
                        accentHex: preview?.accentHex ?? "#005CC2",
                        size: 34
                    )
                    VStack(alignment: .leading, spacing: 1) {
                        Text(FirstRunChecklistRowID364A.lookUp.title)
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(DS.textPrimary)
                            .fixedSize(horizontal: false, vertical: true)
                        Text("No account needed")
                            .font(.caption)
                            .foregroundStyle(DS.textSecondaryReadable)
                    }
                    Spacer(minLength: 6)
                    if let pct = preview?.percentText {
                        Text(pct)
                            .font(.subheadline.weight(.bold).monospacedDigit())
                            .foregroundStyle(DS.blueReadable)
                            .fixedSize(horizontal: true, vertical: false)
                    }
                    rowStatusIcon(isDone: isDone)
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier(FirstRunChecklistRowID364A.lookUp.accessibilityIdentifier)

            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass")
                    .font(.caption)
                    .foregroundStyle(DS.textSecondaryReadable)
                TextField("Search any team, game, or market", text: $inlineSearchQuery)
                    .textFieldStyle(.plain)
                    .font(.subheadline)
                    .accessibilityIdentifier("checklist364A.inlineSearchField")
                Spacer(minLength: 4)
                Text("Go")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DS.blueReadable)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(DS.surface, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(DS.border, lineWidth: 1))
            .onTapGesture { onOpenRow(.lookUp) }

            if !content.lookupExamples.isEmpty {
                FirstRunPickedChipFlow212A(spacing: 5) {
                    ForEach(content.lookupExamples.prefix(3)) { ex in
                        Button {
                            onTapLookupExample(ex)
                        } label: {
                            HStack(spacing: 4) {
                                Text(ex.title)
                                    .font(.caption.weight(.medium))
                                    .foregroundStyle(DS.textPrimary)
                                    .fixedSize(horizontal: false, vertical: true)
                                Text("\(ex.percent)%")
                                    .font(.caption.weight(.bold).monospacedDigit())
                                    .foregroundStyle(DS.blueReadable)
                                    .fixedSize(horizontal: true, vertical: false)
                            }
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(DS.trackBg, in: Capsule())
                            .overlay(Capsule().stroke(DS.border, lineWidth: 1))
                        }
                        .buttonStyle(.plain)
                        .accessibilityIdentifier("checklist364A.example.\(ex.kind.rawValue)")
                    }
                }
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
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

                VStack(alignment: .leading, spacing: 1) {
                    Text(row.title)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(isRowLit ? DS.textPrimary : DS.textSecondaryReadable)
                        .multilineTextAlignment(.leading)
                        .fixedSize(horizontal: false, vertical: true)

                    if let note = mutedNote ?? preview?.subtitle, !note.isEmpty {
                        Text(note)
                            .font(.caption)
                            .foregroundStyle(isRowLit && row == .syncDevices ? DS.blueReadable : DS.textSecondaryReadable)
                            .multilineTextAlignment(.leading)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }

                Spacer(minLength: 6)

                if let badgePillText {
                    Text(badgePillText)
                        .font(.caption.weight(.bold).monospacedDigit())
                        .foregroundStyle(DS.blueReadable)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 3)
                        .background(DS.blueReadable.opacity(colorScheme == .dark ? 0.18 : 0.10), in: Capsule())
                        .fixedSize(horizontal: true, vertical: false)
                } else if let pct = preview?.percentText {
                    Text(pct)
                        .font(.subheadline.weight(.bold).monospacedDigit())
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize(horizontal: true, vertical: false)
                }

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

    private var startWithTonightBlock: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Start with tonight")
                .font(.subheadline.weight(.bold))
                .foregroundStyle(DS.textPrimary)

            VStack(spacing: 6) {
                ForEach(content.startWithTonight) { card in
                    Button {
                        onSelectTonightCard(card)
                    } label: {
                        HStack(spacing: 10) {
                            ChecklistThumbnail364A(
                                urlString: card.imageUrl,
                                sfSymbol: card.sfSymbol,
                                accentHex: card.accentHex,
                                size: 36
                            )

                            VStack(alignment: .leading, spacing: 1) {
                                HStack(spacing: 6) {
                                    Text(card.slotLabel.uppercased())
                                        .font(.caption2.weight(.bold))
                                        .tracking(0.5)
                                        .foregroundStyle(Color(hex: MyStuffTeamTextColour.probabilityHex(card.accentHex, colorScheme: colorScheme)))
                                    if let delta = card.deltaText {
                                        Text(delta)
                                            .font(.caption2.weight(.semibold))
                                            .foregroundStyle(DS.greenReadable)
                                    }
                                }
                                Text(card.title)
                                    .font(.subheadline.weight(.semibold))
                                    .foregroundStyle(DS.textPrimary)
                                    .multilineTextAlignment(.leading)
                                    .fixedSize(horizontal: false, vertical: true)
                                Text(card.subtitle)
                                    .font(.caption)
                                    .foregroundStyle(DS.textSecondaryReadable)
                                    .fixedSize(horizontal: false, vertical: true)
                            }

                            Spacer(minLength: 8)

                            Text("\(card.percent)%")
                                .font(.headline.weight(.heavy).monospacedDigit())
                                .foregroundStyle(DS.textPrimary)
                                .fixedSize(horizontal: true, vertical: false)
                        }
                        .padding(.horizontal, 10)
                        .padding(.vertical, 8)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                        .overlay(
                            RoundedRectangle(cornerRadius: 12, style: .continuous)
                                .stroke(DS.border, lineWidth: 1)
                        )
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("checklist364A.tonight.\(card.id)")
                }
            }
        }
    }

    private var doneFooter: some View {
        VStack(spacing: 0) {
            Divider()
            Button(action: onSkipOrFinish) {
                Text("Go to Discover \u{2192}")
                    .font(.headline)
                    .foregroundStyle(solidButtonForeground)
                    .frame(maxWidth: .infinity, minHeight: 46)
                    .background(DS.blueReadable, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            }
            .buttonStyle(.plain)
            .padding(.horizontal, 16)
            .padding(.vertical, 9)
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

    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        if state.showsInMyStuff {
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 8) {
                    Text("Getting started")
                        .font(.subheadline.weight(.bold))
                        .foregroundStyle(DS.textPrimary)
                    Text(state.progressText)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DS.blueReadable)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 3)
                        .background(DS.blueReadable.opacity(colorScheme == .dark ? 0.18 : 0.10), in: Capsule())
                    Spacer(minLength: 4)
                    Button {
                        state.dismissedFromMyStuff = true
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
                            HStack(spacing: 8) {
                                Image(systemName: isDone ? "checkmark.circle.fill" : "circle")
                                    .font(.subheadline.weight(.semibold))
                                    .foregroundStyle(isDone ? DS.greenReadable : (lit ? DS.blueReadable : DS.textMuted))
                                Text(row.title)
                                    .font(.footnote.weight(isDone ? .medium : .semibold))
                                    .foregroundStyle(isDone ? DS.textSecondaryReadable : (lit ? DS.textPrimary : DS.textMuted))
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
    var onTapExample: (FirstRunLookupExample364A) -> Void = { _ in }
    var onDone: () -> Void = {}

    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        VStack(spacing: 0) {
            StepTopBar364A(
                title: FirstRunChecklistRowID364A.lookUp.title,
                actionTitle: results.isEmpty && query.isEmpty ? "Skip" : "Done",
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
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 12)
                    .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(DS.blueReadable.opacity(0.45), lineWidth: 1.5))

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
                                        Text(ex.title)
                                            .font(.subheadline.weight(.medium))
                                            .foregroundStyle(DS.textPrimary)
                                            .multilineTextAlignment(.leading)
                                            .fixedSize(horizontal: false, vertical: true)
                                    }
                                    Spacer(minLength: 8)
                                    Text("\(ex.percent)%")
                                        .font(.subheadline.weight(.bold).monospacedDigit())
                                        .foregroundStyle(DS.textPrimary)
                                        .fixedSize(horizontal: true, vertical: false)
                                }
                                .padding(10)
                                .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                                .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(DS.border, lineWidth: 1))
                            }
                            .buttonStyle(.plain)
                        }
                    }

                    if !results.isEmpty {
                        VStack(spacing: 0) {
                            ForEach(Array(results.enumerated()), id: \.element.id) { idx, row in
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
                                            .multilineTextAlignment(.leading)
                                            .fixedSize(horizontal: false, vertical: true)
                                        Text("\(row.badgeText) \u{00B7} \(row.subtitle)")
                                            .font(.caption)
                                            .foregroundStyle(DS.textSecondaryReadable)
                                            .fixedSize(horizontal: false, vertical: true)
                                    }
                                    Spacer(minLength: 8)
                                    Text("\(row.percent)%")
                                        .font(.headline.weight(.bold).monospacedDigit())
                                        .foregroundStyle(DS.blueReadable)
                                        .fixedSize(horizontal: true, vertical: false)
                                }
                                .padding(.horizontal, 12)
                                .padding(.vertical, 10)
                                if idx < results.count - 1 {
                                    Divider().padding(.leading, 56)
                                }
                            }
                        }
                        .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(DS.border, lineWidth: 1))
                    }
                }
                .padding(16)
            }
        }
        .background(DS.surface)
    }
}

// MARK: - Step 2: Follow what you care about (teams, cities, schools, subjects w/ pictures + 359:A)

struct FirstRunFollowStepView364A: View {
    @ObservedObject var vm: FirstRunViewModel212A
    let subjectArtByCategory: [String: String]
    var onDone: () -> Void = {}

    @Environment(\.followManager295A) private var followManager
    @Environment(\.colorScheme) private var colorScheme

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
                onAction: {}
            )

            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    Text("Teams, cities, schools, or a plain note \u{2014} all saved in My Stuff.")
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
                        TextField("Type a city, school, team, or sentence", text: $vm.searchQuery, axis: .vertical)
                            .textFieldStyle(.plain)
                            .lineLimit(1...3)
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 12)
                    .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(DS.blueReadable.opacity(0.45), lineWidth: 1.5))

                    sentenceCardSection

                    if !picturedSuggestions.isEmpty {
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
                                            Text(picked ? "Added" : "Add")
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
            }

            Divider()
            Button(action: onDone) {
                Text(vm.pickedItems.isEmpty ? "Skip" : "Save & back")
                    .font(.headline)
                    .foregroundStyle(solidButtonForeground)
                    .frame(maxWidth: .infinity, minHeight: 50)
                    .background(DS.blueReadable, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            }
            .buttonStyle(.plain)
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .background(DS.surface)
        }
        .background(DS.surface)
    }

    @ViewBuilder
    private var sentenceCardSection: some View {
        if case .chips(let chips, let selectedIds, let isSample) = vm.sentenceState {
            let clearChips = chips.filter { $0.ambiguityGroup == nil }
            let ambiguousGroups = Dictionary(grouping: chips.filter { $0.ambiguityGroup != nil }) { $0.ambiguityGroup ?? "" }
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 8) {
                    Text("Confirm your picks")
                        .font(.subheadline.weight(.bold))
                        .foregroundStyle(DS.textPrimary)
                    Spacer(minLength: 4)
                    if isSample {
                        Text(FirstRunSentenceSampleProvider359A.sampleBadgeText)
                            .font(.caption2.weight(.medium))
                            .foregroundStyle(DS.textSecondaryReadable)
                            .padding(.horizontal, 7)
                            .padding(.vertical, 3)
                            .background(DS.trackBg, in: Capsule())
                    }
                }
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
    var onDone: () -> Void = {}

    @Environment(\.colorScheme) private var colorScheme

    private var solidButtonForeground: Color {
        colorScheme == .dark ? Color(hex: "#0F172A") : .white
    }

    var body: some View {
        VStack(spacing: 0) {
            StepTopBar364A(
                title: FirstRunChecklistRowID364A.exploreSets.title,
                actionTitle: nil,
                onAction: {}
            )

            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    Text("Tap the ones you\u{2019}d open.")
                        .font(.subheadline.weight(.medium))
                        .foregroundStyle(DS.textSecondaryReadable)
                        .fixedSize(horizontal: false, vertical: true)

                    ForEach(sets) { choice in
                        let selected = selectedSlugs.contains(choice.slug)
                        ZStack(alignment: .topTrailing) {
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

                            Image(systemName: selected ? "checkmark.circle.fill" : "circle")
                                .font(.title3.weight(.semibold))
                                .foregroundStyle(selected ? DS.blueReadable : DS.textMuted)
                                .padding(10)
                                .accessibilityHidden(true)
                        }
                        .accessibilityIdentifier("checklist364A.set.\(choice.slug)")
                    }
                }
                .padding(16)
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
            .background(DS.surface)
        }
        .background(DS.surface)
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
    var onBackOrSkip: () -> Void = {}

    var body: some View {
        VStack(spacing: 0) {
            StepTopBar364A(
                title: FirstRunChecklistRowID364A.syncDevices.title,
                actionTitle: nil,
                onAction: {}
            )
            ScrollView {
                EarnedSignInCard212A(
                    onAppleSignIn: onBackOrSkip,
                    onGoogleSignIn: onBackOrSkip,
                    onDismissLocalOnly: onBackOrSkip
                )
                .padding(16)
            }
        }
        .background(DS.surface)
    }
}

struct FirstRunAlertsStepView364A: View {
    var previewMover: FirstRunTonightCard364A? = nil
    var onDone: () -> Void = {}

    @Environment(\.colorScheme) private var colorScheme

    private var solidButtonForeground: Color {
        colorScheme == .dark ? Color(hex: "#0F172A") : .white
    }

    private var amberAccent: Color {
        Color(hex: MyStuffTeamTextColour.probabilityHex("#D97706", colorScheme: colorScheme))
    }

    private var exampleTitle: String {
        previewMover?.title ?? "Nevada at San Francisco"
    }

    private var exampleBody: String {
        let shift = previewMover?.deltaText ?? "up 33 points"
        let pct = previewMover?.percent ?? 60
        let capitalizedShift = shift.prefix(1).uppercased() + shift.dropFirst()
        return "\(capitalizedShift) \u{00B7} now \(pct)%"
    }

    var body: some View {
        VStack(spacing: 0) {
            StepTopBar364A(
                title: FirstRunChecklistRowID364A.alerts.title,
                actionTitle: nil,
                onAction: {}
            )

            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    // Show, do not describe: live lock-screen style heads-up preview
                    HStack(spacing: 12) {
                        ChecklistThumbnail364A(
                            urlString: previewMover?.imageUrl,
                            sfSymbol: "bell.badge.fill",
                            accentHex: "#D97706",
                            size: 40
                        )
                        VStack(alignment: .leading, spacing: 2) {
                            HStack(spacing: 6) {
                                Text("LIVE EXAMPLE")
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

                    Text("Apple\u{2019}s alert prompt appears only after you tap Turn on. Offered again when you follow a team with a game coming.")
                        .font(.footnote)
                        .foregroundStyle(DS.textSecondaryReadable)
                        .fixedSize(horizontal: false, vertical: true)

                    VStack(spacing: 10) {
                        Button(action: onDone) {
                            Text("Turn on heads-up")
                                .font(.headline)
                                .foregroundStyle(solidButtonForeground)
                                .frame(maxWidth: .infinity, minHeight: 50)
                                .background(DS.blueReadable, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                        }
                        .buttonStyle(.plain)
                        .accessibilityIdentifier("checklist364A.alerts.turnOn")

                        Button(action: onDone) {
                            Text("Not now")
                                .font(.subheadline.weight(.medium))
                                .foregroundStyle(DS.textSecondaryReadable)
                                .frame(maxWidth: .infinity, minHeight: 40)
                        }
                        .buttonStyle(.plain)
                        .accessibilityIdentifier("checklist364A.alerts.notNow")
                    }
                    .padding(.top, 4)
                }
                .padding(16)
            }
        }
        .background(DS.surface)
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
                HStack(spacing: 6) {
                    Image(systemName: "sparkle")
                        .font(.subheadline.weight(.bold))
                        .foregroundStyle(DS.greenReadable)
                    Text("Discover")
                        .font(.title3.weight(.bold))
                        .foregroundStyle(DS.textPrimary)
                }
                Spacer(minLength: 8)
                Image(systemName: "magnifyingglass")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textSecondaryReadable)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)

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
            }
        }
        .background(DS.surface)
        .accessibilityIdentifier("checklist364A.discoverDefaultLanding")
    }
}

private struct StepTopBar364A: View {
    let title: String
    let actionTitle: String?
    let onAction: () -> Void

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "chevron.left")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DS.blueReadable)
                .accessibilityHidden(true)
            Text(title)
                .font(.headline.weight(.bold))
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
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
    }
}
