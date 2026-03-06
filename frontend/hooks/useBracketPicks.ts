'use client';

import { useState, useCallback, useEffect } from 'react';
import type { BracketGame } from '@/lib/types';

export interface BracketPick {
  event_id: number;
  picked_team: string;  // team name the user picked
  locked: boolean;      // true once game starts or completes
  result: 'correct' | 'incorrect' | 'pending';
}

export interface BracketPicksState {
  picks: Record<number, BracketPick>;  // keyed by event_id
  totalPicks: number;
  correctPicks: number;
  decidedGames: number;
  accuracy: number;  // correctPicks / decidedGames, or 0 if no decided games
}

/**
 * useBracketPicks - Hook that manages bracket picks state using localStorage.
 *
 * Stores picks in localStorage with key: `mm_picks_2026_{tournamentType}`
 * Each pick includes the chosen team name, lock status, and result (correct/incorrect/pending).
 *
 * Features:
 * - Load initial picks from localStorage on mount
 * - Make a pick for an event (automatically locks when game starts)
 * - Get a specific pick by event_id
 * - Update results based on game outcomes (from BracketGame[])
 * - Compute accuracy stats (total, correct, decided, accuracy %)
 * - Reset all picks (clears localStorage)
 */
export function useBracketPicks(tournamentType: string) {
  const storageKey = `mm_picks_2026_${tournamentType}`;

  const [state, setState] = useState<BracketPicksState>({
    picks: {},
    totalPicks: 0,
    correctPicks: 0,
    decidedGames: 0,
    accuracy: 0,
  });

  // Load picks from localStorage on mount
  useEffect(() => {
    if (typeof window === 'undefined') return;

    try {
      const stored = localStorage.getItem(storageKey);
      if (stored) {
        const picks = JSON.parse(stored) as Record<number, BracketPick>;
        const correctCount = Object.values(picks).filter(p => p.result === 'correct').length;
        const decidedCount = Object.values(picks).filter(p => p.result !== 'pending').length;

        setState({
          picks,
          totalPicks: Object.keys(picks).length,
          correctPicks: correctCount,
          decidedGames: decidedCount,
          accuracy: decidedCount > 0 ? (correctCount / decidedCount) * 100 : 0,
        });
      }
    } catch (error) {
      console.error('Failed to load bracket picks:', error);
    }
  }, [storageKey]);

  // Persist picks to localStorage whenever they change
  useEffect(() => {
    if (typeof window === 'undefined') return;

    try {
      localStorage.setItem(storageKey, JSON.stringify(state.picks));
    } catch (error) {
      console.error('Failed to save bracket picks:', error);
    }
  }, [state.picks, storageKey]);

  /**
   * Make or update a pick for a specific event
   */
  const makePick = useCallback((eventId: number, teamName: string) => {
    setState(prevState => {
      const existingPick = prevState.picks[eventId];

      // If already picked, just update the team (don't change lock status unless already locked)
      if (existingPick) {
        if (existingPick.locked) {
          // Can't change a locked pick
          return prevState;
        }

        const updatedPicks = {
          ...prevState.picks,
          [eventId]: {
            ...existingPick,
            picked_team: teamName,
          },
        };

        return {
          ...prevState,
          picks: updatedPicks,
        };
      }

      // New pick
      const newPick: BracketPick = {
        event_id: eventId,
        picked_team: teamName,
        locked: false,
        result: 'pending',
      };

      const updatedPicks = {
        ...prevState.picks,
        [eventId]: newPick,
      };

      return {
        ...prevState,
        picks: updatedPicks,
        totalPicks: Object.keys(updatedPicks).length,
      };
    });
  }, []);

  /**
   * Get a specific pick by event_id, or null if not picked
   */
  const getPick = useCallback((eventId: number): BracketPick | null => {
    return state.picks[eventId] ?? null;
  }, [state.picks]);

  /**
   * Update pick results based on game outcomes
   * Locks picks for live/completed games and marks them correct/incorrect
   */
  const updateResults = useCallback((games: BracketGame[]) => {
    setState(prevState => {
      let changed = false;
      const updatedPicks = { ...prevState.picks };

      for (const game of games) {
        const pick = updatedPicks[game.event_id];
        if (!pick) continue;

        // Game is live or completed — lock the pick
        if (['live', 'in_progress', 'completed', 'closed'].includes(game.status)) {
          if (!pick.locked) {
            updatedPicks[game.event_id].locked = true;
            changed = true;
          }
        }

        // Determine result if game is completed
        if (['completed', 'closed'].includes(game.status) && pick.result === 'pending') {
          if (game.score_home === null || game.score_away === null) continue;

          const winner = game.score_home > game.score_away ? game.home_team : game.away_team;
          const isCorrect = pick.picked_team === winner;

          updatedPicks[game.event_id].result = isCorrect ? 'correct' : 'incorrect';
          changed = true;
        }
      }

      if (!changed) return prevState;

      // Recompute stats
      const correctCount = Object.values(updatedPicks).filter(p => p.result === 'correct').length;
      const decidedCount = Object.values(updatedPicks).filter(p => p.result !== 'pending').length;

      return {
        picks: updatedPicks,
        totalPicks: Object.keys(updatedPicks).length,
        correctPicks: correctCount,
        decidedGames: decidedCount,
        accuracy: decidedCount > 0 ? (correctCount / decidedCount) * 100 : 0,
      };
    });
  }, []);

  /**
   * Reset all picks (clears localStorage and state)
   */
  const resetPicks = useCallback(() => {
    setState({
      picks: {},
      totalPicks: 0,
      correctPicks: 0,
      decidedGames: 0,
      accuracy: 0,
    });
    if (typeof window !== 'undefined') {
      try {
        localStorage.removeItem(storageKey);
      } catch (error) {
        console.error('Failed to reset bracket picks:', error);
      }
    }
  }, [storageKey]);

  return {
    ...state,
    makePick,
    getPick,
    updateResults,
    resetPicks,
  };
}
