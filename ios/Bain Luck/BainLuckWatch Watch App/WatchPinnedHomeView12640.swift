import SwiftUI
import WidgetKit

/// #12640 — Pins-driven Watch home screen (1.0.7, option A: phone sends pin IDs, Watch reads public endpoints).
/// Lists live games first, upcoming games soonest first, markets in pin order, and finished games most recent first.
/// Nothing without a probability is shown (except scored finals). One chosen item shows on the Watch face at a time.
struct WatchPinnedHomeView12640: View {
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @ObservedObject private var store = WatchPinsStore12640.shared
    @State private var choosingFromPins = false
    @State private var choosingOutcome = false
    @State private var showingHandoffHelp = false
    @State private var showingMoreActions = false

    var body: some View {
        ScrollViewReader { scroll in
            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    Color.clear.frame(height: 0).id("watch.pins.top").accessibilityHidden(true)

                    if !store.hasAnyPhonePins {
                        emptyPinsState
                    } else if let target = store.selectedTarget {
                        selectedDetailView(target)
                        footerActions
                    } else {
                        pinsPickerContent(inSheet: false)
                        footerActions
                    }
                }
                .padding(.horizontal, 6)
            }
            .navigationTitle(navigationTitle)
            .navigationBarTitleDisplayMode(store.selectedTarget == nil ? .automatic : .inline)
            .onOpenURL { url in
                guard WatchLaunchRoute.accepts(url) else { return }
                WatchTelemetry.shared.action(.complicationOpen, surface: store.selectedTarget == nil ? .picker : .game)
                choosingFromPins = false
                choosingOutcome = false
                showingHandoffHelp = false
                scroll.scrollTo("watch.pins.top", anchor: .top)
            }
            .onAppear {
                #if DEBUG
                if ProcessInfo.processInfo.environment["BAINLUCK_WATCH_PINS_FIXTURE_12640"] == "outcome-picker" {
                    choosingOutcome = true
                } else if ProcessInfo.processInfo.environment["BAINLUCK_WATCH_PINS_FIXTURE_12640"] == "overflow-11" {
                    DispatchQueue.main.async {
                        scroll.scrollTo("watch.pins.overflow", anchor: .bottom)
                    }
                } else if ProcessInfo.processInfo.environment["BAINLUCK_WATCH_PINS_FIXTURE_12640"] == "partial-error" {
                    DispatchQueue.main.async {
                        scroll.scrollTo("watch.pins.partial-error", anchor: .bottom)
                    }
                }
                #endif
                WatchTelemetry.shared.pullWatchPinsIfReachable()
                store.triggerRefresh()
            }
            .onChange(of: scenePhase) { _, phase in
                if phase == .active {
                    WatchTelemetry.shared.pullWatchPinsIfReachable()
                    store.triggerRefresh()
                }
            }
            .sheet(isPresented: $choosingFromPins) {
                NavigationStack {
                    ScrollView {
                        pinsPickerContent(inSheet: true)
                            .padding(.horizontal, 6)
                    }
                    .navigationTitle("Pins")
                    .toolbar {
                        ToolbarItem(placement: .cancellationAction) {
                            Button {
                                choosingFromPins = false
                            } label: {
                                Image(systemName: "chevron.backward")
                            }
                            .accessibilityLabel("Back")
                            .accessibilityIdentifier("watch.pins.sheet.cancel")
                        }
                    }
                }
            }
            .sheet(isPresented: $choosingOutcome) {
                if case .future(let marketID, _) = store.selectedTarget,
                   let market = store.futuresByID[marketID] {
                    NavigationStack {
                        outcomePickerContent(market: market)
                            .navigationTitle("Outcome")
                            .toolbar {
                                ToolbarItem(placement: .cancellationAction) {
                                    Button {
                                        choosingOutcome = false
                                    } label: {
                                        Image(systemName: "chevron.backward")
                                    }
                                    .accessibilityLabel("Back")
                                    .accessibilityIdentifier("watch.pins.outcome.cancel")
                                }
                            }
                    }
                }
            }
            .userActivity(GameContinuation.activityType, element: activeEventContinuationID) { id, activity in
                GameContinuation.configure(activity, eventID: id)
            }
            .userActivity(StoryContinuation.activityType, element: activeFutureContinuation) { destination, activity in
                StoryContinuation.configure(activity, destination: destination)
            }
            .alert("Continue on iPhone", isPresented: $showingHandoffHelp) {
                Button("OK", role: .cancel) {}
            } message: {
                Text("Look for Bain Luck’s Handoff banner at the bottom of your iPhone’s App Switcher. Both devices need Handoff on and the same Apple Account.")
            }
            #if DEBUG
            if let faceScenario = ProcessInfo.processInfo.environment["BAINLUCK_WATCH_PINS_FACE_PREVIEW_12640"],
               !faceScenario.isEmpty {
                EmptyView()
            }
            #endif
        }
    }

    private var navigationTitle: String {
        if !store.hasAnyPhonePins { return "Pins" }
        switch store.selectedTarget {
        case .event: return "Your game"
        case .future: return "Your market"
        case nil: return "Pins"
        }
    }

    private var activeEventContinuationID: Int? {
        guard scenePhase == .active, !choosingFromPins, !choosingOutcome,
              case .event(let id) = store.selectedTarget else { return nil }
        return id
    }

    private var activeFutureContinuation: StoryContinuationDestination? {
        guard scenePhase == .active, !choosingFromPins, !choosingOutcome,
              case .future(let marketID, _) = store.selectedTarget else { return nil }
        return .futures(marketID)
    }

    // MARK: - Empty State

    private var emptyPinsState: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Pin a game or market on your iPhone to see it here")
                .font(.headline)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("watch.pins.empty")
        }
    }

    // MARK: - 4-Bucket Pins List

    private func pinsPickerContent(inSheet: Bool) -> some View {
        let entries = store.displayedEntries
        return VStack(alignment: .leading, spacing: 10) {
            if !inSheet {
                Text("Pinned on iPhone")
                    .font(.headline)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.isHeader)
                    .accessibilityIdentifier("watch.pins.heading")
            }

            if entries.isEmpty {
                if store.isRefreshing {
                    ProgressView("Loading pins")
                        .accessibilityIdentifier("watch.pins.loading")
                } else if let error = store.lastRefreshError {
                    Text(error)
                        .font(.footnote).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier("watch.pins.error")
                } else {
                    Text("Pin a game or market on your iPhone to see it here")
                        .font(.footnote).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier("watch.pins.none-priced")
                }
            } else {
                TimelineView(.periodic(from: .now, by: 30)) { context in
                    VStack(alignment: .leading, spacing: 8) {
                        ForEach(entries) { entry in
                            pinRowButton(entry: entry, now: context.date, inSheet: inSheet)
                        }
                    }
                }
                if let failedLine = store.failedLoadLine {
                    Text(failedLine)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .id("watch.pins.partial-error")
                        .accessibilityIdentifier("watch.pins.partial-error")
                }
                if let overflowLine = store.overflowFooterLine {
                    Text(overflowLine)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .id("watch.pins.overflow")
                        .accessibilityIdentifier("watch.pins.overflow")
                }
            }

            Button {
                WatchTelemetry.shared.pullWatchPinsIfReachable()
                store.triggerRefresh()
            } label: {
                Label(store.isRefreshing ? "Refreshing…" : "Refresh pins", systemImage: "arrow.clockwise")
                    .font(.footnote.weight(.semibold))
                    .padding(.horizontal, 8)
                    .frame(maxWidth: .infinity, minHeight: 44)
                    .background(.quaternary, in: RoundedRectangle(cornerRadius: 12))
            }
            .buttonStyle(.plain)
            .disabled(store.isRefreshing)
            .accessibilityIdentifier("watch.pins.refresh")
        }
    }

    @ViewBuilder
    private func pinRowButton(entry: WatchPinnedOrderedEntry12640, now: Date, inSheet: Bool) -> some View {
        switch entry.wireItem.kind {
        case .event:
            if let game = store.eventsByID[entry.wireItem.id] {
                let isSelected: Bool = {
                    if case .event(let sid) = store.selectedTarget { return sid == game.id }
                    return false
                }()
                Button {
                    store.selectEvent(game.id)
                    if inSheet { choosingFromPins = false }
                } label: {
                    eventPinCard(game: game, isSelected: isSelected, now: now)
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("watch.pins.event.\(game.id)")
            }
        case .future:
            if let market = store.futuresByID[entry.wireItem.id],
               let outcome = market.resolvedOutcome(
                   chosenOutcomeID: store.chosenOutcomes[market.id],
                   wireOutcomeID: entry.wireItem.outcomeId
               ),
               let formatted = outcome.formattedProbability {
                let isSelected: Bool = {
                    if case .future(let mid, _) = store.selectedTarget { return mid == market.id }
                    return false
                }()
                Button {
                    store.selectFuture(market.id, outcomeID: outcome.id)
                    if inSheet { choosingFromPins = false }
                } label: {
                    marketPinCard(
                        market: market,
                        outcome: outcome,
                        probabilityText: formatted.display,
                        isSelected: isSelected
                    )
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("watch.pins.future.\(market.id)")
            }
        }
    }

    private func eventPinCard(game: WatchSelectedGame, isSelected: Bool, now: Date) -> some View {
        let awayShort = game.awayCompactIdentity?.abbreviation ?? game.awayTeam
        let homeShort = game.homeCompactIdentity?.abbreviation ?? game.homeTeam
        return VStack(alignment: .leading, spacing: 3) {
            HStack(alignment: .firstTextBaseline, spacing: 4) {
                Text(eventRowBadge(game: game, now: now))
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(game.isLive ? Color.cyan : Color.secondary)
                Spacer(minLength: 4)
                if isSelected {
                    Image(systemName: "bookmark.fill")
                        .font(.caption2)
                        .foregroundStyle(.orange)
                }
            }
            Text(eventRowMatchup(game: game, awayShort: awayShort, homeShort: homeShort))
                .font(.footnote.weight(.semibold))
                .fixedSize(horizontal: false, vertical: true)

            if game.isFinal, let hs = game.homeScore, let ascore = game.awayScore {
                Text(hs >= ascore ? "\(homeShort) \(hs), \(awayShort) \(ascore)" : "\(awayShort) \(ascore), \(homeShort) \(hs)")
                    .font(.body.bold())
                    .monospacedDigit()
            } else if let pct = game.homeProbabilityText {
                Text("\(homeShort) \(pct)")
                    .font(.title3.bold())
                    .monospacedDigit()
                    .foregroundStyle(.cyan)
            }
        }
        .padding(8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.quaternary, in: RoundedRectangle(cornerRadius: 12))
    }

    private func eventRowBadge(game: WatchSelectedGame, now: Date) -> String {
        if game.isFinal { return "Final" }
        if game.isLive {
            if let clock = game.liveClockText, !clock.isEmpty { return "Live · \(clock)" }
            return "Live"
        }
        if let start = game.commenceTime {
            if now >= start { return "Open to update" }
            return WatchRectangularReading.upcomingStartClock(start, now: now)
        }
        return game.stateLabel
    }

    private func eventRowMatchup(game: WatchSelectedGame, awayShort: String, homeShort: String) -> String {
        let base = "\(game.awayTeam) at \(game.homeTeam)"
        if game.isLive, let ascore = game.awayScore, let hs = game.homeScore {
            return "\(awayShort) at \(homeShort) · \(ascore)–\(hs)"
        }
        return base
    }

    private func marketPinCard(
        market: WatchFutureDetail12640,
        outcome: WatchFutureOutcome12640,
        probabilityText: String,
        isSelected: Bool
    ) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(alignment: .firstTextBaseline, spacing: 4) {
                Text("Market")
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(.secondary)
                Spacer(minLength: 4)
                if isSelected {
                    Image(systemName: "bookmark.fill")
                        .font(.caption2)
                        .foregroundStyle(.orange)
                }
            }
            Text(market.name)
                .font(.footnote.weight(.semibold))
                .fixedSize(horizontal: false, vertical: true)
            Text("\(outcome.name) \(probabilityText)")
                .font(.title3.bold())
                .monospacedDigit()
                .foregroundStyle(.cyan)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.quaternary, in: RoundedRectangle(cornerRadius: 12))
    }

    // MARK: - Selected Detail Views

    @ViewBuilder
    private func selectedDetailView(_ target: WatchSelectedPinTarget12640) -> some View {
        switch target {
        case .event(let id):
            if let game = store.eventsByID[id] {
                selectedEventView(game)
            } else {
                ProgressView("Loading game")
            }
        case .future(let marketID, let explicitOutcomeID):
            if let market = store.futuresByID[marketID] {
                selectedFutureView(market: market, explicitOutcomeID: explicitOutcomeID)
            } else {
                ProgressView("Loading market")
            }
        }
    }

    private func selectedEventView(_ game: WatchSelectedGame) -> some View {
        let homeShort = game.homeCompactIdentity?.abbreviation ?? game.homeTeam
        let awayShort = game.awayCompactIdentity?.abbreviation ?? game.awayTeam
        return TimelineView(.periodic(from: .now, by: 15)) { context in
            let now = context.date
            VStack(alignment: .leading, spacing: 6) {
                Text("\(game.awayTeam) at \(game.homeTeam)")
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("watch.pins.selected.event.header")

                if game.isFinal, let hs = game.homeScore, let ascore = game.awayScore {
                    Text(hs >= ascore
                         ? "Final · \(homeShort) \(hs), \(awayShort) \(ascore)"
                         : "Final · \(awayShort) \(ascore), \(homeShort) \(hs)")
                        .font(.title3.bold())
                        .monospacedDigit()
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier("watch.pins.selected.event.final")
                    if let obs = game.scoreObservedAt,
                       let compact = WatchRectangularReading.compactAge(observedAt: obs, now: now) {
                        Text(compact)
                            .font(.footnote).foregroundStyle(.secondary)
                    }
                } else if let pct = game.homeProbabilityText {
                    Text("\(homeShort) win")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.secondary)
                    Text(pct)
                        .font(dynamicTypeSize.isAccessibilitySize
                              ? .title2.bold()
                              : .system(size: 34, weight: .bold, design: .rounded))
                        .monospacedDigit()
                        .foregroundStyle(.cyan)
                        .accessibilityIdentifier("watch.pins.selected.event.probability")

                    if game.isLive, let ascore = game.awayScore, let hs = game.homeScore {
                        Text("\(awayShort) \(ascore) – \(homeShort) \(hs)")
                            .font(.body.bold())
                            .monospacedDigit()
                            .accessibilityIdentifier("watch.pins.selected.event.score")
                    }

                    Text(selectedEventClockLine(game: game, now: now))
                        .font(.footnote).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier("watch.pins.selected.event.clock")
                }

                selectedActionButtons(allowsOutcomeChoice: false, outcomeCount: 0)
            }
        }
    }

    private func selectedEventClockLine(game: WatchSelectedGame, now: Date) -> String {
        if game.isLive {
            if let obs = game.probabilityObservedAt {
                if now.timeIntervalSince(obs) > WatchRectangularReading.liveAgeThresholdSeconds {
                    return "As of \(WatchRectangularReading.asOfClock(obs))"
                }
                if let age = WatchRectangularReading.compactAge(observedAt: obs, now: now) {
                    return "Live · \(age)"
                }
            }
            return "Live"
        }
        if let start = game.commenceTime {
            if now >= start { return "Open to update" }
            return WatchRectangularReading.upcomingStartClock(start, now: now)
        }
        return game.stateLabel
    }

    private func selectedFutureView(market: WatchFutureDetail12640, explicitOutcomeID: Int?) -> some View {
        let wireOutcome = store.wireItems.first { $0.kind == .future && $0.id == market.id }?.outcomeId
        let chosen = market.resolvedOutcome(
            chosenOutcomeID: explicitOutcomeID ?? store.chosenOutcomes[market.id],
            wireOutcomeID: wireOutcome
        )
        let pricedCount = market.pricedOutcomes.count
        return TimelineView(.periodic(from: .now, by: 15)) { context in
            let now = context.date
            VStack(alignment: .leading, spacing: 6) {
                Text(market.name)
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("watch.pins.selected.future.title")

                if let outcome = chosen, let formatted = outcome.formattedProbability {
                    Text(outcome.name)
                        .font(.headline)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier("watch.pins.selected.future.outcome")
                    Text(formatted.display)
                        .font(dynamicTypeSize.isAccessibilitySize
                              ? .title2.bold()
                              : .system(size: 34, weight: .bold, design: .rounded))
                        .monospacedDigit()
                        .foregroundStyle(.cyan)
                        .accessibilityIdentifier("watch.pins.selected.future.probability")

                    let obs = outcome.effectiveObservedAt ?? market.updatedAt
                    if let obs {
                        let ageLine: String = {
                            if now.timeIntervalSince(obs) > WatchRectangularReading.liveAgeThresholdSeconds {
                                return "As of \(WatchRectangularReading.asOfClock(obs))"
                            }
                            return WatchRectangularReading.compactAge(observedAt: obs, now: now) ?? "As of \(WatchRectangularReading.asOfClock(obs))"
                        }()
                        Text(ageLine)
                            .font(.footnote).foregroundStyle(.secondary)
                            .accessibilityIdentifier("watch.pins.selected.future.clock")
                    }
                }

                selectedActionButtons(allowsOutcomeChoice: pricedCount > 1, outcomeCount: pricedCount)
            }
        }
    }

    private func selectedActionButtons(allowsOutcomeChoice: Bool, outcomeCount: Int) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            if allowsOutcomeChoice {
                Button {
                    choosingOutcome = true
                } label: {
                    Label("Choose outcome (\(outcomeCount))", systemImage: "list.bullet")
                        .font(.footnote.weight(.semibold))
                        .padding(.horizontal, 8)
                        .frame(maxWidth: .infinity, minHeight: 44)
                        .background(.quaternary, in: RoundedRectangle(cornerRadius: 12))
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("watch.pins.choose-outcome")
            }

            Button {
                store.triggerRefresh()
            } label: {
                Label(store.isRefreshing ? "Refreshing…" : "Refresh", systemImage: "arrow.clockwise")
                    .font(.footnote.weight(.semibold))
                    .padding(.horizontal, 8)
                    .frame(maxWidth: .infinity, minHeight: 44)
                    .background(.quaternary, in: RoundedRectangle(cornerRadius: 12))
            }
            .buttonStyle(.plain)
            .disabled(store.isRefreshing)
            .accessibilityIdentifier("watch.pins.selected.refresh")

            Button {
                choosingFromPins = true
            } label: {
                Text("Choose another pin")
                    .font(.footnote.weight(.semibold))
                    .padding(.horizontal, 8)
                    .frame(maxWidth: .infinity, minHeight: 44)
                    .background(.quaternary, in: RoundedRectangle(cornerRadius: 12))
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("watch.pins.choose-another")
        }
        .padding(.top, 4)
    }

    private func outcomePickerContent(market: WatchFutureDetail12640) -> some View {
        let currentOutcomeID = market.resolvedOutcome(
            chosenOutcomeID: store.chosenOutcomes[market.id],
            wireOutcomeID: store.wireItems.first { $0.kind == .future && $0.id == market.id }?.outcomeId
        )?.id
        return ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                Text("Show on Watch face")
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)

                ForEach(market.pricedOutcomes) { outcome in
                    if let formatted = outcome.formattedProbability {
                        Button {
                            store.chooseFutureOutcome(marketID: market.id, outcomeID: outcome.id)
                            choosingOutcome = false
                        } label: {
                            HStack(alignment: .firstTextBaseline, spacing: 6) {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(outcome.name)
                                        .font(.footnote.weight(.semibold))
                                        .fixedSize(horizontal: false, vertical: true)
                                    Text(formatted.display)
                                        .font(.body.bold())
                                        .monospacedDigit()
                                        .foregroundStyle(.cyan)
                                }
                                Spacer(minLength: 4)
                                if outcome.id == currentOutcomeID {
                                    Image(systemName: "checkmark.circle.fill")
                                        .foregroundStyle(.cyan)
                                }
                            }
                            .padding(8)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(.quaternary, in: RoundedRectangle(cornerRadius: 12))
                        }
                        .buttonStyle(.plain)
                        .accessibilityIdentifier("watch.pins.outcome.\(outcome.id)")
                    }
                }
            }
            .padding(.horizontal, 6)
        }
    }

    // MARK: - Footer Actions

    private var footerActions: some View {
        VStack(alignment: .leading, spacing: 8) {
            Button {
                showingMoreActions.toggle()
            } label: {
                Label("More actions", systemImage: showingMoreActions ? "chevron.up" : "chevron.down")
                    .font(.footnote.weight(.semibold))
                    .padding(.horizontal, 8)
                    .frame(maxWidth: .infinity, minHeight: 44)
                    .background(.quaternary, in: RoundedRectangle(cornerRadius: 12))
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("watch.pins.more-actions")

            if showingMoreActions {
                if store.selectedTarget != nil {
                    Button {
                        showingHandoffHelp = true
                    } label: {
                        Text("Continue on iPhone")
                            .font(.footnote.weight(.semibold))
                            .padding(.horizontal, 8)
                            .frame(maxWidth: .infinity, minHeight: 44)
                            .background(.quaternary, in: RoundedRectangle(cornerRadius: 12))
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("watch.pins.continue-on-phone")
                }
                NavigationLink("Diagnostics") {
                    WatchDiagnosticsView().dynamicTypeSize(dynamicTypeSize)
                }
                .accessibilityIdentifier("watch.diagnostics")
            }

            if store.selectedTarget != nil {
                Divider()
                Button {
                    choosingFromPins = false
                    choosingOutcome = false
                    showingHandoffHelp = false
                    store.clearSelection()
                } label: {
                    Text("Clear selection")
                        .font(.footnote).foregroundStyle(.primary)
                        .padding(.horizontal, 8)
                        .frame(maxWidth: .infinity, minHeight: 44)
                        .contentShape(RoundedRectangle(cornerRadius: 12))
                        .overlay(RoundedRectangle(cornerRadius: 12).stroke(.quaternary, lineWidth: 1))
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("watch.pins.clear-selection")
            }
        }
    }
}

#if DEBUG
/// Renders the rectangular Watch face slot directly for `#12640` face previews (days-away game + future outcome).
struct WatchPinsFacePreviewFixture12640: View {
    let scenario: String

    var body: some View {
        let now = Date()
        let snapshot = makeSnapshot(now: now)
        VStack(spacing: 8) {
            WatchSavedComplicationContent(snapshot: snapshot, now: now)
                .frame(width: 156, height: 76, alignment: .leading)
                .padding(6)
                .background(Color.black)
                .overlay(RoundedRectangle(cornerRadius: 10).stroke(.gray.opacity(0.5), lineWidth: 1))
            Text("Face slot · \(scenario)")
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .environment(\.widgetRenderingMode, .fullColor)
        .navigationTitle("Watch face")
    }

    private func makeSnapshot(now: Date) -> WatchComplicationSnapshot? {
        switch scenario {
        case "future":
            return WatchComplicationProjection.futureSnapshot(
                marketID: 9303,
                marketTitle: "2028 Democratic Nominee",
                outcomeName: "Newsom",
                probability: 0.23,
                observedAt: now.addingTimeInterval(-3600),
                savedAt: now
            )
        case "days-away":
            var calendar = Calendar(identifier: .gregorian)
            calendar.timeZone = .current
            var comps = calendar.dateComponents([.yearForWeekOfYear, .weekOfYear], from: now.addingTimeInterval(3 * 86400))
            comps.weekday = 1
            comps.hour = 13
            comps.minute = 25
            let sunday = calendar.date(from: comps) ?? now.addingTimeInterval(3 * 86400)
            let reading = WatchRectangularReading(
                version: 1,
                eventID: 9202,
                kind: .scheduledForecast,
                homeName: "Kansas City Chiefs",
                awayName: "Buffalo Bills",
                home: WatchCompactTeamIdentity(teamID: 11, abbreviation: "KC"),
                away: WatchCompactTeamIdentity(teamID: 12, abbreviation: "BUF"),
                homePercent: 58,
                homeScore: nil,
                awayScore: nil,
                commenceTime: sunday,
                stateLabel: "Scheduled",
                observedAt: now.addingTimeInterval(-180),
                scoreObservedAt: nil
            )
            return WatchComplicationSnapshot(
                version: 1,
                eventID: 9202,
                title: "Kansas City Chiefs win",
                detail: "58% · Scheduled",
                observedAt: now.addingTimeInterval(-180),
                savedAt: now,
                circularReading: nil,
                rectangularReading: reading
            )
        default:
            return nil
        }
    }
}
#endif
