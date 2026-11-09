import StoreKit
import SwiftUI

/// #12307 — the clip's one page: the game or market the link names, read by the
/// saved widget's rules, then Apple's overlay offering the full app.
struct ClipPageView12307: View {
    let model: ClipModel12307
    @State private var showGetApp = false

    var body: some View {
        NavigationStack {
            ScrollView {
                content
                    .padding(.horizontal, 20)
                    .padding(.top, 8)
                    .frame(maxWidth: .infinity, alignment: .leading)
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
                    now: context.date,
                    lastUpdateFailed: model.lastUpdateFailed,
                    webURL: model.subject.flatMap(ClipInvocation12307.webURL(for:)),
                    getApp: { showGetApp = true })
            }
        case .unsupported:
            ClipMessageView12307(
                title: "Open a game from bainluck.com",
                detail: "This link doesn't name a game or market that Bain Luck can show here.",
                getApp: { showGetApp = true })
        case .gone:
            ClipMessageView12307(
                title: "This page isn't on Bain Luck anymore",
                detail: "The game or market this link names has been removed.",
                getApp: { showGetApp = true })
        case .unreachable:
            ClipMessageView12307(
                title: "Bain Luck can't be reached",
                detail: "Check your connection, then try again.",
                retry: { Task { await model.refresh() } },
                getApp: { showGetApp = true })
        }
    }
}

struct ClipReadingView12307: View {
    let reading: SavedWidgetReading10875
    let now: Date
    let lastUpdateFailed: Bool
    let webURL: URL?
    let getApp: () -> Void

    private var caption: String? {
        ClipLoader12307.caption(reading, now: now).map { clock in
            reading.priceCaption.map { "\($0) · \(clock)" } ?? clock
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(reading.status)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.secondary)
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
                }
                ForEach(Array(reading.rows.enumerated()), id: \.offset) { _, row in
                    ClipRowView12307(row: row)
                }
                if let caption {
                    Text(caption)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .accessibilityIdentifier("clipCaption")
                }
            }
            .padding(16)
            .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(Color(.secondarySystemBackground)))
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(reading.spoken + (caption.map { " \($0)." } ?? ""))

            if lastUpdateFailed {
                Label("Not updated: Bain Luck couldn't be reached.", systemImage: "wifi.exclamationmark")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }

            Button(action: getApp) {
                Label("Get Bain Luck for the whole game page", systemImage: "arrow.down.app")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .padding(.top, 8)

            if let webURL {
                Link("Open on bainluck.com", destination: webURL)
                    .font(.footnote)
                    .frame(maxWidth: .infinity)
            }
        }
    }
}

private struct ClipRowView12307: View {
    let row: SavedWidgetReading10875.Row

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            Text(row.label)
                .font(.body.weight(row.emphasized ? .semibold : .regular))
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 8)
            if let figure = row.figure {
                Text(figure)
                    .font(.title.weight(.bold).monospacedDigit())
            }
            if let verdict = row.verdict {
                Text(verdict)
                    .font(.headline)
                    .foregroundStyle(row.emphasized ? Color.green : Color.secondary)
            }
            if row.figure == nil && row.verdict == nil {
                Text("—")
                    .font(.title3)
                    .foregroundStyle(.secondary)
                    .accessibilityLabel("No number")
            }
        }
    }
}

private struct ClipMessageView12307: View {
    let title: String
    let detail: String
    var retry: (() -> Void)?
    let getApp: () -> Void

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
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .padding(.top, 8)
        }
        .padding(.top, 24)
    }
}
