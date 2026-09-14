"use client";

import { Suspense } from "react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { EMBED_PARAM, isEmbeddedAbout } from "@/lib/embed";

// #5914 — a `next/link` inside the About embed, rendered as a REAL navigation.
//
// THE PROBLEM NATIVE FOUND WHILE BUILDING ITS HALF, which neither half would
// have caught alone: `next/link` navigates with `pushState`, and WKWebView never
// shows its navigation delegate a same-document navigation. So native's link
// policy — "the embed About URL renders in place, every other navigation is
// handed to the system" — simply cannot fire, and a tap on "the calibration
// page" lands the reader on /calibration INSIDE the About screen. Worse for the
// web half: the client-side route drops the query string, so `embed=1` is gone
// and the chrome this ship just removed comes straight back, one tap from the
// screen we cleaned.
//
// Native offered three ways out and recommended (c); codex's 10:11 directive
// picked it in the same words ("plain anchors in embed mode so native policy can
// open outgoing links externally"). Rejected alternatives, recorded so nobody
// re-opens them:
//
//   (a) persist the flag in sessionStorage/context, so the whole site is
//       chromeless inside the app webview. Cheap, and it leaves a chromeless
//       Discover sitting under a native title bar that says "About" — a
//       different wrong screen, and a harder one to notice.
//   (b) do nothing and file the tap as a follow-on. Defensible: the three
//       photographed defects are still fixed. But it leaves the ship's own
//       claim — "one coherent page" — false at the first tap.
//
// So in embed mode these render as a plain `<a href>`. It becomes a real
// document navigation, native's policy sees it, and the link opens in Safari:
// About stays About.
//
// THE FALLBACK IS THE `<Link>`, AND HERE THAT IS FREE. `useSearchParams()`
// suspends on a statically prerendered route, so the shell ships whatever the
// fallback is — the `<Link>`, correct for every reader outside the app. In the
// embed the anchor is swapped in at hydration, and a tap cannot happen before
// hydration, so the only state a finger ever meets is the resolved one. This is
// the opposite of `TelemetryGate`'s case in `EmbedGate`, where the pre-hydration
// render has a side effect and the fallback therefore has to be nothing.

function EmbedAwareLinkInner({
  href,
  className,
  children,
}: {
  href: string;
  className?: string;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const embedValue = useSearchParams().get(EMBED_PARAM);

  if (isEmbeddedAbout(pathname, embedValue)) {
    return (
      <a href={href} className={className} data-embed-external="1">
        {children}
      </a>
    );
  }
  return (
    <Link href={href} className={className}>
      {children}
    </Link>
  );
}

export default function EmbedAwareLink(props: {
  href: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <Suspense
      fallback={
        <Link href={props.href} className={props.className}>
          {props.children}
        </Link>
      }
    >
      <EmbedAwareLinkInner {...props} />
    </Suspense>
  );
}
