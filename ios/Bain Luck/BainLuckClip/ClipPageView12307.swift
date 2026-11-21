import StoreKit
import SwiftUI

/// #12307 — the clip's one page: the game or market the link names, read by the
/// saved widget's rules, then Apple's overlay offering the full app.
struct ClipPageView12307: View {
    let model: ClipModel12307
    @State private var showGetApp = false

    var body: some View {
        NavigationStack {
            ScrollViewReader { proxy in
                ScrollView {
                    content
                        .padding(.horizontal, 20)
                        .padding(.top, 8)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                #if DEBUG
                .onChange(of: model.load) { _, load in
                    if case .detail = load,
                       ProcessInfo.processInfo.environment["_XCAppClipDemoScrollBottom"] == "1" {
                        Task { @MainActor in
                            try? await Task.sleep(for: .milliseconds(350))
                            proxy.scrollTo("clipBottomAnchor", anchor: .bottom)
                        }
                    }
                }
                #endif
            }
            .navigationTitle("Bain Luck")
            .navigationBarTitleDisplayMode(.inline)
        }
        .task {
            try? await Task.sleep(for: ClipModel12307.invocationWait)
            if model.subject == nil { model.noInvocation() }
        }
        .task(id: model.subject) {
            guard model.subject != nil else { return }
            while !Task.isCancelled {
                await model.refresh()
                try? await Task.sleep(for: ClipModel12307.refreshEvery)
            }
        }
        .onChange(of: model.load) { _, load in
            // Offered once the page has something to show, as Apple suggests:
            // after the reader has what they came for.
            if case .detail = load { showGetApp = true }
        }
        .appStoreOverlay(isPresented: $showGetApp) {
            SKOverlay.AppClipConfiguration(position: .bottom)
        }
    }

    @ViewBuilder private var content: some View {
        switch model.load {
        case .loading:
            ProgressView("Loading…")
                .frame(maxWidth: .infinity, minHeight: 240)
        case .detail(let payload):
            // Read again every 30 s, so a current price turns "last recorded" on
            // its own clock between refreshes, as the widget's timeline does.
            TimelineView(.periodic(from: .now, by: 30)) { context in
                ClipReadingView12307(
                    reading: ClipLoader12307.reading(payload, at: context.date),
                    scoreClock: ClipLoader12307.gameScoreClock(payload),
                    subjectKind: model.subject?.kind ?? .game,
                    now: context.date,
                    lastUpdateFailed: model.lastUpdateFailed,
                    webURL: model.subject.flatMap(ClipInvocation12307.webURL(for:)),
                    getApp: presentGetApp)
            }
        case .unsupported:
            ClipMessageView12307(
                title: "Open a game from bainluck.com",
                detail: "This link doesn't name a game or market that Bain Luck can show here.",
                getApp: presentGetApp)
        case .gone:
            ClipMessageView12307(
                title: "This page isn't on Bain Luck anymore",
                detail: "The game or market this link names has been removed.",
                getApp: presentGetApp)
        case .unreachable:
            ClipMessageView12307(
                title: "Bain Luck can't be reached",
                detail: "Check your connection, then try again.",
                retry: { Task { await model.refresh() } },
                getApp: presentGetApp)
        }
    }

    private func presentGetApp() {
        ClipTelemetry13261.recordGetAppTap(subject: model.subject)
        showGetApp = true
    }
}

struct ClipReadingView12307: View {
    let reading: SavedWidgetReading10875
    let scoreClock: ClipGameScoreClock12307?
    let subjectKind: SavedWidgetSubject10875.Kind
    let now: Date
    let lastUpdateFailed: Bool
    let webURL: URL?
    let getApp: () -> Void

    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    private var getAppButtonTitle: String {
        switch subjectKind {
        case .game: return "Get Bain Luck for the whole game page"
        case .market: return "Get Bain Luck for the whole market page"
        }
    }

    private var statusLine: String {
        ClipLoader12307.statusText(for: reading, scoreClock: scoreClock)
    }

    private var showsLiveScoreColumn: Bool {
        scoreClock?.hasLiveScores == true && reading.rows.count == 2
    }

    private var caption: String? {
        ClipLoader12307.caption(reading, now: now).map { clock in
            reading.priceCaption.map { "\($0) · \(clock)" } ?? clock
        }
    }

    private var accessibilitySummary: String {
        var parts = [reading.spoken]
        if let clock = scoreClock?.clockLine, !reading.spoken.contains(clock) {
            parts.append(clock)
        }
        if let caption { parts.append(caption) }
        return parts.joined(separator: " ")
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(statusLine)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityIdentifier("clipStatus")
            Text(reading.subject)
                .font(.title2.weight(.bold))
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
                .accessibilityIdentifier("clipSubject")

            VStack(spacing: 12) {
                if reading.rows.isEmpty {
                    Text(reading.phase == .noResult ? "No result recorded" : "No chance to show")
                        .font(.body.weight(.medium))
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                } else if showsLiveScoreColumn && !dynamicTypeSize.isAccessibilitySize {
                    HStack(spacing: 12) {
                        Spacer(minLength: 8)
                        Text("Score")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                            .fixedSize(horizontal: true, vertical: false)
                            .frame(minWidth: 44, alignment: .trailing)
                        Text("Now")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                            .fixedSize(horizontal: true, vertical: false)
                            .frame(minWidth: 68, alignment: .trailing)
                    }
                }
                ForEach(Array(reading.rows.enumerated()), id: \.offset) { index, row in
                    ClipRowView12307(
                        row: row,
                        liveScore: scoreClock?.score(forRowIndex: index),
                        alignColumns: showsLiveScoreColumn && !dynamicTypeSize.isAccessibilitySize
                    )
                }
                if let caption {
                    Text(caption)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .accessibilityIdentifier("clipCaption")
                }
            }
            .padding(16)
            .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(Color(.secondarySystemBackground)))
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(accessibilitySummary)

            if lastUpdateFailed {
                Label("Not updated: Bain Luck couldn't be reached.", systemImage: "wifi.exclamationmark")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }

            Button(action: getApp) {
                Label(getAppButtonTitle, systemImage: "arrow.down.app")
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, dynamicTypeSize.isAccessibilitySize ? 6 : 2)
            }
            .buttonStyle(.borderedProminent)
            .buttonBorderShape(dynamicTypeSize.isAccessibilitySize ? .roundedRectangle(radius: 14) : .capsule)
            .controlSize(.large)
            .padding(.top, 8)
            .accessibilityIdentifier("clipGetAppButton")

            if let webURL {
                Link("Open on bainluck.com", destination: webURL)
                    .font(.footnote)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity)
                    .padding(.bottom, 16)
                    .accessibilityIdentifier("clipWebLink")
                    .id("clipBottomAnchor")
            }
        }
    }
}

private struct ClipRowView12307: View {
    let row: SavedWidgetReading10875.Row
    let liveScore: String?
    let alignColumns: Bool

    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    @ViewBuilder private var accessibilityFigures: some View {
        if let liveScore {
            Text("Score \(liveScore)")
                .font(.subheadline.weight(.semibold).monospacedDigit())
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .fixedSize(horizontal: true, vertical: false)
        }
        if let figure = row.figure {
            Text(figure)
                .font(.title.weight(.bold).monospacedDigit())
                .lineLimit(1)
                .fixedSize(horizontal: true, vertical: false)
        }
        if let verdict = row.verdict {
            Text(verdict)
                .font(.headline)
                .foregroundStyle(row.emphasized ? Color.green : Color.secondary)
                .lineLimit(1)
                .fixedSize(horizontal: true, vertical: false)
        }
    }

    @ViewBuilder private var numbers: some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            if let liveScore {
                Text(liveScore)
                    .font(.title3.weight(.semibold).monospacedDigit())
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .fixedSize(horizontal: true, vertical: false)
                    .frame(minWidth: alignColumns ? 44 : nil, alignment: .trailing)
            }
            if let figure = row.figure {
                Text(figure)
                    .font(.title.weight(.bold).monospacedDigit())
                    .lineLimit(1)
                    .fixedSize(horizontal: true, vertical: false)
                    .frame(minWidth: alignColumns ? 68 : nil, alignment: .trailing)
            }
            if let verdict = row.verdict {
                Text(verdict)
                    .font(.headline)
                    .foregroundStyle(row.emphasized ? Color.green : Color.secondary)
                    .lineLimit(1)
                    .fixedSize(horizontal: true, vertical: false)
            }
            if liveScore == nil && row.figure == nil && row.verdict == nil {
                Text("—")
                    .font(.title3)
                    .foregroundStyle(.secondary)
                    .accessibilityLabel("No number")
            }
        }
    }

    var body: some View {
        if dynamicTypeSize.isAccessibilitySize {
            VStack(alignment: .leading, spacing: 4) {
                Text(row.label)
                    .font(.body.weight(row.emphasized ? .semibold : .regular))
                    .fixedSize(horizontal: false, vertical: true)
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .firstTextBaseline, spacing: 12) {
                        accessibilityFigures
                    }
                    VStack(alignment: .leading, spacing: 2) {
                        accessibilityFigures
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        } else {
            HStack(alignment: .firstTextBaseline, spacing: 12) {
                Text(row.label)
                    .font(.body.weight(row.emphasized ? .semibold : .regular))
                    .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 8)
                numbers
            }
        }
    }
}

private struct ClipMessageView12307: View {
    let title: String
    let detail: String
    var retry: (() -> Void)?
    let getApp: () -> Void

    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(title)
                .font(.title3.weight(.bold))
                .fixedSize(horizontal: false, vertical: true)
            Text(detail)
                .font(.body)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            if let retry {
                Button("Try again", action: retry)
                    .buttonStyle(.bordered)
            }
            Button(action: getApp) {
                Label("Get Bain Luck", systemImage: "arrow.down.app")
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, dynamicTypeSize.isAccessibilitySize ? 6 : 2)
            }
            .buttonStyle(.borderedProminent)
            .buttonBorderShape(dynamicTypeSize.isAccessibilitySize ? .roundedRectangle(radius: 14) : .capsule)
            .controlSize(.large)
            .padding(.top, 8)
        }
        .padding(.top, 24)
    }
}
