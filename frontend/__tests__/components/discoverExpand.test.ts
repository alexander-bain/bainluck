import { feedContextSnippet, feedExpandedContext, sentencePreview } from "../../components/discover/utils";

const makeFuturesItem = (overrides: Record<string, unknown> = {}) => ({
  type: "futures" as const,
  headline: "",
  reason: "",
  context_summary: "",
  data: { hook_description: "", ...overrides.data as Record<string, unknown> || {} },
  ...overrides,
});

describe("feedExpandedContext", () => {
  test("truncated text expands to full text", () => {
    const longSnippet =
      "This is a very long context summary that goes on and on and describes the market in great detail including probabilities and historical context about the event. It exceeds the preview character limit easily.";
    const item = makeFuturesItem({ context_summary: longSnippet });
    const compact = feedContextSnippet(item as any);
    const expanded = feedExpandedContext(item as any);
    const preview = sentencePreview(compact);

    // Preview should be shorter than the full text
    expect(preview.length).toBeLessThan(longSnippet.length);
    // Expanded should contain the full snippet
    expect(expanded).toContain(compact);
  });

  test("distinct expandedText appends to snippet", () => {
    const item = makeFuturesItem({
      context_summary: "The Fed is expected to cut rates.",
      data: { hook_description: "Markets price in a 75% chance of a December cut." },
    });
    const snippet = feedContextSnippet(item as any);
    const expanded = feedExpandedContext(item as any);

    // Expanded should start with the snippet
    expect(expanded.startsWith(snippet)).toBe(true);
    // Expanded should contain the extra context
    expect(expanded).toContain("75%");
  });

  test("near-duplicate expandedText produces no extra content", () => {
    const text = "Markets expect a rate cut in December.";
    const item = makeFuturesItem({
      context_summary: text,
      data: { hook_description: text }, // same content
    });
    const snippet = feedContextSnippet(item as any);
    const expanded = feedExpandedContext(item as any);

    // Should be identical — no " — " separator
    expect(expanded).toBe(snippet);
  });

  test("contained expandedText produces no extra content", () => {
    const snippet = "The Atlanta Hawks are favored to win tonight's game against the Celtics.";
    const hookDesc = "The Hawks are favored to win tonight's game."; // subset of snippet
    const item = makeFuturesItem({
      context_summary: snippet,
      data: { hook_description: hookDesc },
    });
    const expanded = feedExpandedContext(item as any);

    // hookDesc is contained in snippet — no expansion
    expect(expanded).toBe(snippet);
  });
});
