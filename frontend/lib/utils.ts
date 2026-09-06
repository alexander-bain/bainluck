import { clsx, type ClassValue } from "clsx"
import { extendTailwindMerge } from "tailwind-merge"

// `text-prob-*` are custom fontSize entries (tailwind.config.ts `theme.extend.fontSize`).
// tailwind-merge cannot infer that, so it files them under `text-color` alongside
// `text-text-primary` and keeps only the last one written — silently dropping the size.
// Registering the scale puts them in `font-size`, so a size and a colour survive together.
const twMerge = extendTailwindMerge({
  extend: {
    classGroups: {
      "font-size": [{ text: ["prob-hero", "prob-lg", "prob-md", "prob-sm"] }],
    },
  },
})

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
