import SwiftUI

/// One fight card: its bouts, and what the market thinks of each (#6667).
///
/// Alex, 2026-09-16, on his phone: tapping a UFC card on Discover opened
/// **UFC, the sport** — not the card he tapped. `NativeConceptDiscoverCard`
/// said why in its own comment: "No native concept-hub view exists yet (web
/// opens /event/{key})". This is that view, for the one kind of concept it
/// knows how to draw — a card of two-fighter bouts. It reads the same endpoint
/// the web page reads.
///
/// Laid out like `GolfTournamentView` so the two kinds of Discover card behave
/// the same way once opened.
struct ConceptCardView: View {
    let key: String
    let displayName: String

    @StateObject private var vm: ConceptCardViewModel

    init(key: String, displayName: String) {
        self.key = key
        self.displayName = displayName
        _vm = StateObject(wrappedValue: ConceptCardViewModel(key: key))
    }

    var body: some View {
        Group {
            switch vm.state {
            case .loading:
                ProgressView()
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            case .loaded(let presentation):
                loaded(presentation)
            case .unavailable:
                unavailableState
            case .error(let message):
                errorState(message)
            }
        }
        .navigationTitle(title)
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .task {
            await vm.load()
            AnalyticsService.trackScreen(name: "concept_card", type: "concept")
        }
    }

    /// The server's own name once there is one. A deep link arrives knowing
    /// only the domain, and "UFC" is a worse title than "331: Van vs Pantoja".
    private var title: String {
        if case .loaded(let presentation) = vm.state, let name = presentation.name { return name }
        return displayName
    }

    // MARK: - Loaded

    private func loaded(_ presentation: ConceptCardPresentation) -> some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                header(presentation)

                if presentation.bouts.isEmpty {
                    // A real card with no bouts listed yet. One short line
                    // (notice 34), not an error: the server answered.
                    Text("No fights listed yet")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.top, 8)
                } else {
                    VStack(spacing: 10) {
                        ForEach(presentation.bouts) { bout in
                            boutRow(bout)
                        }
                    }
                }
            }
            .padding(.horizontal)
            .padding(.bottom, 40)
        }
        .refreshable { await vm.load() }
    }

    /// The title bar already says the card's name (`GolfTournamentView`'s
    /// measured lesson), so this says what the bar does not: which sport, when,
    /// and how many fights.
    private func header(_ presentation: ConceptCardPresentation) -> some View {
        let details = [
            presentation.domain.map(sportCategoryDisplayName),
            presentation.status == "settled" ? "Final" : formattedShortDate(presentation.startDate),
            presentation.bouts.isEmpty
                ? nil
                : "\(presentation.bouts.count) fight\(presentation.bouts.count == 1 ? "" : "s")",
        ]
        .compactMap { $0 }
        .filter { !$0.isEmpty }

        return Text(details.joined(separator: " · "))
            .font(.caption)
            .foregroundStyle(.secondary)
            .padding(.top, 8)
    }

    @ViewBuilder
    private func boutRow(_ bout: ConceptBoutRow) -> some View {
        if let route = ConceptCardRouting.route(for: bout.target) {
            // A value link on the enclosing stack — the same push Discover's
            // own cards use, so Back returns here and Back again returns to the
            // feed where the reader left it.
            NavigationLink(value: route) { boutBody(bout) }
                .buttonStyle(.plain)
        } else {
            boutBody(bout)
        }
    }

    private func boutBody(_ bout: ConceptBoutRow) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                if bout.isMainEvent {
                    Text("MAIN EVENT")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(.secondary)
                }
                Spacer()
                if bout.isSettled {
                    Text("Final")
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(.secondary)
                }
            }

            ForEach(Array(bout.fighters.enumerated()), id: \.offset) { index, fighter in
                HStack {
                    Text(fighter.name)
                        .font(.subheadline)
                        .fontWeight(emphasised(fighter, in: bout, at: index) ? .semibold : .regular)
                        .foregroundStyle(dimmed(fighter, in: bout) ? .secondary : .primary)
                        .lineLimit(1)
                    Spacer()
                    if bout.isSettled {
                        // Settled means settled: a decided bout shows who won,
                        // not a 99% that reads as live.
                        if bout.winner == fighter.name {
                            Text("Won")
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(.secondary)
                        }
                    } else {
                        // #6816: the pair is ONE decision, served by the
                        // builder; `nil` prints exactly what this printed before.
                        Text(formatProbabilityOrDash(
                            fighter.probability,
                            renderedPercent: bout.percents.indices.contains(index)
                                ? bout.percents[index] : nil))
                            .font(.subheadline)
                            .fontWeight(.semibold)
                            .monospacedDigit()
                            .foregroundStyle(index == 0 && fighter.probability != nil ? .blue : .secondary)
                    }
                }
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.secondary.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .contentShape(Rectangle())
        .accessibilityIdentifier("concept-bout-row")
    }

    private func emphasised(_ fighter: EventConceptOutcome, in bout: ConceptBoutRow, at index: Int) -> Bool {
        bout.isSettled ? bout.winner == fighter.name : (index == 0 && fighter.probability != nil)
    }

    private func dimmed(_ fighter: EventConceptOutcome, in bout: ConceptBoutRow) -> Bool {
        guard bout.isSettled, let winner = bout.winner else { return false }
        return winner != fighter.name
    }

    // MARK: - Unavailable / error

    /// The server said no such card. No Retry: it cannot change the answer.
    private var unavailableState: some View {
        VStack(spacing: 12) {
            Text("\(displayName) isn't available")
                .font(.subheadline.weight(.medium))
                .multilineTextAlignment(.center)
            if let domain = ConceptKey(key)?.domain {
                NavigationLink(value: Route.sportCategory(key: domain, name: sportCategoryDisplayName(domain))) {
                    Text("See all \(sportCategoryDisplayName(domain))")
                        .font(.subheadline.weight(.medium))
                        .foregroundStyle(.blue)
                }
            }
        }
        .padding()
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

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
