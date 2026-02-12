"use client";

import { useAuthContext } from "@/components/AuthProvider";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

export default function PreferencesPage() {
  const { user, isAuthenticated, isLoading, signOut } = useAuthContext();
  const router = useRouter();

  // Redirect to home if not authenticated
  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push("/");
    }
  }, [isLoading, isAuthenticated, router]);

  if (isLoading || !isAuthenticated) {
    return null;
  }

  return (
    <div className="max-w-lg mx-auto px-4 py-8">
      <h1 className="text-2xl font-bold text-graphite mb-6">Preferences</h1>

      {/* Profile section */}
      <div className="bg-white rounded-xl border border-mist p-6 mb-6">
        <h2 className="text-sm font-semibold text-slate uppercase tracking-wide mb-4">
          Account
        </h2>
        <div className="flex items-center gap-4">
          {user?.photoURL ? (
            <img
              src={user.photoURL}
              alt=""
              className="w-12 h-12 rounded-full border border-mist"
              referrerPolicy="no-referrer"
            />
          ) : (
            <div className="w-12 h-12 rounded-full bg-graphite text-white flex items-center justify-center text-lg font-medium">
              {user?.displayName?.charAt(0)?.toUpperCase() || "?"}
            </div>
          )}
          <div>
            <p className="font-medium text-graphite">
              {user?.displayName || "User"}
            </p>
            <p className="text-sm text-slate">{user?.email}</p>
          </div>
        </div>
      </div>

      {/* Coming soon */}
      <div className="bg-white rounded-xl border border-mist p-6 mb-6">
        <h2 className="text-sm font-semibold text-slate uppercase tracking-wide mb-3">
          Personalization
        </h2>
        <p className="text-sm text-slate">
          Team preferences, sport affinities, and personalized highlights are coming soon.
        </p>
      </div>

      {/* Sign out */}
      <button
        onClick={async () => {
          await signOut();
          router.push("/");
        }}
        className="w-full py-3 text-sm text-slate hover:text-graphite border border-mist rounded-xl hover:bg-snow transition-colors"
      >
        Sign out
      </button>
    </div>
  );
}
