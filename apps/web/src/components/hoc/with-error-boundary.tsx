"use client";

import { Component as ReactComponent, type ComponentType, type ErrorInfo, type ReactNode } from "react";
import { displayNameOf } from "./display-name";

export type ErrorFallbackProps = { error: Error; reset: () => void };

type BoundaryProps = {
  fallback: ComponentType<ErrorFallbackProps> | ReactNode;
  onError?: (error: Error, info: ErrorInfo) => void;
  /** Changing any key resets the boundary (e.g. the selected trip id). */
  resetKeys?: readonly unknown[];
  children: ReactNode;
};

type BoundaryState = { error: Error | null; keys: readonly unknown[] };

/** Isolates a streaming panel (copilot, execution viewer, chat) so its failure stays local. */
export class ErrorBoundary extends ReactComponent<BoundaryProps, BoundaryState> {
  state: BoundaryState = { error: null, keys: this.props.resetKeys ?? [] };

  static getDerivedStateFromError(error: Error): Partial<BoundaryState> {
    return { error };
  }

  static getDerivedStateFromProps(props: BoundaryProps, state: BoundaryState): Partial<BoundaryState> | null {
    const keys = props.resetKeys ?? [];
    const changed = keys.length !== state.keys.length || keys.some((k, i) => !Object.is(k, state.keys[i]));
    return changed ? { error: null, keys } : null;
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    this.props.onError?.(error, info);
  }

  reset = () => this.setState({ error: null });

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    const { fallback: Fallback } = this.props;
    if (typeof Fallback === "function") return <Fallback error={error} reset={this.reset} />;
    return Fallback;
  }
}

export function withErrorBoundary<P extends object>(
  Component: ComponentType<P>,
  opts: Omit<BoundaryProps, "children" | "resetKeys"> & { resetKeys?: (props: P) => readonly unknown[] },
) {
  function WithErrorBoundary(props: P) {
    return (
      <ErrorBoundary fallback={opts.fallback} onError={opts.onError} resetKeys={opts.resetKeys?.(props)}>
        <Component {...props} />
      </ErrorBoundary>
    );
  }
  WithErrorBoundary.displayName = `withErrorBoundary(${displayNameOf(Component as ComponentType<never>)})`;
  return WithErrorBoundary;
}
