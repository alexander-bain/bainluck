import SwiftUI

/// One golf tournament: who is in the field and what the market thinks of them
/// (#1471).
///
/// ## Why this screen exists
///
/// Alex, 2026-09-16, on his phone: tapping the golf card on Discover took him to
/// the generic Golf page, which showed him **the same card again**, and tapping
/// that produced **"Couldn't load Biltmore Championship Asheville"** — and the
/// retry button could not fix it, because it re-made the same call.
///
/// Every step of that was real. `Route.golfTournament` discarded its slug
/// (`case .golfTournament(_, let name): SportCategoryView(categoryKey: "golf" …)`)
/// so every tournament row on the Golf page led back to a golf-shaped list —
/// the "duplicate card". And `SportCategoryView` sent feed tournament rows to
/// `Route.tournamentHub`, which calls `/api/tournaments/{slug}`: the registered
/// **tennis** hub, a guaranteed 404 for a golf slug.
///
/// There was nowhere for a golf tournament to go. This is the somewhere. The
/// data was there the whole time — `/api/golf/tournaments/biltmore-championship-asheville`
/// answered 200 with 132 golfers while the phone was printing an error.
struct GolfTournamentView: View {
    let slug: String
    let displayName: String

    @StateObject private var vm: GolfTournamentViewModel
    @State private var showingWholeField = false

    init(slug: String, displayName: String) {
        self.slug = slug
        self.displayName = displayName
        _vm = StateObject(wrappedValue: GolfTournamentViewModel(slug: slug))
    }

    var body: some View {
        Group {
            switch vm.state {
            case .loading:
                ProgressView()
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            case .loaded(let presentation):
                loaded(presentation)
            case .error(let message):
                errorState(message)
            }
        }
        .navigationTitle(displayName)
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .task {
            await vm.load()
            AnalyticsService.trackScreen(name: "golf_tournament", type: "tournament")
        }
    }

    // MARK: - Loaded

    private func loaded(_ presentation: GolfTournamentPresentation) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                header(presentation)

                if presentation.field.isEmpty {
                    // The tournament is real and the field is not published yet
                    // — a normal state for an event days out, and it is said in
                    // one short line rather than explained (notice 34).
                    Text("No odds yet")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.top, 8)
                } else {
                    fieldSection(presentation)
                }
            }
            .padding(.horizontal)
            .padding(.bottom, 40)
        }
        .refreshable { await vm.load() }
    }

    /// The title bar already says the tournament's name, so this does not.
    ///
    /// MEASURED — the first shot of this screen printed "Biltmore Championship
    /// Asheville" in the navigation bar and again, in bold, directly beneath
    /// it. `TournamentHubView` is the house idiom here and draws no title of its
    /// own for exactly this reason. What a reader needs under the bar is the
    /// information the bar does not have: where it is being played and when.
    private func header(_ presentation: GolfTournamentPresentation) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            if presentation.isMajor {
                Text("MAJOR")
                    .font(.system(size: 10, weight: .bold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 3)
                    .background(Color.yellow.opacity(0.8))
                    .clipShape(RoundedRectangle(cornerRadius: 4))
            }

            if let venue = presentation.venue {
                HStack(spacing: 4) {
                    Image(systemName: "mappin.circle.fill")
                        .font(.system(size: 11))
                        .foregroundStyle(.mint.opacity(0.7))
                    // Promoted to primary now that the page draws no title of
                    // its own: without it the whole header was tertiary grey
                    // under an inline bar, and the screen opened with nothing
                    // for the eye to land on.
                    Text(venue)
                        .font(.headline)
                }
            }

            // Location, tour and dates are one quiet line, in the order a person
            // reads them: where, which tour, when.
            let details = [presentation.location, presentation.tourLabel, presentation.dateRange]
                .compactMap { $0 }
                .filter { !$0.isEmpty }
            if !details.isEmpty {
                Text(details.joined(separator: " · "))
                    .font(.caption)
                    .foregroundStyle(.tertiary)
            }
        }
        .padding(.top, 8)
    }

    private func fieldSection(_ presentation: GolfTournamentPresentation) -> some View {
        let shown = showingWholeField
            ? presentation.field
            : Array(presentation.field.prefix(GolfTournamentPresentation.initiallyShown))

        return VStack(alignment: .leading, spacing: 8) {
            Text("Winner")
                .font(.headline)

            VStack(spacing: 6) {
                ForEach(shown) { row in
                    fieldRow(row)
                }
            }

            // The rest of the field is behind a toggle rather than 132 rows of
            // scroll (D102's collapsed-toggle shape). The count is on the
            // control so the reader knows what they are asking for.
            if presentation.field.count > GolfTournamentPresentation.initiallyShown {
                Button {
                    withAnimation { showingWholeField.toggle() }
                } label: {
                    Text(showingWholeField
                         ? "Show less"
                         : "Show all \(presentation.field.count)")
                        .font(.subheadline)
                        .fontWeight(.medium)
                        .foregroundStyle(.blue)
                }
                .buttonStyle(.plain)
                .padding(.top, 4)
            }
        }
    }

    private func fieldRow(_ row: GolfTournamentFieldRow) -> some View {
        HStack(spacing: 8) {
            Text("\(row.position)")
                .font(.caption2)
                .fontWeight(.bold)
                .frame(width: 20, alignment: .trailing)
                .foregroundStyle(row.position == 1 ? .orange : .secondary)

            Text(row.name)
                .font(.subheadline)
                .fontWeight(row.position == 1 ? .semibold : .medium)

            if row.hasMeaningfulMovement, let movement = row.movement24h {
                HStack(spacing: 1) {
                    Image(systemName: movement > 0 ? "arrow.up" : "arrow.down")
                        .font(.system(size: 7))
                    Text(String(format: "%.1f", abs(movement * 100)))
                        .font(.system(size: 9))
                }
                .foregroundStyle(movement > 0 ? .green : .red)
            }

            Spacer()

            Text(String(format: "%.1f%%", row.probability * 100))
                .font(.subheadline)
                .fontWeight(.semibold)
                .monospacedDigit()
                .foregroundStyle(row.position == 1 ? .blue : .secondary)
        }
    }

    // MARK: - Error

    /// The state Alex was stuck in, now with a retry that can actually succeed.
    ///
    /// It says the tournament's name because "Couldn't load" on its own, on a
    /// screen whose title bar is the only other text, tells a reader nothing
    /// about what failed.
    private func errorState(_ message: String) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "arrow.clockwise")
                .font(.title2)
                .foregroundStyle(.secondary)
            Text("Couldn't load \(displayName)")
                .font(.subheadline.weight(.medium))
                .multilineTextAlignment(.center)
            Text(message)
                .font(.caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            Button("Retry") { Task { await vm.load() } }
                .font(.subheadline.weight(.medium))
                .foregroundStyle(.blue)
        }
        .padding()
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
