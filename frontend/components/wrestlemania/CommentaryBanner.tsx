"use client";

interface CommentaryBannerProps {
  text: string;
}

export default function CommentaryBanner({ text }: CommentaryBannerProps) {
  if (!text) return null;

  return (
    <div className="wm-commentary-banner">
      <div className="wm-commentary-mic">🎤</div>
      <p className="wm-commentary-text">{text}</p>
    </div>
  );
}
