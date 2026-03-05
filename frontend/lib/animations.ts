/**
 * Framer Motion Animation Presets
 *
 * Shared animation variants and transitions for consistent motion
 * across the Bain Luck frontend. Import what you need:
 *
 *   import { fadeIn, slideUp, probabilityTransition } from "@/lib/animations";
 *   <motion.div variants={fadeIn} initial="hidden" animate="visible" />
 */

import type { Variants, Transition } from "framer-motion";

// ── TRANSITIONS ──

/** Fast transition for micro-interactions (hover, focus) */
export const transitionFast: Transition = {
  duration: 0.15,
  ease: "easeOut",
};

/** Standard transition for most UI changes */
export const transitionNormal: Transition = {
  duration: 0.3,
  ease: "easeOut",
};

/** Slow transition for dramatic reveals */
export const transitionSlow: Transition = {
  duration: 0.5,
  ease: "easeOut",
};

/** Spring transition for bouncy, natural-feeling motion */
export const transitionSpring: Transition = {
  type: "spring",
  stiffness: 300,
  damping: 24,
};

/** Smooth transition for probability number changes */
export const probabilityTransition: Transition = {
  duration: 0.4,
  ease: [0.25, 0.1, 0.25, 1], // ease-out cubic
};

// ── VARIANTS ──

/** Simple fade in/out */
export const fadeIn: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: transitionNormal },
  exit: { opacity: 0, transition: transitionFast },
};

/** Slide up from below with fade */
export const slideUp: Variants = {
  hidden: { opacity: 0, y: 12 },
  visible: { opacity: 1, y: 0, transition: transitionNormal },
  exit: { opacity: 0, y: -8, transition: transitionFast },
};

/** Slide in from the right (for list items, cards) */
export const slideRight: Variants = {
  hidden: { opacity: 0, x: -12 },
  visible: { opacity: 1, x: 0, transition: transitionNormal },
  exit: { opacity: 0, x: 12, transition: transitionFast },
};

/** Scale up from slightly smaller (for modals, tooltips) */
export const scaleIn: Variants = {
  hidden: { opacity: 0, scale: 0.95 },
  visible: { opacity: 1, scale: 1, transition: transitionSpring },
  exit: { opacity: 0, scale: 0.95, transition: transitionFast },
};

/** Stagger children animation — use on parent container */
export const staggerContainer: Variants = {
  hidden: {},
  visible: {
    transition: {
      staggerChildren: 0.05,
      delayChildren: 0.1,
    },
  },
};

/** Individual item in a staggered list */
export const staggerItem: Variants = {
  hidden: { opacity: 0, y: 8 },
  visible: { opacity: 1, y: 0, transition: transitionNormal },
};

// ── LIVE DATA ANIMATIONS ──

/** Pulse animation for live badges */
export const livePulse: Variants = {
  initial: { scale: 1, opacity: 1 },
  animate: {
    scale: [1, 1.05, 1],
    opacity: [1, 0.7, 1],
    transition: {
      duration: 2,
      repeat: Infinity,
      ease: "easeInOut",
    },
  },
};

/**
 * EI "breathing" animation — speed maps to excitement score.
 * Higher EI = faster pulse. Used in TV mode and live badges.
 *
 * @param eiScore - Excitement Index score (0-100)
 * @returns Transition config with duration mapped to EI
 */
export function eiBreathingTransition(eiScore: number): Transition {
  // beatMs = Math.max(550, 2000 - score * 14.5)
  // EI 0 → 2000ms, EI 50 → 1275ms, EI 91 → 681ms, EI 100 → 550ms
  const durationMs = Math.max(550, 2000 - eiScore * 14.5);
  return {
    duration: durationMs / 1000,
    repeat: Infinity,
    ease: "easeInOut",
  };
}

/** Breathing scale variant — pair with eiBreathingTransition() */
export const breathingScale: Variants = {
  initial: { scale: 1 },
  animate: { scale: [1, 1.03, 1] },
};

/**
 * Number counter transition for animating probability values.
 * Use with framer-motion's `useMotionValue` + `useTransform`.
 */
export const numberTransition: Transition = {
  duration: 0.6,
  ease: [0.16, 1, 0.3, 1], // expo-out
};
