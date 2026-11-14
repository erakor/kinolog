import { Component, type ReactNode } from 'react'

interface State {
  error: Error | null
}

/** Shows a load failure (data or code-split chunk) in place of the view. */
export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  render() {
    if (this.state.error) {
      return <p className="empty">Could not load this view: {this.state.error.message}</p>
    }
    return this.props.children
  }
}
