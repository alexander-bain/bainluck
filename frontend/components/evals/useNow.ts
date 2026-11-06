"use client";

import { useEffect, useState } from "react";

/**
 * The reader's clock, or null until the page has mounted.
 *
 * /evals is prerendered at build time, so a "3 days ago" computed during that
 * render would be frozen at the build's date and served for weeks. The server
 * render and the first client render both see null and print only the date;
 * the age appears once the browser has a real clock, so hydration never
 * disagrees with the server.
 */
export function useNow(): Date | null {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    setNow(new Date());
  }, []);
  return now;
}
