/**
 * The truth-rule scanner for a rendered /evals tree (#12102). Not a test file:
 * the page tests import it, and its own negative controls live in
 * `components/evals/__tests__/evalsPage.test.tsx`.
 *
 * It reads the DOM, not the source, because a number can reach a reader from a
 * template, a join or a data file, and only the render shows all of them.
 */

/** Labels and identifiers, not figures: dates, ages, issue numbers. */
const EXEMPT = "[data-evals-figure], [data-truth-chip], [data-evals-ref], time, script, style";

export interface EvalsScan {
  /** Digits a reader sees outside a Figure, a truth chip, a date or an issue link. */
  bareNumbers: string[];
  /** Figures rendered inside a PLANNED item. */
  figuresInPlanned: string[];
  /** Figures whose nearest truth scope is missing or says a different kind. */
  figuresOutsideScope: string[];
}

export function scanEvalsDom(root: Element): EvalsScan {
  const figures = Array.from(root.querySelectorAll("[data-evals-figure]"));

  const figuresInPlanned = figures
    .filter((fig) => fig.closest("[data-planned-item]"))
    .map((fig) => fig.textContent ?? "");

  const figuresOutsideScope = figures
    .filter((fig) => {
      const scope = fig.closest("[data-truth-scope]");
      return !scope || scope.getAttribute("data-truth-scope") !== fig.getAttribute("data-truth");
    })
    .map((fig) => fig.textContent ?? "");

  const clone = root.cloneNode(true) as Element;
  clone.querySelectorAll(EXEMPT).forEach((node) => node.remove());
  const text = (clone.textContent ?? "").replace(/\s+/g, " ");
  const bareNumbers = Array.from(text.matchAll(/\d+/g)).map((m) => {
    const at = m.index ?? 0;
    return text.slice(Math.max(0, at - 40), at + 40).trim();
  });

  return { bareNumbers, figuresInPlanned, figuresOutsideScope };
}
