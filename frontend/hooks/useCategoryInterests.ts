"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useAuthContext } from "@/components/AuthProvider";
import { fetchUserPreferences, updateSportAffinities } from "@/lib/api";

const STORAGE_KEY = "bainluck_categoryInterests";

/**
 * Interest levels — maps to the onboarding 4-level selector.
 * Thumbs up/down step through these levels.
 */
export const INTEREST_LEVELS = [0, 0.1, 0.3, 1.0] as const;

export function stepUp(current: number): number {
  if (current >= 0.8) return 1.0;
  if (current >= 0.2) return 1.0;
  if (current > 0) return 0.3;
  return 0.1;
}

export function stepDown(current: number): number {
  if (current >= 0.8) return 0.3;
  if (current >= 0.2) return 0.1;
  if (current > 0) return 0;
  return 0;
}

export function getLevelLabel(value: number): string {
  if (value >= 0.8) return "Love it";
  if (value >= 0.2) return "Playoffs only";
  if (value > 0) return "If wild";
  return "Nah";
}

function loadLocalInterests(): Record<string, number> {
  if (typeof window === "undefined") return {};
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) return {};
    return JSON.parse(stored);
  } catch {
    return {};
  }
}

function saveLocalInterests(interests: Record<string, number>) {
  if (typeof window === "undefined") return;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(interests));
}

/**
 * Hook for reading/writing category interests.
 * Auth'd users: reads/writes via API (sport affinities).
 * Anonymous users: reads/writes via localStorage.
 */
export function useCategoryInterests() {
  const { isAuthenticated, isLoading: authLoading } = useAuthContext();
  const [interests, setInterestsState] = useState<Record<string, number>>({});
  const [isLoading, setIsLoading] = useState(true);
  const saveTimeoutRef = useRef<NodeJS.Timeout>();

  // Load initial data
  useEffect(() => {
    if (authLoading) return;

    if (isAuthenticated) {
      fetchUserPreferences()
        .then((prefs) => {
          setInterestsState(prefs.sport_affinities || {});
          setIsLoading(false);
        })
        .catch(() => {
          setIsLoading(false);
        });
    } else {
      setInterestsState(loadLocalInterests());
      setIsLoading(false);
    }
  }, [isAuthenticated, authLoading]);

  const setInterest = useCallback((category: string, value: number) => {
    setInterestsState(prev => {
      const updated = { ...prev, [category]: value };

      if (isAuthenticated) {
        // Debounce server saves to batch rapid thumb clicks
        if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);
        saveTimeoutRef.current = setTimeout(() => {
          updateSportAffinities(updated).catch((err) => {
            console.warn("Failed to save interests:", err);
          });
        }, 2000);
      } else {
        saveLocalInterests(updated);
      }

      return updated;
    });
  }, [isAuthenticated]);

  return { interests, setInterest, isLoading };
}
