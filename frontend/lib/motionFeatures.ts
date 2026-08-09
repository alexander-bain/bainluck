/**
 * The framer-motion feature set, isolated in its own module so it can be code-split.
 *
 * This file exists to be `import()`-ed, never imported statically. Keeping it separate is
 * the whole mechanism: `MotionProvider` loads it lazily, so the animation features land in
 * their own async chunk instead of the route's First Load JS.
 *
 * `domAnimation` (~15 kB) covers animations, variants, exit animations, and tap/hover/focus
 * gestures. That is everything this codebase uses. The heavier `domMax` set is only needed
 * for layout animations (`layout`, `layoutId`) and drag/pan, and we use none of them — see
 * the guard in `__tests__/lib/motionBundle.test.ts`, which fails if that stops being true.
 */
export { domAnimation as default } from "framer-motion";
