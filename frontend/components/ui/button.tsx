import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

/**
 * Bain Luck Button System
 *
 * Three variants mapped to the design system:
 *
 * - **primary**: Dark bg (bg-text-primary), white text. Main CTAs.
 *   Examples: "Play", "Sign In", "Submit", "Back to Discover"
 *
 * - **ghost**: Transparent bg, border, secondary text. Secondary actions.
 *   Examples: "Cancel", "Replay Today", "Back", filter toggles
 *
 * - **text**: No bg, no border, accent-brand color with hover underline.
 *   Examples: "See more", "View all", "Share", "Edit"
 *
 * Three sizes: sm (h-8), md (h-10, default), lg (h-12)
 */
const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-brand focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary:
          "bg-text-primary text-white rounded-lg hover:opacity-90",
        ghost:
          "bg-transparent border border-surface-border text-text-secondary rounded-lg hover:bg-surface-elevated hover:text-text-primary",
        text:
          "bg-transparent text-accent-brand hover:underline underline-offset-2 p-0 h-auto",
      },
      size: {
        sm: "h-8 px-3 text-xs rounded-md",
        md: "h-10 px-4 text-sm",
        lg: "h-12 px-6 text-sm",
      },
    },
    compoundVariants: [
      // Text variant ignores size padding — it renders inline
      { variant: "text", size: "sm", className: "h-auto px-0 text-xs" },
      { variant: "text", size: "md", className: "h-auto px-0 text-sm" },
      { variant: "text", size: "lg", className: "h-auto px-0 text-sm" },
    ],
    defaultVariants: {
      variant: "primary",
      size: "md",
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button"
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"

export { Button, buttonVariants }
