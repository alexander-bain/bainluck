import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { selfCanonical } from "@/lib/routeMetadata";

/**
 * #4193. `/golf` is a permanent alias for `/categories/golf`, and it is
 * prerendered — so it emits metadata even though a reader never lingers here.
 * It was emitting the root's `canonical: "/"`, which is the one claim that is
 * wrong twice over: this page is neither the home page nor its own destination.
 *
 * The canonical points at the DESTINATION, not at `/golf`. That is what a
 * redirect means: the content lives there, and the duplicate should consolidate
 * onto it rather than compete with it.
 */
export const metadata: Metadata = selfCanonical("/categories/golf");

export default function GolfRedirect() {
  redirect("/categories/golf");
}
