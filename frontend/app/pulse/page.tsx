"use client";

import { redirect } from "next/navigation";

/**
 * Redirect /pulse → /ei
 */
export default function PulseRedirectPage() {
  redirect("/ei");
}
