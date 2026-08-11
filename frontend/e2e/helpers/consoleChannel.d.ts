/**
 * UX-P058 (#1610/#1612/#1614) — the ONE home for "is this console message a
 * statement about a REQUEST?", so the console and network channels cannot
 * disagree about who grades sub-resource failures.
 */

/** Chromium's generic sub-resource failure message, status and transport forms. */
export declare const RESOURCE_LOAD_CONSOLE_RE: RegExp;

/** True when `text` is the browser's own resource-load complaint. */
export declare function isResourceLoadConsoleError(text: unknown): boolean;

/**
 * Split captured console-error text into the channel that grades it:
 * `scriptErrors` still fail `console.no_errors`; `resourceErrors` are evidence,
 * graded by `network.no_unexpected_failures` where a URL exists to scope on.
 */
export declare function partitionConsoleErrors(texts: readonly unknown[]): {
  scriptErrors: string[];
  resourceErrors: string[];
};
