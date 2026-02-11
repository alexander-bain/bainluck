/**
 * UserMenu - Sign-in button or user avatar with dropdown.
 *
 * When not authenticated: shows "Sign in" text button.
 * When authenticated: shows user avatar/initial with dropdown menu.
 * When auth is not configured: renders nothing.
 */

"use client";

import { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { useAuthContext } from "@/components/AuthProvider";

export default function UserMenu() {
  const { user, isLoading, isAuthenticated, isAuthAvailable, signInWithGoogle, signOut } =
    useAuthContext();
  const [isOpen, setIsOpen] = useState(false);
  const [isSigningIn, setIsSigningIn] = useState(false);
  const [imgError, setImgError] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Don't render anything if auth is not configured
  if (!isAuthAvailable) return null;

  // Not authenticated (or still loading) — show sign-in button
  if (!isAuthenticated) {
    return (
      <button
        onClick={() => signInWithGoogle()}
        className="text-sm font-medium text-slate hover:text-graphite transition-colors"
      >
        Sign in
      </button>
    );
  }

  // Authenticated — show avatar with dropdown
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
            className="w-8 h-8 rounded-full border border-mist"
            referrerPolicy="no-referrer"
            onError={() => setImgError(true)}
          />
        ) : (
          <div className="w-8 h-8 rounded-full bg-graphite text-white flex items-center justify-center text-sm font-medium">
            {initial}
          </div>
        )}
      </button>

      {isOpen && (
        <div className="absolute right-0 mt-2 w-48 bg-white rounded-lg shadow-lg border border-mist py-1 z-50">
          {/* User info */}
          <div className="px-4 py-2 border-b border-mist">
            <p className="text-sm font-medium text-graphite truncate">
              {user?.displayName || "User"}
            </p>
            <p className="text-xs text-slate truncate">{user?.email}</p>
          </div>

          {/* Menu items */}
          <Link
            href="/preferences"
            onClick={() => setIsOpen(false)}
            className="block px-4 py-2 text-sm text-graphite hover:bg-snow transition-colors"
          >
            Preferences
          </Link>

          <button
            onClick={async () => {
              setIsOpen(false);
              await signOut();
            }}
            className="w-full text-left px-4 py-2 text-sm text-slate hover:bg-snow transition-colors"
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
