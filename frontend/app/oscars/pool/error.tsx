"use client";

export default function OscarsPoolError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="min-h-screen bg-[#09090b] flex items-center justify-center">
      <div className="max-w-md mx-auto px-4 text-center">
        <h2 className="text-xl font-bold text-white mb-2">Something went wrong</h2>
        <p className="text-zinc-400 text-sm mb-4">{error.message}</p>
        <button
          onClick={reset}
          className="px-4 py-2 bg-[#D4AF37] text-black font-bold rounded-lg"
        >
          Try Again
        </button>
      </div>
    </div>
  );
}
