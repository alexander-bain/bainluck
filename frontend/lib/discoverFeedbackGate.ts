/**
 * #9643 — WHO MAY TEACH DISCOVER.
 *
 * A swipe (or its button twin: thumbs up / "less like this") is preference
 * feedback. It writes the local profile (`recordDiscoverInteraction`), queues a
 * server interaction (`sendDiscoverInteraction`) and, for a dismiss, the local
 * dismiss set. v3 rule: only a signed-in reader teaches the feed. A signed-out
 * reader who swipes is invited to sign in instead, and nothing is written.
 *
 * Three states, not two, because auth restore is asynchronous:
 *
 *   learn  — resolved, signed in, with a stable uid. Feedback proceeds.
 *   invite — resolved and signed out. Feedback is refused; the page offers
 *            sign-in.
 *   hold   — auth still resolving, or a user object without a uid yet. Feedback
 *            is refused SILENTLY: this may be a signed-in reader mid-restore, and
 *            telling them to sign in would be wrong.
 *
 * A refused attempt is dropped, never queued. Signing in afterwards does not
 * replay it — the first thing a new account learns from is its own first swipe.
 */

export type DiscoverLearningState = "learn" | "invite" | "hold";

export interface DiscoverLearningAuth {
  isLoading: boolean;
  isAuthenticated: boolean;
  uid: string | null | undefined;
}

export function resolveDiscoverLearning(auth: DiscoverLearningAuth): DiscoverLearningState {
  if (auth.isLoading) return "hold";
  if (!auth.isAuthenticated) return "invite";
  return auth.uid ? "learn" : "hold";
}

export interface DiscoverFeedbackDecision {
  /** The card may record the feedback and run its dismiss. */
  proceed: boolean;
  /** The page should open the sign-in invitation. */
  invite: boolean;
}

export function decideDiscoverFeedbackAttempt(state: DiscoverLearningState): DiscoverFeedbackDecision {
  if (state === "learn") return { proceed: true, invite: false };
  if (state === "invite") return { proceed: false, invite: true };
  return { proceed: false, invite: false };
}

/**
 * Run one provider sign-in from the invitation. A cancelled popup or a provider
 * error must leave the feed usable, so the rejection is absorbed here (the auth
 * hook already surfaces `authError`) and `onSettled` always runs — the page uses
 * it to close the invitation either way.
 */
export async function runDiscoverInviteSignIn(
  signIn: () => Promise<void>,
  onSettled: () => void,
): Promise<void> {
  try {
    await signIn();
  } catch {
    // Cancelled or failed: browsing continues signed out.
  } finally {
    onSettled();
  }
}
