/**
 * UserMenu - Sign-in button or user avatar with dropdown.
 *
 * Unauthenticated: "Sign in" button that opens a provider chooser
 * (Google / Apple) inline dropdown.
 * Authenticated: User avatar that opens preferences/sign-out dropdown.
 */

"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { useAuthContext } from "@/components/AuthProvider";
import { preloadFirebaseAuth } from "@/lib/firebase";

export default function UserMenu() {
  const {
    user,
    isAuthenticated,
    isAuthAvailable,
    signInWithGoogle,
    signInWithApple,
    signOut,
  } = useAuthContext();
  const [isOpen, setIsOpen] = useState(false);
  const [showProviders, setShowProviders] = useState(false);
  const [imgError, setImgError] = useState(false);
  const [signingIn, setSigningIn] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setIsOpen(false);
        setShowProviders(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  if (!isAuthAvailable) return null;

  if (!isAuthenticated) {
    return (
      <div className="relative" ref={menuRef}>
        <button
          onClick={() => {
            if (signingIn) return;
            setShowProviders(!showProviders);
            // Pre-load Firebase Auth module so Apple popup opens instantly
            preloadFirebaseAuth();
          }}
          disabled={signingIn}
          aria-expanded={showProviders}
          aria-haspopup="true"
          aria-label={signingIn ? "Signing in" : "Sign in"}
          className="text-sm text-text-secondary hover:text-text-primary transition-colors"
        >
          {signingIn ? "Signing in..." : "Sign in"}
        </button>

        {showProviders && !signingIn && (
          <div className="absolute right-0 mt-2 w-56 bg-surface-card rounded-lg shadow-lg border border-surface-border py-1 z-50" role="menu" aria-label="Sign in options">
            <button
              onClick={async () => {
                setShowProviders(false);
                setSigningIn(true);
                try {
                  await signInWithGoogle();
                } finally {
                  setSigningIn(false);
                }
              }}
              role="menuitem"
              className="w-full text-left px-4 py-2.5 text-sm text-text-primary hover:bg-surface-elevated transition-colors flex items-center gap-3"
            >
              <svg viewBox="0 0 24 24" className="w-5 h-5 flex-shrink-0" aria-hidden="true">
                <path
                  d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"
                  fill="#4285F4"
                />
                <path
                  d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                  fill="#34A853"
                />
                <path
                  d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                  fill="#FBBC05"
                />
                <path
                  d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                  fill="#EA4335"
                />
              </svg>
              Continue with Google
            </button>

            <button
              onClick={async () => {
                setShowProviders(false);
                setSigningIn(true);
                try {
                  await signInWithApple();
                } finally {
                  setSigningIn(false);
                }
              }}
              role="menuitem"
              className="w-full text-left px-4 py-2.5 text-sm text-text-primary hover:bg-surface-elevated transition-colors flex items-center gap-3"
            >
              <svg viewBox="0 0 24 24" className="w-5 h-5 flex-shrink-0 fill-current" aria-hidden="true">
                <path d="M17.05 20.28c-.98.95-2.05.88-3.08.4-1.09-.5-2.08-.48-3.24 0-1.44.62-2.2.44-3.06-.4C2.79 15.25 3.51 7.59 9.05 7.31c1.35.07 2.29.74 3.08.8 1.18-.24 2.31-.93 3.57-.84 1.51.12 2.65.72 3.4 1.8-3.12 1.87-2.38 5.98.48 7.13-.57 1.5-1.31 2.99-2.54 4.09zM12.03 7.25c-.15-2.23 1.66-4.07 3.74-4.25.29 2.58-2.34 4.5-3.74 4.25z" />
              </svg>
              Continue with Apple
            </button>

            <div className="border-t border-surface-border mt-1 pt-1">
              <Link
                href="/about"
                onClick={() => setShowProviders(false)}
                className="block px-4 py-2 text-sm text-text-muted hover:bg-surface-elevated transition-colors"
              >
                About Bain Luck
              </Link>
            </div>
          </div>
        )}
      </div>
    );
  }

  const initial =
    user?.displayName?.charAt(0)?.toUpperCase() ||
    user?.email?.charAt(0)?.toUpperCase() ||
    "?";

  return (
    <div className="relative" ref={menuRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2"
        aria-label="User menu"
        aria-expanded={isOpen}
        aria-haspopup="true"
      >
        {user?.photoURL && !imgError ? (
          <img
            src={user.photoURL}
            alt=""
            className="w-8 h-8 rounded-full border border-surface-border"
            referrerPolicy="no-referrer"
            onError={() => setImgError(true)}
          />
        ) : (
          <div className="w-8 h-8 rounded-full bg-accent-brand text-text-inverse flex items-center justify-center text-sm font-medium">
            {initial}
          </div>
        )}
      </button>

      {isOpen && (
        <div className="absolute right-0 mt-2 w-48 bg-surface-card rounded-lg shadow-lg border border-surface-border py-1 z-50" role="menu" aria-label="User options">
          <div className="px-4 py-2 border-b border-surface-border">
            <p className="text-sm font-medium text-text-primary truncate">
              {user?.displayName || "User"}
            </p>
            <p className="text-xs text-text-muted truncate">{user?.email}</p>
          </div>

          <Link
            href="/preferences"
            onClick={() => setIsOpen(false)}
            className="block px-4 py-2 text-sm text-text-secondary hover:bg-surface-elevated transition-colors"
          >
            Preferences
          </Link>

          <Link
            href="/about"
            onClick={() => setIsOpen(false)}
            className="block px-4 py-2 text-sm text-text-secondary hover:bg-surface-elevated transition-colors"
          >
            About
          </Link>

          <button
            onClick={async () => {
              setIsOpen(false);
              await signOut();
            }}
            className="w-full text-left px-4 py-2 text-sm text-text-muted hover:bg-surface-elevated transition-colors"
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
