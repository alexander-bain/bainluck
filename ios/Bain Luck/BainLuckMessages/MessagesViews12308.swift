import SwiftUI

/// #12308 — the card. Opened from the thread, it draws the current reading.
/// Sent, it is rendered to the picture the thread shows: the title and the
/// line only, clear of the corner where Messages badges the app, because the
/// message's caption carries the dated standing as text beneath it.
struct MessageCardView12308: View {
    let card: MessageCard12308
    /// The picture that goes into the thread, rather than the live card.
    var sent = false

    static let width: CGFloat = 320
    static let height: CGFloat = 132
    static let sentHeight: CGFloat = 96

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            if sent {
                // Messages draws the app's badge over this corner.
                Spacer(minLength: 0)
            } else {
                HStack(spacing: 6) {
                    CloverMark12308()
                    Text("Bain Luck")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(Color.secondary)
                }
                Spacer(minLength: 0)
            }
            Text(card.title)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(Color.primary)
                .lineLimit(1)
                .minimumScaleFactor(0.8)
            Text(card.line)
                .font(.title3.weight(.bold).monospacedDigit())
                .foregroundStyle(Color.primary)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
            if !sent {
                Text(card.status)
                    .font(.caption2)
                    .foregroundStyle(Color.secondary)
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, minHeight: sent ? Self.sentHeight : Self.height,
               maxHeight: sent ? Self.sentHeight : Self.height, alignment: .topLeading)
        .background(Color(uiColor: .systemBackground))
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(sent ? card.sentSpoken : card.spoken)
    }
}

/// The app's clover, from the icon's own outline, in the clover's green.
struct CloverMark12308: View {
    var body: some View {
        Image("Clover")
            .renderingMode(.template)
            .resizable()
            .scaledToFit()
            .frame(width: 13, height: 13)
            .foregroundStyle(Color(red: 0.24, green: 0.62, blue: 0.16))
            .accessibilityHidden(true)
    }
}

/// While an opened card loads, or when it can't: the item's kind, never a
/// number that isn't there.
struct MessageCardPlaceholder12308: View {
    let subject: SavedWidgetSubject10875
    let reading: MessageCardReading12308?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                CloverMark12308()
                Text("Bain Luck")
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(Color.secondary)
            }
            switch reading {
            case .gone?:
                Text("This \(subject.kind == .game ? "game" : "market") is no longer on Bain Luck.")
                    .font(.subheadline)
            case .unreachable?:
                Text("Can't reach Bain Luck right now.")
                    .font(.subheadline)
            default:
                ProgressView()
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, minHeight: MessageCardView12308.height,
               maxHeight: MessageCardView12308.height, alignment: .topLeading)
        .background(Color(uiColor: .systemBackground))
    }
}

/// Everything the extension draws: the picker, or a card opened from the thread.
struct MessagesRootView12308: View {
    @ObservedObject var model: MessagesModel12308
    let send: (MessageCard12308) -> Void
    let open: (URL) -> Void

    var body: some View {
        switch model.screen {
        case .picker:
            picker
        case .card(let subject):
            opened(subject)
        }
    }

    /// The item's current reading, and the way into the app.
    private func opened(_ subject: SavedWidgetSubject10875) -> some View {
        VStack(spacing: 16) {
            Group {
                if case .card(let card)? = model.readings[subject] {
                    MessageCardView12308(card: card)
                } else {
                    MessageCardPlaceholder12308(subject: subject, reading: model.readings[subject])
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: 16))
            .overlay(RoundedRectangle(cornerRadius: 16).stroke(Color(uiColor: .separator)))
            if let app = subject.url {
                Button {
                    open(app)
                } label: {
                    Label("Open in Bain Luck", systemImage: "arrow.up.forward.app")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
            }
            Spacer(minLength: 0)
        }
        .padding()
    }

    @ViewBuilder
    private var picker: some View {
        switch model.saved {
        case .loading:
            ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
        case .openApp:
            message("Open Bain Luck once, and the games and markets you save show up here to send.",
                    action: "Open Bain Luck", url: URL(string: "bainluck://my-stuff"))
        case .empty:
            message("Save a game or market in Bain Luck, then send it from here.",
                    action: "Open Bain Luck", url: URL(string: "bainluck://my-stuff"))
        case .items(let subjects):
            List {
                Section {
                    ForEach(subjects, id: \.token) { subject in
                        pickerRow(subject)
                    }
                } header: {
                    Text("Send a saved game or market")
                } footer: {
                    Text("Friends see the card as you sent it. With Bain Luck, tapping it shows the latest.")
                }
            }
            .listStyle(.insetGrouped)
        }
    }

    @ViewBuilder
    private func pickerRow(_ subject: SavedWidgetSubject10875) -> some View {
        switch model.readings[subject] {
        case .card(let card)?:
            Button {
                send(card)
            } label: {
                HStack(spacing: 12) {
                    VStack(alignment: .leading, spacing: 3) {
                        Text(card.title).font(.subheadline.weight(.semibold)).foregroundStyle(Color.primary)
                        Text(card.line).font(.subheadline.monospacedDigit()).foregroundStyle(Color.primary)
                        Text(card.status).font(.caption).foregroundStyle(Color.secondary)
                    }
                    Spacer(minLength: 0)
                    Image(systemName: "arrow.up.circle.fill")
                        .font(.title2)
                        .foregroundStyle(Color.accentColor)
                        .accessibilityHidden(true)
                }
            }
            .accessibilityLabel("Send \(card.spoken)")
        case .gone?:
            Text("\(subject.fallbackTitle) · no longer on Bain Luck").foregroundStyle(Color.secondary)
        case .unreachable?:
            Text("\(subject.fallbackTitle) · can't reach Bain Luck").foregroundStyle(Color.secondary)
        default:
            HStack { Text(subject.fallbackTitle).foregroundStyle(Color.secondary); Spacer(); ProgressView() }
        }
    }

    private func message(_ text: String, action: String, url: URL?) -> some View {
        VStack(spacing: 12) {
            Text(text)
                .font(.subheadline)
                .multilineTextAlignment(.center)
                .foregroundStyle(Color.secondary)
            if let url {
                Button(action) { open(url) }
                    .buttonStyle(.bordered)
            }
        }
        .padding()
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
