import SwiftUI

// MARK: - Tournament hub screen
//
// G2 of SHOWABLE-1: "the US Open exists in the app". Browse → US Open → this
// screen, fed by `GET /api/tournaments/{slug}` — the same payload the web hub
// renders.
//
// The screen is split in two on purpose. `TournamentHubSurface` takes a finished
// `TournamentHubPresentation` and owns no `.task`, no view model and no network,
// so `ImageRenderer` rasterises the REAL rows instead of a loading skeleton —
// the trap that makes native render evidence quietly worthless.
// `TournamentHubView` is the shell that loads.

struct TournamentHubView: View {
    let slug: String
    let displayName: String

    @StateObject private var vm: TournamentHubViewModel

    init(slug: String, displayName: String) {
        self.slug = slug
        self.displayName = displayName
        _vm = StateObject(wrappedValue: TournamentHubViewModel(slug: slug))
    }

    var body: some View {
        Group {
            switch vm.state {
            case .loading:
                TournamentHubLoadingView()
            case .loaded(let presentation):
                ScrollView {
                    TournamentHubSurface(presentation: presentation)
                        .padding(.horizontal, 18)
                        .padding(.vertical, 16)
                        .frame(maxWidth: 900, alignment: .leading)
                }
                .background(Color.groupedBackground.opacity(0.35))
            case .error(let message):
                TournamentHubErrorView(name: displayName, message: message) {
                    Task { await vm.load() }
                }
            }
        }
        .navigationTitle(displayName)
        .navigationBarTitleDisplayMode(.inline)
        .task {
            await vm.load()
            AnalyticsService.trackScreen(name: "tournament_hub", type: slug)
        }
        .refreshable { await vm.load() }
    }
}

// MARK: - The surface (presentation only — no network, no clock, no view model)

struct TournamentHubSurface: View {
    let presentation: TournamentHubPresentation

    var body: some View {
        VStack(alignment: .leading, spacing: 22) {
            header

            if let note = presentation.wholePayloadEmptyNote {
                // D27: the tournament returning nothing is a fact worth printing.
                // A blank screen is the one thing that reads as a broken app.
                TournamentHubNote(text: note)
            } else {
                TournamentHubSection(title: "Live now", accent: DS.danger) {
                    if let note = presentation.liveEmptyNote {
                        TournamentHubNote(text: note)
                    } else {
                        VStack(spacing: 10) {
                            ForEach(presentation.liveMatches) { TournamentHubMatchCard(row: $0) }
                        }
                    }
                }

                TournamentHubSection(title: "Next up", accent: DS.blue) {
                    if let note = presentation.upcomingEmptyNote {
                        TournamentHubNote(text: note)
                    } else {
                        VStack(spacing: 10) {
                            ForEach(presentation.upcomingMatches) { TournamentHubMatchCard(row: $0) }
                        }
                    }
                }

                ForEach(presentation.boards) { board in
                    TournamentHubSection(title: board.title, accent: DS.emeraldDark) {
                        TournamentHubBoardCard(board: board)
                    }
                }
                if let note = presentation.boardsEmptyNote {
                    TournamentHubSection(title: "Title odds", accent: DS.emeraldDark) {
                        TournamentHubNote(text: note)
                    }
                }

                TournamentHubSection(title: "Latest results", accent: DS.purple) {
                    if let note = presentation.resultsEmptyNote {
                        TournamentHubNote(text: note)
                    } else {
                        VStack(spacing: 10) {
                            ForEach(presentation.results) { TournamentHubResultCard(row: $0) }
                        }
                    }
                }

                TournamentHubSection(title: "Draw", accent: DS.textMuted) {
                    TournamentHubNote(text: presentation.bracketNote)
                }
            }

            if let age = presentation.priceAgeNote {
                Text(age)
                    .font(.caption2)
                    .foregroundStyle(DS.textMuted)
            }
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(presentation.title)
                .font(.title2.weight(.bold))
                .foregroundStyle(DS.textPrimary)
            if let subtitle = presentation.subtitle, !subtitle.isEmpty {
                Text(subtitle)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
            }
        }
    }
}

// MARK: - Section shell

private struct TournamentHubSection<Content: View>: View {
    let title: String
    let accent: Color
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title.uppercased())
                .font(.system(size: 11, weight: .heavy))
                .tracking(1.2)
                .foregroundStyle(accent)
            content
        }
    }
}

/// The honest-empty sentence. One place, one treatment, so an empty section can
/// never be mistaken for a section that failed to render.
private struct TournamentHubNote: View {
    let text: String

    var body: some View {
        Text(text)
            .font(.footnote)
            .foregroundStyle(DS.textSecondary)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(14)
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 12))
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(DS.border, lineWidth: 0.5))
    }
}

// MARK: - Match card

private struct TournamentHubMatchCard: View {
    let row: TournamentHubPresentation.MatchRow

    var body: some View {
        // Only a match that resolves to an event page becomes a link. A row that
        // looks tappable and goes nowhere is worse than a row that doesn't:
        // today the hub resolves event ids for FINISHED matches only, so every
        // live row would otherwise be a dead chevron.
        if let eventId = row.eventId {
            NavigationLink(value: Route.eventDetail(id: eventId)) {
                card(showsChevron: true)
            }
            .buttonStyle(.plain)
        } else {
            card(showsChevron: false)
        }
    }

    private func card(showsChevron: Bool) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                if row.isLive {
                    Text("LIVE")
                        .font(.system(size: 9, weight: .heavy))
                        .tracking(0.8)
                        .foregroundStyle(.white)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(DS.danger, in: Capsule())
                }
                Text(row.headline)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(DS.textMuted)
                    .lineLimit(1)
                Spacer(minLength: 4)
                Text(row.statusText)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(row.isLive ? DS.danger : DS.textSecondary)
                if showsChevron {
                    Image(systemName: "chevron.right")
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(DS.textMuted)
                }
            }

            VStack(spacing: 8) {
                ForEach(row.sides) { side in
                    HStack(spacing: 10) {
                        TournamentHubFlag(url: side.flagUrl)
                        Text(side.name)
                            .font(.subheadline.weight(side.isFavourite ? .bold : .regular))
                            .foregroundStyle(DS.textPrimary)
                            .lineLimit(1)
                        Spacer(minLength: 6)
                        Text(side.percentText)
                            .font(.subheadline.weight(.bold).monospacedDigit())
                            .foregroundStyle(side.hasPrice ? DS.textPrimary : DS.textMuted)
                    }
                }
            }

            if let note = row.noPriceNote {
                Text(note)
                    .font(.caption2)
                    .foregroundStyle(DS.textMuted)
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(DS.border, lineWidth: 0.5))
    }
}

// MARK: - Result card

private struct TournamentHubResultCard: View {
    let row: TournamentHubPresentation.ResultRow

    var body: some View {
        if let eventId = row.eventId {
            NavigationLink(value: Route.eventDetail(id: eventId)) {
                card(showsChevron: true)
            }
            .buttonStyle(.plain)
        } else {
            card(showsChevron: false)
        }
    }

    private func card(showsChevron: Bool) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Text(row.headline)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(DS.textMuted)
                    .lineLimit(1)
                Spacer(minLength: 4)
                if let note = row.completionNote {
                    Text(note.uppercased())
                        .font(.system(size: 9, weight: .heavy))
                        .tracking(0.6)
                        .foregroundStyle(DS.amber)
                }
                if showsChevron {
                    Image(systemName: "chevron.right")
                        .font(.caption2.weight(.bold))
                        .foregroundStyle(DS.textMuted)
                }
            }

            HStack(spacing: 8) {
                Image(systemName: "checkmark.circle.fill")
                    .font(.footnote)
                    .foregroundStyle(DS.emerald)
                Text(row.winnerName)
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(DS.textPrimary)
                    .lineLimit(1)
                Text("def.")
                    .font(.caption)
                    .foregroundStyle(DS.textMuted)
                Text(row.loserName)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .lineLimit(1)
            }

            if let score = row.score {
                Text(score)
                    .font(.footnote.monospacedDigit())
                    .foregroundStyle(DS.textSecondary)
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(DS.border, lineWidth: 0.5))
    }
}

// MARK: - Board card

private struct TournamentHubBoardCard: View {
    let board: TournamentHubPresentation.BoardSection

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            ForEach(board.rows) { row in
                HStack(spacing: 10) {
                    Text(row.rank.map(String.init) ?? "–")
                        .font(.caption.weight(.bold).monospacedDigit())
                        .foregroundStyle(DS.textMuted)
                        .frame(width: 16, alignment: .trailing)
                    TournamentHubFlag(url: row.flagUrl)
                    Text(row.name)
                        .font(.subheadline)
                        .foregroundStyle(DS.textPrimary)
                        .lineLimit(1)
                    Spacer(minLength: 6)
                    if let delta = row.deltaPoints {
                        Text(delta > 0
                             ? "+\(String(format: "%.0f", delta))"
                             : String(format: "%.0f", delta))
                            .font(.caption2.weight(.semibold).monospacedDigit())
                            .foregroundStyle(delta > 0 ? DS.emerald : DS.danger)
                    }
                    Text(row.percentText)
                        .font(.subheadline.weight(.bold).monospacedDigit())
                        .foregroundStyle(DS.textPrimary)
                        .frame(minWidth: 44, alignment: .trailing)
                }
            }

            if let note = board.trimNote {
                Text(note)
                    .font(.caption2)
                    .foregroundStyle(DS.textMuted)
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 12))
        .overlay(RoundedRectangle(cornerRadius: 12).stroke(DS.border, lineWidth: 0.5))
    }
}

// MARK: - Flag

private struct TournamentHubFlag: View {
    let url: String?

    var body: some View {
        Group {
            if let url, let parsed = URL(string: url) {
                AsyncImage(url: parsed) { image in
                    image.resizable().aspectRatio(contentMode: .fit)
                } placeholder: {
                    placeholder
                }
            } else {
                placeholder
            }
        }
        .frame(width: 20, height: 14)
        .clipShape(RoundedRectangle(cornerRadius: 2))
    }

    private var placeholder: some View {
        RoundedRectangle(cornerRadius: 2).fill(DS.trackBg)
    }
}

// MARK: - Loading / error

private struct TournamentHubLoadingView: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            ForEach(0..<4, id: \.self) { _ in
                VStack(alignment: .leading, spacing: 8) {
                    SkeletonShape(width: 120, height: 10)
                    SkeletonShape(height: 16)
                    SkeletonShape(height: 16)
                }
                .padding(14)
                .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 12))
            }
            Spacer()
        }
        .padding(18)
    }
}

private struct TournamentHubErrorView: View {
    let name: String
    let message: String
    let retry: () -> Void

    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: "wifi.exclamationmark")
                .font(.largeTitle)
                .foregroundStyle(DS.textMuted)
            Text("Couldn't load \(name)")
                .font(.headline)
            Text(message)
                .font(.footnote)
                .foregroundStyle(DS.textSecondary)
                .multilineTextAlignment(.center)
            Button("Try Again", action: retry)
                .buttonStyle(.borderedProminent)
        }
        .padding(30)
    }
}
