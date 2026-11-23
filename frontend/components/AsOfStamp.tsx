"use client";

import { useSyncExternalStore, type ReactNode } from "react";
import { formatAsOfStamp } from "@/lib/asOfStamp";

const emptySubscribe = () => () => {};

/**
 * Returns `false` during SSR (`renderToString`) and `true` in the browser once
 * hydrated, so client-clock formatting never bakes the server's UTC time into
 * SSR HTML (#13203).
 */
export function useIsClient(): boolean {
  return useSyncExternalStore(
    emptySubscribe,
    () => true,
    () => false,
  );
}

/**
 * Renders an "As of ..." timestamp strictly in the browser's local time zone.
 * Emits nothing on the server (`renderToString`), then populates cleanly after
 * hydration so the reader's clock always wins without hydration warnings.
 */
export function AsOfStamp({
  iso,
  prefix = "",
  className,
  now,
  timeZone,
  render,
}: {
  iso: string | null | undefined;
  prefix?: string;
  className?: string;
  now?: Date;
  timeZone?: string;
  render?: (label: string) => ReactNode;
}) {
  const isClient = useIsClient();
  if (!isClient) return null;
  const label = formatAsOfStamp(iso, now, timeZone);
  if (!label) return null;
  if (render) {
    return <>{render(label)}</>;
  }
  return (
    <span className={className} data-as-of-stamp>
      {prefix}
      {label}
    </span>
  );
}
