"use client";

import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export default class AdminErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <div className="max-w-2xl mx-auto py-12 px-4">
          <div className="bg-surface-card border border-accent-danger/20 rounded-xl p-6">
            <h2 className="text-base font-semibold text-text-primary mb-2">
              Admin page error
            </h2>
            <p className="text-sm text-text-secondary mb-3">
              {this.state.error.message}
            </p>
            <pre className="text-xs text-text-muted bg-surface-elevated rounded-lg p-3 overflow-x-auto mb-4 max-h-32 overflow-y-auto">
              {this.state.error.stack?.split("\n").slice(0, 5).join("\n")}
            </pre>
            <button
              onClick={() => this.setState({ error: null })}
              className="px-4 py-2 rounded-lg bg-text-primary text-text-inverse text-sm font-medium hover:opacity-90"
            >
              Try again
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
