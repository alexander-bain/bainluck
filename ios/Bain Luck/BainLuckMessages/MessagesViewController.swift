import Messages
import SwiftUI
import UIKit

/// #12308 — Bain Luck in Messages.
///
/// From the app drawer the reader picks one of their saved games or markets
/// and it goes into the message field as a card ("Bills 62% · Vikings 38%").
/// The card is a picture of the reading as sent, with its price dated, and
/// everyone in the thread sees the same picture. Tapping it opens the item's
/// current reading here, with a way into the app. The message's link opens the
/// game or market on bainluck.com for anyone without Bain Luck.
///
/// Nothing is sent for the reader: the card waits in the message field until
/// they press Send. The message carries only the public link.
final class MessagesViewController: MSMessagesAppViewController {
    private let model = MessagesModel12308()

    override func viewDidLoad() {
        super.viewDidLoad()
        let root = MessagesRootView12308(
            model: model,
            send: { [weak self] card in self?.stage(card) },
            open: { [weak self] url in self?.extensionContext?.open(url) })
        let host = UIHostingController(rootView: root)
        host.view.backgroundColor = .clear
        addChild(host)
        host.view.frame = view.bounds
        host.view.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        view.addSubview(host.view)
        host.didMove(toParent: self)
    }

    override func willBecomeActive(with conversation: MSConversation) {
        super.willBecomeActive(with: conversation)
        show(for: conversation, style: presentationStyle)
    }

    override func didTransition(to presentationStyle: MSMessagesAppPresentationStyle) {
        super.didTransition(to: presentationStyle)
        if let conversation = activeConversation { show(for: conversation, style: presentationStyle) }
    }

    override func didSelect(_ message: MSMessage, conversation: MSConversation) {
        super.didSelect(message, conversation: conversation)
        show(for: conversation, style: presentationStyle)
    }

    private func show(for conversation: MSConversation, style: MSMessagesAppPresentationStyle) {
        let screen = MessageScreen12308.screen(expanded: style == .expanded, selected: conversation.selectedMessage?.url)
        Task { await model.show(screen) }
    }

    /// Puts the card in the message field. Sending is the reader's.
    private func stage(_ card: MessageCard12308) {
        guard let conversation = activeConversation else { return }
        let message = MSMessage(session: MSSession())
        message.url = card.url
        message.summaryText = card.summary
        message.accessibilityLabel = card.sentSpoken
        let layout = MSMessageTemplateLayout()
        layout.image = MessageCardImage12308.image(card)
        // The dated standing, as text under the picture.
        layout.caption = card.sentStatus
        message.layout = layout
        conversation.insert(message) { _ in }
        requestPresentationStyle(.compact)
    }
}

/// The card as sent, as a picture.
enum MessageCardImage12308 {
    static func image(_ card: MessageCard12308) -> UIImage? {
        let renderer = ImageRenderer(content:
            MessageCardView12308(card: card, sent: true).frame(width: MessageCardView12308.width))
        renderer.scale = 3
        return renderer.uiImage
    }
}
