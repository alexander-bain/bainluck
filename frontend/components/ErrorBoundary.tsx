"use client";

import React from "react";

interface Props {
  children: React.ReactNode;
  fallback?: React.ReactNode;
  /**
   * UX-P055: when this value changes, a boundary that has caught retries.
   *
   * Without it a boundary LATCHES: `hasError` is only ever cleared by the user
   * pressing "Try again". On a polling surface — the event page refetches while
   * you watch it — one transient bad payload would keep a section dead for the
   * rest of the session even after good data arrived. Callers pass whatever
   * identifies the data the subtree renders.
   *
   * Optional, and `undefined` never changes, so every existing caller keeps its
   * current latching behaviour untouched.
   */
  resetKey?: unknown;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export default class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidUpdate(prevProps: Props) {
    if (this.state.hasError && prevProps.resetKey !== this.props.resetKey) {
      this.setState({ hasError: false, error: null });
    }
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div className="py-8 text-center">
          <p className="text-text-secondary text-sm">Something went wrong rendering this section.</p>
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            className="mt-2 text-xs text-blue-600 hover:underline"
          >
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
