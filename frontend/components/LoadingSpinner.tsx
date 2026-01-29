"use client";

interface LoadingSpinnerProps {
  size?: "sm" | "md" | "lg";
  text?: string;
}

/**
 * Loading spinner with subtle animation.
 */
export default function LoadingSpinner({
  size = "md",
  text,
}: LoadingSpinnerProps) {
  const sizeClasses = {
    sm: "w-4 h-4 border-2",
    md: "w-8 h-8 border-2",
    lg: "w-12 h-12 border-3",
  };

  return (
    <div className="flex flex-col items-center justify-center gap-3">
      <div
        className={`${sizeClasses[size]} border-mist border-t-charcoal rounded-full animate-spin`}
      />
      {text && <span className="text-caption text-slate">{text}</span>}
    </div>
  );
}
