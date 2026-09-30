/// Discover feedback belongs to a resolved account, never a guest gesture (#9644).
/// Capture the state when a gesture begins and check it again at each delayed
/// effect. Signing in cannot retroactively authorize a rejected swipe.
nonisolated struct DiscoverGuestFeedbackGate: Equatable, Sendable {
    enum AuthState: Equatable, Sendable {
        case resolving
        case signedOut
        case signedIn(userId: String)
    }

    private(set) var hasPresentedInvitation = false

    static func authState(userId: String?, isLoading: Bool) -> AuthState {
        if isLoading { return .resolving }
        guard let userId else { return .signedOut }
        return .signedIn(userId: userId)
    }

    static func allowsFeedback(startedWith: AuthState, current: AuthState) -> Bool {
        guard case .signedIn = startedWith else { return false }
        return startedWith == current
    }

    /// One invitation per Discover sitting. Dismissal leaves guest browsing
    /// available and does not retain a pending action to replay after sign-in.
    mutating func requestInvitation(current: AuthState) -> Bool {
        guard case .signedOut = current,
              !hasPresentedInvitation else { return false }
        hasPresentedInvitation = true
        return true
    }
}
