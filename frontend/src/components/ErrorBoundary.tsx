import { Component, type ReactNode } from 'react';

type Props = { children: ReactNode; fallback: ReactNode; onError?: (error: Error) => void };

export class ErrorBoundary extends Component<Props, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error) {
    this.props.onError?.(error);
  }

  render() {
    return this.state.error ? this.props.fallback : this.props.children;
  }
}
