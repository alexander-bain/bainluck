"use client";

import { useEffect } from "react";
import { Button } from "@/components/ui/button";
import { preloadFirebaseAuth } from "@/lib/firebase";
import { runDiscoverInviteSignIn } from "@/lib/discoverFeedbackGate";

/**
 * #9643 — what a signed-out reader sees when they swipe a Discover card.
 *
 * The swipe itself has already been refused (`lib/discoverFeedbackGate.ts`);
 * this only explains why and offers the existing providers. "Not now", Escape
 * and the backdrop all close it, and every path back leaves the feed exactly as
 * it was — no guest profile, no queued swipe waiting for an account.
 *
 * Presentational: the page owns open/close and hands in the auth context's own
 * sign-in functions, the same ones `UserMenu` and My Stuff call.
 */
export interface SignInToPersonalizeInviteProps {
  open: boolean;
  onClose: () => void;
  onSignInGoogle: () => Promise<void>;
  onSignInApple: () => Promise<void>;
}

export default function SignInToPersonalizeInvite({
  open,
  onClose,
  onSignInGoogle,
  onSignInApple,
}: SignInToPersonalizeInviteProps) {
  useEffect(() => {
    if (!open) return;
    // Same reason as My Stuff's prompt: the Apple popup must open on the click.
    preloadFirebaseAuth();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 bg-black/55 backdrop-blur-sm flex items-end sm:items-center justify-center p-4"
      onClick={onClose}
      data-testid="discover-sign-in-invite"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="discover-sign-in-invite-title"
        className="w-full max-w-sm rounded-2xl bg-surface-card shadow-2xl border border-surface-border p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="discover-sign-in-invite-title" className="text-base font-semibold text-text-primary">
          Sign in to personalize Discover
        </h2>
        <p className="mt-1.5 text-sm text-text-secondary">
          Swipes tell Discover what you want more or less of. Sign in and they&apos;ll shape your feed.
        </p>
        <div className="mt-5 flex flex-col gap-2.5">
          <Button onClick={() => runDiscoverInviteSignIn(onSignInGoogle, onClose)} className="w-full">
            Continue with Google
          </Button>
          <Button onClick={() => runDiscoverInviteSignIn(onSignInApple, onClose)} className="w-full">
            Continue with Apple
          </Button>
          <Button variant="ghost" onClick={onClose} className="w-full">
            Not now
          </Button>
        </div>
      </div>
    </div>
  );
}
