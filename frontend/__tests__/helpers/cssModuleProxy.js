/**
 * Stand-in for a CSS Module under jest.
 *
 * Next compiles `*.module.css` into an object of hashed class names; ts-jest
 * does not, so `import s from "./x.module.css"` is handed to node as raw CSS
 * and the suite dies on `Unexpected token '.'` before a single test runs. That
 * is the only reason components which style themselves with a CSS Module —
 * every section of `/politics` among them — could not be render-tested at all.
 *
 * Returns the property name for any key, so `s.crossCard` is `"crossCard"`:
 * markup stays readable and a `className` assertion is possible if one is ever
 * wanted. `identity-obj-proxy` is the usual package for this; the npm registry
 * is not reachable from this environment and it is a Proxy either way.
 *
 * Wired in `jest.config.js`, ahead of the `^@/` alias — the alias would match
 * `@/app/politics/politics.module.css` first and hand back the CSS again.
 */
module.exports = new Proxy(
  {},
  {
    get: (_target, key) => (key === "__esModule" ? false : key),
  },
);
