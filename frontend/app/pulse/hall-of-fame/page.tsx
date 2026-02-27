"use client";

import { redirect } from "next/navigation";

/**
 * Redirect /pulse/hall-of-fame → /ei/hall-of-fame
 */
export default function PulseHallOfFameRedirect() {
  redirect("/ei/hall-of-fame");
}
