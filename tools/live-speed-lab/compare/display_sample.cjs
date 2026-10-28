// Passive sample of PR #11673's adopted-state attributes. No inferred identity.
function readDisplayIdentity10090() {
  const started = performance.now();
  function surface(selector, fields) {
    const nodes = document.querySelectorAll(selector);
    if (nodes.length !== 1) return {
      status: nodes.length ? 'ambiguous' : 'missing', count: nodes.length,
      attributes: null, visible: false, inViewport: false,
    };
    const node = nodes[0];
    const attributes = Object.fromEntries(fields.map(key => [key, node.getAttribute(key)]));
    let visible = node.isConnected && node.getClientRects().length > 0;
    for (let parent = node; visible && parent; parent = parent.parentElement) {
      const css = getComputedStyle(parent);
      if (parent.hidden || parent.getAttribute('aria-hidden') === 'true' ||
          css.display === 'none' || css.visibility !== 'visible' || Number(css.opacity) === 0) visible = false;
    }
    const rect = node.getBoundingClientRect();
    return {
      status: fields.every(key => attributes[key] !== null) ? 'present' : 'unsupported',
      count: 1, attributes, visible,
      inViewport: visible && rect.width > 0 && rect.height > 0 && rect.bottom > 0 &&
        rect.right > 0 && rect.top < innerHeight && rect.left < innerWidth,
    };
  }
  const headline = surface('[data-testid="event-hero-probability"]', [
    'data-display-basis', 'data-display-state', 'data-display-received', 'data-display-observed-at',
  ]);
  const chart = surface('[data-testid="win-probability-card"] [data-chart-endpoint-state]', [
    'data-chart-endpoint-at', 'data-chart-endpoint-basis', 'data-chart-endpoint-state', 'data-chart-history',
  ]);
  return {
    schema: 'display-identity-sample/1', started_mono: started, ended_mono: performance.now(),
    documentVisibility: document.visibilityState, headline, chart,
  };
}

module.exports = {readDisplayIdentity10090};
