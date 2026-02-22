/**
 * UserMenu - Sign-in button or user avatar with dropdown.
 */

"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { useAuthContext } from "@/components/AuthProvider";

export default function UserMenu() {
  const { user, isAuthenticated, isAuthAvailable, signInWithGoogle, signOut } =
    useAuthContext();
  const [isOpen, setIsOpen] = useState(false);
  const [imgError, setImgError] = useState(false);
  const [signingIn, setSigningIn] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  if (!isAuthAvailable) return null;

  if (!isAuthenticated) {
    return (
      <button
        onClick={async () => {
          if (signingIn) return;
          setSigningIn(true);
          try {
            await signInWithGoogle();
          } finally {
            setSigningIn(false);
          }
        }}
        disabled={signingIn}
        className="text-sm text-text-secondary hover:text-text-primary transition-colors"
      >
        {signingIn ? "Signing in..." : "Sign in"}
      </button>
    );
  }

  const initial = user?.displayName?.charAt(0)?.toUpperCase() || user?.email?.charAt(0)?.toUpperCase() || "?";

  return (
    <div className="relative" ref={menuRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2"
        aria-label="User menu"
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
        <div className="absolute right-0 mt-2 w-48 bg-surface-card rounded-lg shadow-lg border border-surface-border py-1 z-50">
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
