"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/**
 * Redirect /preferences to /my-stuff for backward compatibility.
 */
export default function PreferencesRedirect() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/my-stuff");
  }, [router]);

  return null;
}
