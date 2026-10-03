"use client";

import OriginBackControl from "@/components/OriginBackControl";
import { questionOrigin } from "@/lib/futuresReturnOrigin";

/**
 * #10265 — the question page's back control: "Back" to the page the reader
 * tapped from when that entry is provably the one behind it, otherwise the old
 * Discover link. The control itself: `components/OriginBackControl.tsx`.
 */
export default function FuturesBackControl() {
  return <OriginBackControl store={questionOrigin} fallbackHref="/discover" fallbackLabel="Back to Discover" />;
}
