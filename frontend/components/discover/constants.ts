export const CATEGORY_GRADIENTS: Record<string, string> = {
  basketball: "linear-gradient(135deg, #7c2d12, #c2410c)",
  football: "linear-gradient(135deg, #14532d, #15803d)",
  baseball: "linear-gradient(135deg, #7f1d1d, #b91c1c)",
  hockey: "linear-gradient(135deg, #1e3a5f, #2563eb)",
  soccer: "linear-gradient(135deg, #064e3b, #059669)",
  golf: "linear-gradient(135deg, #14532d, #166534)",
  mma: "linear-gradient(135deg, #450a0a, #991b1b)",
  boxing: "linear-gradient(135deg, #450a0a, #991b1b)",
  motorsports: "linear-gradient(135deg, #1c1917, #44403c)",
  economics: "linear-gradient(135deg, #2e1065, #7c3aed)",
  culture: "linear-gradient(135deg, #831843, #db2777)",
  tech: "linear-gradient(135deg, #083344, #0891b2)",
  politics: "linear-gradient(135deg, #1e1b4b, #4338ca)",
  geopolitics: "linear-gradient(135deg, #1e1b4b, #3730a3)",
  olympics: "linear-gradient(135deg, #78350f, #d97706)",
  cricket: "linear-gradient(135deg, #134e4a, #14b8a6)",
  weather: "linear-gradient(135deg, #0c4a6e, #0284c7)",
  entertainment: "linear-gradient(135deg, #701a75, #c026d3)",
};

const CATEGORY_COLORS: Record<string, { bg: string; text: string; emoji: string }> = {
  basketball: { bg: "bg-orange-500/15", text: "text-orange-600", emoji: "🏀" },
  football: { bg: "bg-green-700/15", text: "text-green-700", emoji: "🏈" },
  baseball: { bg: "bg-red-500/15", text: "text-red-600", emoji: "⚾" },
  hockey: { bg: "bg-blue-500/15", text: "text-blue-600", emoji: "🏒" },
  soccer: { bg: "bg-emerald-500/15", text: "text-emerald-600", emoji: "⚽" },
  golf: { bg: "bg-lime-600/15", text: "text-lime-700", emoji: "⛳" },
  mma: { bg: "bg-red-700/15", text: "text-red-700", emoji: "🥊" },
  boxing: { bg: "bg-red-600/15", text: "text-red-600", emoji: "🥊" },
  motorsports: { bg: "bg-gray-600/15", text: "text-gray-600", emoji: "🏎" },
  economics: { bg: "bg-violet-500/15", text: "text-violet-600", emoji: "📈" },
  culture: { bg: "bg-pink-500/15", text: "text-pink-600", emoji: "🎭" },
  tech: { bg: "bg-cyan-500/15", text: "text-cyan-600", emoji: "💻" },
  politics: { bg: "bg-indigo-500/15", text: "text-indigo-600", emoji: "🏛" },
  geopolitics: { bg: "bg-indigo-500/15", text: "text-indigo-600", emoji: "🌍" },
  olympics: { bg: "bg-amber-500/15", text: "text-amber-600", emoji: "🏅" },
  cricket: { bg: "bg-teal-500/15", text: "text-teal-600", emoji: "🏏" },
  weather: { bg: "bg-sky-500/15", text: "text-sky-600", emoji: "🌤" },
  entertainment: { bg: "bg-fuchsia-500/15", text: "text-fuchsia-600", emoji: "🎬" },
};

const DEFAULT_CAT = { bg: "bg-gray-500/15", text: "text-gray-600", emoji: "📊" };

export function getCat(cat: string | null | undefined) {
  if (!cat) return DEFAULT_CAT;
  return CATEGORY_COLORS[cat.toLowerCase()] ?? DEFAULT_CAT;
}
