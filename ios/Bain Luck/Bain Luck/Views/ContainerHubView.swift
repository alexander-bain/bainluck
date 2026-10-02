import SwiftUI

/// #9652: the selected sensible-group treatment, using ordinary card routes.
/// It stays in its caller's NavigationStack, so Back reveals the same StateObject
/// and scroll binding rather than constructing a replacement hub.
struct ContainerHubView: View {
    let displayName: String
    @StateObject private var vm: ContainerHubViewModel

    init(slug: String, displayName: String, service: any ContainerHubLoading = ContainerHubService()) {
        self.displayName = displayName
        _vm = StateObject(wrappedValue: ContainerHubViewModel(slug: slug, service: service))
    }

    var body: some View {
        Group {
            switch vm.state {
            case .loading:
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            case .loaded(let presentation):
                hub(presentation)
            case .unavailable:
                status("This collection isn't available right now.", retry: false)
            case .error(let message):
                status(message, retry: true)
            }
        }
        .background(DS.surface)
        .navigationTitle(displayName)
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .task {
            // Returning revalidates publication/lifecycle while retaining the
            // existing view model and anchor. No new hub or loading skeleton.
            await vm.load()
            AnalyticsService.trackScreen(name: "collection_hub", type: vm.slug)
        }
    }

    private func hub(_ presentation: ContainerHubPresentation) -> some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 16) {
                if let title = presentation.title {
                    Text(title).font(.title2.weight(.bold)).foregroundStyle(DS.textPrimary)
                }
                if let note = presentation.note {
                    Text(note).font(.subheadline).foregroundStyle(DS.textSecondary)
                }
                ForEach(presentation.children) { child in
                    NavigationLink(value: Route.containerHub(slug: child.slug, name: child.name)) {
                        HStack {
                            Text(child.name).font(.headline)
                            Spacer()
                            Image(systemName: "chevron.right").font(.caption.weight(.semibold))
                        }
                        .foregroundStyle(DS.textPrimary)
                        .padding(16)
                        .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 12))
                    }
                    .buttonStyle(.plain)
                    .id("container:\(child.slug)")
                }
                // Standalone cards retain published section order. Questions
                // linked to a rendered event are reached through that game's page.
                ForEach(presentation.displaySections) { section in
                    Section {
                        ForEach(section.members) { member in
                            memberCard(member, presentation: presentation)
                                .id(member.id)
                        }
                    } header: {
                        Text(ContainerHubPresentation.sectionTitle(section.sectionClass))
                            .font(.headline)
                            .foregroundStyle(DS.textPrimary)
                            .padding(.top, 8)
                    }
                }
            }
            .scrollTargetLayout()
            .padding(18)
            .frame(maxWidth: 900, alignment: .leading)
            .frame(maxWidth: .infinity)
        }
        .scrollPosition(id: Binding(get: { vm.context.scrollMemberId }, set: { vm.scrolled(to: $0) }), anchor: .top)
        .refreshable { await vm.load() }
    }

    @ViewBuilder
    private func memberCard(_ member: ContainerHubMember, presentation: ContainerHubPresentation) -> some View {
        switch member.card {
        case .event(let event):
            VStack(alignment: .leading, spacing: 8) {
                NavigationLink(value: Route.eventDetail(id: member.memberId)) {
                    EventCardView(event: event, reason: nil)
                }
                .buttonStyle(.plain)
                .simultaneousGesture(TapGesture().onEnded { vm.opened(member) })
                // #10146: the game page is the fuller view of its questions; the hub
                // no longer expands hundreds of contracts inline under each card.
                if let route = presentation.moreOnGameRoute(for: member) {
                    NavigationLink(value: route) {
                        HStack {
                            Text("More on this game")
                            Spacer()
                            Image(systemName: "chevron.right").font(.caption.weight(.semibold))
                        }
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DS.textSecondary)
                        .padding(.vertical, 10)
                        .padding(.horizontal, 12)
                        .background(DS.surface, in: RoundedRectangle(cornerRadius: 8))
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .simultaneousGesture(TapGesture().onEnded { vm.opened(member) })
                    .accessibilityIdentifier("hub.moreOnGame.\(member.memberId)")
                }
            }
            .padding(14)
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 12))
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(DS.border, lineWidth: 0.5))
        case .question(let feed, let search):
            questionCard(member, feed: feed, search: search)
        case .unsupported:
            EmptyView() // Counted as partial; never given a destination.
        }
    }

    /// Standalone questions keep the familiar hydrated card and ordinary
    /// destination; never an opaque text link.
    private func questionCard(_ member: ContainerHubMember, feed: FeedFuturesData, search: SearchFuturesMarket) -> some View {
        NavigationLink(value: Route.futuresDetail(id: member.memberId)) {
            VStack(alignment: .leading, spacing: 8) {
                if let imageURL = feed.imageUrl {
                    FuturesHeroBackground(imageURL: imageURL, category: feed.llmSportCategory)
                        .frame(height: 120)
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                }
                if ContainerHubPresentation.questionNeedsVerdictRows(search) {
                    Text(search.name).font(.subheadline.weight(.semibold))
                        .fixedSize(horizontal: false, vertical: true)
                    ForEach(search.topOutcomes ?? []) { outcome in
                        HStack(alignment: .firstTextBaseline) {
                            Text(outcome.name).font(.caption)
                            Spacer(minLength: 8)
                            Text(ContainerHubPresentation.outcomeLabel(outcome, market: search))
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(outcome.verdict(in: search) == .won ? DS.emerald : DS.textSecondary)
                        }
                    }
                    if search.topOutcomes?.isEmpty != false {
                        Text("Result unavailable").font(.caption).foregroundStyle(DS.textSecondary)
                    }
                } else {
                    // This existing compact card omits missing prices rather
                    // than the Discover hero's current `nil -> 0%` treatment.
                    FuturesCardView(futures: feed)
                    if search.topOutcomes?.isEmpty != false {
                        Text("Prices aren't available right now.").font(.caption).foregroundStyle(DS.textSecondary)
                    } else if search.topOutcomes?.contains(where: { $0.probability == nil }) == true {
                        Text("Some prices aren't available right now.").font(.caption).foregroundStyle(DS.textSecondary)
                    }
                }
            }
            .foregroundStyle(DS.textPrimary)
            .padding(14)
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 12))
            .overlay(RoundedRectangle(cornerRadius: 12).stroke(DS.border, lineWidth: 0.5))
        }
        .buttonStyle(.plain)
        .simultaneousGesture(TapGesture().onEnded { vm.opened(member) })
    }

    private func status(_ message: String, retry: Bool) -> some View {
        VStack(spacing: 16) {
            Text(message).font(.subheadline).foregroundStyle(DS.textSecondary)
                .multilineTextAlignment(.center)
            if retry {
                Button("Try Again") { Task { await vm.load() } }.buttonStyle(.borderedProminent)
            }
        }
        .padding(24)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

/// Surface owners can pass the exact #9653 additive producer card here once
/// they place it. Deep links reach the same screen independently of placement.
struct ContainerHubCollectionLink: View {
    let collection: ContainerHubCollection

    var body: some View {
        if collection.canOpen {
            NavigationLink(value: Route.containerHub(slug: collection.slug, name: collection.name)) {
                HStack {
                    Text(collection.text).font(.headline)
                    Spacer()
                    Image(systemName: "chevron.right").font(.caption.weight(.semibold))
                }
                .foregroundStyle(DS.textPrimary)
                .padding(16)
                .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 12))
            }
            .buttonStyle(.plain)
        }
    }
}
