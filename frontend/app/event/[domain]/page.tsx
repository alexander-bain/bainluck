// L2-113: legacy event-concept URL redirector. The old shape
// `/event/event%3A<domain>%3A<slug>` (a SINGLE path segment with the colons
// percent-encoded — the "looks TERRIBLE" URL Alex flagged) is captured here as
// `params.domain` (the whole old key) and permanently redirected to the colon-free
// `/event/<domain>/<slug>`. Pure string transform of the key, so this is a real
// server-side 308 (permanent) redirect — old links, shares, and any indexed URL
// keep working while search engines learn the clean canonical form. The live page
// lives at `app/event/[domain]/[slug]/page.tsx` (two segments).

import { permanentRedirect } from "next/navigation";
import { parseEventKey } from "@/lib/eventKey";

export default function LegacyEventKeyRedirect({
  params,
}: {
  params: { domain: string };
}) {
  // `params.domain` is the legacy single-segment key, e.g. "event:ufc:26jul11".
  const { domain, slug } = parseEventKey(params?.domain || "");
  permanentRedirect(`/event/${encodeURIComponent(domain)}/${encodeURIComponent(slug)}`);
}
