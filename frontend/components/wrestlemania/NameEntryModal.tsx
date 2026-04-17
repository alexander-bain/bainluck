"use client";

import { useState } from "react";

interface NameEntryModalProps {
  onSubmit: (name: string) => void;
  loading?: boolean;
}

export default function NameEntryModal({ onSubmit, loading }: NameEntryModalProps) {
  const [name, setName] = useState("");

  return (
    <div className="wm-modal-overlay">
      <div className="wm-modal">
        <h2 className="wm-modal-title">Enter The Ring</h2>
        <p className="wm-modal-subtitle">
          Pick a display name for the leaderboard. Same name on another device? You&apos;ll pick up where you left off.
        </p>
        <input
          className="wm-modal-input"
          type="text"
          placeholder="Your name"
          maxLength={50}
          value={name}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && name.trim()) onSubmit(name.trim());
          }}
          autoFocus
        />
        <button
          className="wm-modal-btn"
          disabled={!name.trim() || loading}
          onClick={() => onSubmit(name.trim())}
        >
          {loading ? "Entering..." : "Let's Go"}
        </button>
      </div>
    </div>
  );
}
